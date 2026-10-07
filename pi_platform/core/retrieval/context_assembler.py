"""Default context assembler core.

Implements :class:`pi_platform.ports.retrieval.context_assembler.ContextAssemblerPort`
with deduplication, context-budget enforcement, citation
preservation, authoritative-evidence preference, conflict
detection and uncertainty surfacing per §32.

The core is intentionally pure and free of Phase 3 backend imports;
the only side effect is the per-call statistics counters used by
the retrieval-benchmark fixture.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from pi_platform.core.canonical.value_types import (
    KnowledgeState,
    ProjectVersion,
)

from pi_platform.ports.retrieval.context_assembler import (
    Citation,
    ContextAssemblerError,
    ContextAssemblerPort,
    ContextBudget,
    ContextBundle,
)
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit


__all__ = [
    "ContextAssemblerCore",
    "DROP_DEDUPLICATED",
    "DROP_BUDGET_EXHAUSTED",
    "DROP_AUTHORITATIVE_PREFERENCE",
]


DROP_DEDUPLICATED = "deduplicated"
DROP_BUDGET_EXHAUSTED = "budget_exhausted"
DROP_AUTHORITATIVE_PREFERENCE = "authoritative_preference"


def _project_version(hit: RetrievalHit) -> ProjectVersion:
    git = hit.metadata.gitCommit or ""
    return ProjectVersion(
        gitHead=git,
        workingTreeFingerprint="",
        knowledgeSchemaVersion=hit.metadata.version or "0.0.0",
        embeddingModelVersion="unknown",
        indexSchemaVersion="unknown",
    )


class ContextAssemblerCore(ContextAssemblerPort):
    """Default §32 context assembler."""

    def __init__(self) -> None:
        self._calls = 0
        self._dedup = 0
        self._budget_drops = 0
        self._authority_drops = 0
        self._conflicts = 0
        self._uncertainties = 0

    def assemble(
        self, hits: Sequence[RetrievalHit], *,
        contextBudget: ContextBudget,
        query: object,
    ) -> ContextBundle:
        self._calls += 1
        deduped = self._deduplicate(hits)
        # Authoritative-preference: split the deduplicated hits
        # BEFORE the budget truncation so authoritative evidence
        # wins the budget, and inferred / assumption hits are
        # dropped with the documented `authoritative_preference`
        # reason per §32.
        authoritative, inferred = self._split_authoritative(deduped)
        ordered = list(authoritative) + list(inferred)
        trimmed, budget_drops = self._enforce_budget(ordered, contextBudget)
        # When authoritative evidence is available, demote budget
        # drops of inferred hits to the documented
        # ``authoritative_preference`` reason per §32.
        drop_records: list[tuple[object, str]] = []
        drop_records.extend(getattr(self, "_dedup_drop_reasons", []))
        if authoritative:
            for hit, reason in budget_drops:
                if hit in inferred:
                    drop_records.append((hit, DROP_AUTHORITATIVE_PREFERENCE))
                    self._authority_drops += 1
                else:
                    drop_records.append((hit, reason))
        else:
            drop_records.extend(budget_drops)
        self._budget_drop_reasons = drop_records
        uncertain = [h for h in trimmed if _is_uncertain(h)]
        self._uncertainties += len(uncertain)
        conflicting = self._detect_conflicts(trimmed)
        self._conflicts += len(conflicting)
        citations = tuple(self._citation(h) for h in trimmed)
        dropped_hits = tuple(hit for hit, _ in drop_records)
        drop_reasons = tuple(reason for _, reason in drop_records)
        explanations = self._explanations(query, authoritative, conflicting)
        return ContextBundle(
            hits=tuple(trimmed),
            citations=citations,
            authoritativeHits=tuple(authoritative),
            conflictingHits=tuple(conflicting),
            uncertainHits=tuple(uncertain),
            budgetUsed=sum(h.tokenEstimate for h in trimmed),
            droppedHits=dropped_hits,
            dropReasons=drop_reasons,
            explanations=explanations,
        )

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "deduplicated": self._dedup,
            "budget_drops": self._budget_drops,
            DROP_DEDUPLICATED: self._dedup,
            DROP_BUDGET_EXHAUSTED: self._budget_drops,
            DROP_AUTHORITATIVE_PREFERENCE: self._authority_drops,
            "conflicts": self._conflicts,
            "uncertainties": self._uncertainties,
        }

    # -- internal helpers --------------------------------------------------

    def _deduplicate(
        self, hits: Sequence[RetrievalHit],
    ) -> list[RetrievalHit]:
        by_id: dict[str, RetrievalHit] = {}
        deduped: list[RetrievalHit] = []
        drop_reasons: list[tuple[RetrievalHit, str]] = []
        for hit in hits:
            existing = by_id.get(hit.chunkId)
            if existing is None:
                by_id[hit.chunkId] = hit
                deduped.append(hit)
                continue
            self._dedup += 1
            drop_reasons.append((hit, DROP_DEDUPLICATED))
        self._dedup_drop_reasons = drop_reasons
        return deduped

    def _enforce_budget(
        self, hits: Sequence[RetrievalHit], budget: ContextBudget,
    ) -> tuple[list[RetrievalHit], list[tuple[RetrievalHit, str]]]:
        trimmed: list[RetrievalHit] = []
        remaining = budget.tokenLimit
        drop_reasons: list[tuple[RetrievalHit, str]] = []
        for hit in hits:
            tokens = max(hit.tokenEstimate, 1)
            if remaining < tokens:
                self._budget_drops += 1
                drop_reasons.append((hit, DROP_BUDGET_EXHAUSTED))
                continue
            if budget.maxHits and len(trimmed) >= budget.maxHits:
                self._budget_drops += 1
                drop_reasons.append((hit, DROP_BUDGET_EXHAUSTED))
                continue
            trimmed.append(hit)
            remaining -= tokens
        return trimmed, drop_reasons

    def _split_authoritative(
        self, hits: Sequence[RetrievalHit],
    ) -> tuple[list[RetrievalHit], list[RetrievalHit]]:
        authoritative = [h for h in hits if _is_authoritative(h)]
        inferred = [h for h in hits if not _is_authoritative(h)]
        return authoritative, inferred

    def _detect_conflicts(
        self, hits: Sequence[RetrievalHit],
    ) -> list[RetrievalHit]:
        conflicts: list[RetrievalHit] = []
        seen_conflicts: dict[str, set[str]] = defaultdict(set)
        for i, left in enumerate(hits):
            for right in hits[i + 1:]:
                if _are_conflicting(left, right):
                    seen_conflicts[left.chunkId].add(right.chunkId)
                    seen_conflicts[right.chunkId].add(left.chunkId)
                    conflicts.append(left)
                    conflicts.append(right)
        # Preserve input order while deduplicating the conflict set.
        ordered: list[RetrievalHit] = []
        seen: set[str] = set()
        for hit in conflicts:
            if hit.chunkId in seen:
                continue
            seen.add(hit.chunkId)
            ordered.append(hit)
        return ordered

    def _citation(self, hit: RetrievalHit) -> Citation:
        return Citation(
            chunkId=hit.chunkId,
            contentHash=hit.contentHash or "",
            sourceReference=hit.metadata.sourcePath or hit.chunkId,
            projectVersion=_project_version(hit),
            evidenceWeight=hit.evidenceWeight,
        )

    def _drop_reasons(
        self, original: Sequence[RetrievalHit], deduped: list[RetrievalHit],
        trimmed: list[RetrievalHit],
    ) -> list[tuple[RetrievalHit, str]]:
        out: list[tuple[RetrievalHit, str]] = []
        out.extend(getattr(self, "_dedup_drop_reasons", []))
        out.extend(getattr(self, "_budget_drop_reasons", []))
        kept_ids = {h.chunkId for h in trimmed}
        for hit in original:
            if hit.chunkId in kept_ids:
                continue
            if any(hit is dropped for dropped, _ in out):
                continue
            out.append((hit, DROP_AUTHORITATIVE_PREFERENCE))
        return out

    def _explanations(
        self, query: object,
        authoritative: Sequence[RetrievalHit],
        conflicts: Sequence[RetrievalHit],
    ) -> tuple[str, ...]:
        bits = [
            f"Context bundle for purpose={query.purpose!r}",
            f"authoritativeHits={len(authoritative)}",
            f"conflictingHits={len(conflicts)}",
        ]
        return tuple(bits)


def _is_authoritative(hit: RetrievalHit) -> bool:
    return (
        hit.knowledgeState == KnowledgeState.VERIFIED
        and (hit.evidenceWeight or 0) >= 0.5
    )


def _is_uncertain(hit: RetrievalHit) -> bool:
    return hit.knowledgeState in (
        KnowledgeState.INFERRED,
        KnowledgeState.ASSUMPTION,
        KnowledgeState.STALE,
        KnowledgeState.UNKNOWN,
        KnowledgeState.CONFLICTING,
    )


def _are_conflicting(left: RetrievalHit, right: RetrievalHit) -> bool:
    if left.chunkId == right.chunkId:
        return False
    if not left.metadata.validTo and not right.metadata.validTo:
        return False
    if not left.metadata.validTo or not right.metadata.validTo:
        return False
    if left.metadata.validTo == right.metadata.validTo:
        return False
    return left.chunkId[:4] == right.chunkId[:4] and left.chunkId != right.chunkId