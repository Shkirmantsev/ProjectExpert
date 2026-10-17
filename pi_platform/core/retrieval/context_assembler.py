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
    "DROP_NEAR_DUPLICATE_COLLAPSED",
]


DROP_DEDUPLICATED = "deduplicated"
DROP_BUDGET_EXHAUSTED = "budget_exhausted"
DROP_AUTHORITATIVE_PREFERENCE = "authoritative_preference"
# Change Package A4: near-duplicate collapse in the selection-aware
# path keeps the provenance of every collapsed candidate.
DROP_NEAR_DUPLICATE_COLLAPSED = "near_duplicate_collapsed"


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
        support_evidence: Sequence[object] = (),
        selection_result: object = None,
    ) -> ContextBundle:
        self._calls += 1
        # Selection-aware path (Change Package A4). The legacy path
        # stays byte-identical when no selection result and no
        # support evidence are supplied.
        if selection_result is not None or support_evidence:
            return self._assemble_selection_aware(
                hits,
                contextBudget=contextBudget,
                query=query,
                support_evidence=support_evidence,
                selection_result=selection_result,
            )
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

    def _assemble_selection_aware(
        self, hits: Sequence[RetrievalHit], *,
        contextBudget: ContextBudget,
        query: object,
        support_evidence: Sequence[object],
        selection_result: object,
    ) -> ContextBundle:
        """Assemble a bundle with PRIMARY / PROTECTED / SUPPORT / RESERVE
        awareness (Change Package A4, plan §6).

        Consumption order: protected direct evidence → authoritative
        PRIMARY → other PRIMARY → mandatory SUPPORT → conflict-support
        evidence → reserve escalation for uncovered subtopics →
        optional additional SUPPORT, stopping at the context budget.
        Near-duplicates are collapsed by ``contentHash`` (when
        non-empty) and by ``chunkId`` while preserving the collapsed
        provenance in ``dropReasons`` / ``explanations``.
        """
        if selection_result is not None:
            protected_hits = tuple(
                getattr(selection_result, "protected", ()) or (),
            )
            primary = tuple(
                getattr(selection_result, "primary", ()) or (),
            )
            reserve_hits = tuple(
                getattr(selection_result, "reserve", ()) or (),
            )
        else:
            protected_hits = ()
            primary = tuple(hits)
            reserve_hits = ()
        support = tuple(support_evidence or ())
        authoritative_primary, other_primary = (
            self._split_authoritative(primary)
        )

        state = _SelectionConsumeState(contextBudget)

        # 1. protected direct evidence.
        for hit in protected_hits:
            state.try_add(hit, pool="protected")
        # 2. authoritative PRIMARY evidence.
        for hit in authoritative_primary:
            state.try_add(hit, pool="primary")
        # 3. other PRIMARY evidence.
        for hit in other_primary:
            state.try_add(hit, pool="primary")
        # 4. mandatory SUPPORT, conservatively capped.
        mandatory_cap = max(1, contextBudget.tokenLimit // 4) // 2
        mandatory_support = support[:mandatory_cap]
        for item in mandatory_support:
            state.try_add(item, pool="support")
        # 5. conflict-support evidence: remaining SUPPORT items whose
        #    source document matches a conflict already in the bundle.
        hit_like = [
            h for h in state.trimmed
            if isinstance(h, RetrievalHit)
        ]
        conflicting = self._detect_conflicts(hit_like)
        conflict_docs = {
            c.metadata.documentId for c in conflicting
            if c.metadata.documentId
        }
        for item in support[mandatory_cap:]:
            doc = str(getattr(item, "source_document_id", "") or "")
            if not doc or doc not in conflict_docs:
                continue
            state.try_add(item, pool="support")
        # 6. reserve escalation for uncovered subtopics: pull reserve
        #    candidates until every distinct source document already
        #    represented across the selection pools has at least one
        #    hit in the trimmed set, or the budget is exhausted.
        represented = {
            h.metadata.documentId for h in hit_like
            if h.metadata.documentId
        }
        target_docs = represented | {
            h.metadata.documentId for h in (*primary, *reserve_hits)
            if h.metadata.documentId
        }
        for hit in reserve_hits:
            if state.budget_exhausted:
                break
            doc = hit.metadata.documentId
            if doc and doc in represented:
                continue
            if state.try_add(hit, pool="reserve") and doc:
                represented.add(doc)
        # 7. optional additional SUPPORT if the budget remains.
        for item in support[mandatory_cap:]:
            if state.budget_exhausted:
                break
            state.try_add(item, pool="support")

        trimmed = state.trimmed
        hit_like = [h for h in trimmed if isinstance(h, RetrievalHit)]
        uncertain = [h for h in hit_like if _is_uncertain(h)]
        self._uncertainties += len(uncertain)
        self._conflicts += len(conflicting)
        self._dedup += state.collapsed
        self._budget_drops += state.budget_drops
        citations = tuple(self._citation(h) for h in hit_like)
        explanations = list(
            self._explanations(query, authoritative_primary, conflicting),
        )
        explanations.extend(state.explanations)
        return ContextBundle(
            hits=tuple(trimmed),
            citations=citations,
            authoritativeHits=tuple(authoritative_primary),
            conflictingHits=tuple(conflicting),
            uncertainHits=tuple(uncertain),
            budgetUsed=sum(_token_estimate(h) for h in trimmed),
            droppedHits=tuple(item for item, _ in state.drop_records),
            dropReasons=tuple(
                reason for _, reason in state.drop_records
            ),
            explanations=tuple(explanations),
            protected_hits=tuple(state.protected_included),
            support_hits=tuple(state.support_included),
            reserve_hits=tuple(state.reserve_included),
            selection_summary={
                "primary": len(primary),
                "reserve": len(reserve_hits),
                "protected": len(protected_hits),
                "support": len(support),
            },
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


def _token_estimate(item: object) -> int:
    """Token cost of a bundle item.

    :class:`RetrievalHit` carries ``tokenEstimate`` directly. Support
    evidence (and any other object without that field) is estimated
    from its snippet at roughly four characters per token; the
    minimum cost is always one token so tiny items are still bounded.
    """
    tokens = getattr(item, "tokenEstimate", None)
    if tokens is not None:
        return max(int(tokens), 1)
    snippet = str(getattr(item, "snippet", "") or "")
    return max(1, len(snippet) // 4)


class _SelectionConsumeState:
    """Budget + near-duplicate bookkeeping for the selection-aware path.

    Tracks the trimmed item list, per-pool inclusions (protected /
    reserve / support), near-duplicate collapses with provenance and
    budget drops. Kept as a private helper so the assembler core
    stays a readable sequence of consumption steps.
    """

    def __init__(self, budget: ContextBudget) -> None:
        self.budget = budget
        self.remaining = budget.tokenLimit
        self.trimmed: list[object] = []
        self.protected_included: list[object] = []
        self.reserve_included: list[object] = []
        self.support_included: list[object] = []
        self.drop_records: list[tuple[object, str]] = []
        self.explanations: list[str] = []
        self.seen_ids: dict[str, str] = {}
        self.seen_hashes: dict[str, str] = {}
        self.collapsed = 0
        self.budget_drops = 0

    @property
    def budget_exhausted(self) -> bool:
        return (
            bool(self.budget.maxHits)
            and len(self.trimmed) >= self.budget.maxHits
        ) or self.remaining <= 0

    def try_add(self, item: object, *, pool: str) -> bool:
        """Try to consume ``item`` into the trimmed bundle.

        Near-duplicates (same ``chunkId`` or non-empty ``contentHash``)
        are dropped first with the ``near_duplicate_collapsed`` reason
        and a ``collapsed_into:<winner>`` explanation so provenance is
        preserved. Items that do not fit the token / hit budget are
        dropped with ``budget_exhausted``.
        """
        chunk_key = str(
            getattr(item, "chunkId", "")
            or getattr(item, "chunk_id", "")
            or ""
        )
        content_hash = str(getattr(item, "contentHash", "") or "")
        winner = ""
        if chunk_key and chunk_key in self.seen_ids:
            winner = self.seen_ids[chunk_key]
        elif content_hash and content_hash in self.seen_hashes:
            winner = self.seen_hashes[content_hash]
        if winner:
            self.collapsed += 1
            self.drop_records.append(
                (item, DROP_NEAR_DUPLICATE_COLLAPSED),
            )
            self.explanations.append(f"collapsed_into:{winner}")
            return False
        tokens = _token_estimate(item)
        if self.budget.maxHits and len(self.trimmed) >= self.budget.maxHits:
            self.budget_drops += 1
            self.drop_records.append((item, DROP_BUDGET_EXHAUSTED))
            return False
        if self.remaining < tokens:
            self.budget_drops += 1
            self.drop_records.append((item, DROP_BUDGET_EXHAUSTED))
            return False
        self.trimmed.append(item)
        self.remaining -= tokens
        if chunk_key:
            self.seen_ids[chunk_key] = chunk_key
        if content_hash:
            self.seen_hashes.setdefault(
                content_hash, chunk_key or content_hash,
            )
        if pool == "protected":
            self.protected_included.append(item)
        elif pool == "reserve":
            self.reserve_included.append(item)
        elif pool == "support":
            self.support_included.append(item)
        return True