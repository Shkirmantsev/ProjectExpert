"""Default candidate selection core.

Implements :class:`pi_platform.ports.retrieval.selection.SelectionPort`
with the non-destructive rules from the retrieval-candidate-selection
delta spec: protected-reason detection, content-hash / chunk-id
near-duplicate collapse with provenance, score-ordered PRIMARY
selection with a soft per-source diversity cap, an uncapped-diversity
RESERVE pool and a full per-candidate :class:`CandidateTrace`.
"""

from __future__ import annotations

from typing import Sequence

from pi_platform.core.retrieval.query_features import QueryFeatures
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.selection import (
    DEFAULT_MAX_PRIMARY_PER_SOURCE,
    DEFAULT_PRIMARY_TOP_K,
    DEFAULT_RESERVE_TOP_K,
    CandidateTrace,
    SelectionPort,
    SelectionResult,
    SelectionState,
)


__all__ = [
    "SelectionCore",
    "DROP_NEAR_DUPLICATE",
]


DROP_NEAR_DUPLICATE = "near_duplicate"

# Hit-level selection state written by the hybrid core for exact
# candidates on the mixed identifier + free-text path.
_HIT_STATE_PROTECTED = "PROTECTED"


class SelectionCore(SelectionPort):
    """Default non-destructive candidate selection implementation.

    Takes no required constructor arguments; every decision is made
    from the ``select`` inputs so the core stays pure and testable.
    """

    def select(
        self, candidates: Sequence[RetrievalHit], *,
        query_features: QueryFeatures | None,
        budget: int,
    ) -> SelectionResult:
        qf = query_features or QueryFeatures()
        winners, dropped, duplicate_of = self._deduplicate(candidates)
        protected: list[tuple[RetrievalHit, str]] = []
        rest: list[RetrievalHit] = []
        for hit in winners:
            reason = self._protected_reason(hit, qf)
            if reason:
                protected.append((hit, reason))
            else:
                rest.append(hit)
        rest.sort(key=lambda h: (-h.score, h.chunkId))
        primary_cap = min(DEFAULT_PRIMARY_TOP_K, max(budget, 0))
        reserve_cap = min(
            DEFAULT_RESERVE_TOP_K, max(budget - 0, 0),
        )
        # Reserve is bounded by the remaining budget after primary.
        primary, reserve, beyond_reserve = self._split_primary_reserve(
            rest, primary_cap, reserve_cap,
            bypass_diversity=bool(qf.target_document),
        )
        traces = self._build_traces(
            candidates=candidates,
            winners=winners,
            protected=protected,
            primary=primary,
            reserve=reserve,
            dropped=dropped,
            duplicate_of=duplicate_of,
            beyond_reserve=beyond_reserve,
        )
        return SelectionResult(
            primary=tuple(primary),
            reserve=tuple(reserve),
            protected=tuple(h for h, _ in protected),
            support=(),
            dropped_duplicate=tuple(dropped),
            traces=tuple(traces),
        )

    # -- internal helpers --------------------------------------------------

    def _deduplicate(
        self, candidates: Sequence[RetrievalHit],
    ) -> tuple[list[RetrievalHit], list[RetrievalHit], dict[str, str]]:
        """Collapse near-duplicates by chunkId and non-empty contentHash.

        The first candidate in input order wins; losers are recorded
        with a ``duplicate_of`` link so provenance is never discarded.
        """

        winners: list[RetrievalHit] = []
        dropped: list[RetrievalHit] = []
        duplicate_of: dict[str, str] = {}
        seen_ids: dict[str, str] = {}
        seen_hashes: dict[str, str] = {}
        for hit in candidates:
            winner_id = seen_ids.get(hit.chunkId)
            if winner_id is None and hit.contentHash:
                winner_id = seen_hashes.get(hit.contentHash)
            if winner_id is not None:
                dropped.append(hit)
                duplicate_of[hit.chunkId] = winner_id
                continue
            seen_ids[hit.chunkId] = hit.chunkId
            if hit.contentHash:
                seen_hashes.setdefault(hit.contentHash, hit.chunkId)
            winners.append(hit)
        return winners, dropped, duplicate_of

    def _protected_reason(
        self, hit: RetrievalHit, qf: QueryFeatures,
    ) -> str:
        """Return the protected reason for ``hit`` or an empty string.

        A candidate is protected when it is an exact upstream match
        (marked ``PROTECTED`` by the hybrid core), matches an
        engineering identifier, matches a quoted phrase, or matches
        a target symbol. A target document alone does NOT make a
        candidate protected; the target_document flag only BYPASSES
        the per-source diversity cap during primary selection.
        """

        if hit.selection_state == _HIT_STATE_PROTECTED:
            return "exact candidate protected upstream"
        for identifier in qf.identifiers:
            if (identifier in hit.chunkId or identifier in hit.snippet):
                return f"engineering identifier {identifier}"
        for phrase in qf.quoted_phrases:
            if phrase and phrase in hit.snippet:
                return f"quoted phrase {phrase!r}"
        if qf.target_symbol and qf.target_symbol in hit.chunkId:
            return f"target symbol {qf.target_symbol}"
        return ""

    def _split_primary_reserve(
        self, ranked: Sequence[RetrievalHit],
        primary_cap: int, reserve_cap: int, *,
        bypass_diversity: bool,
    ) -> tuple[list[RetrievalHit], list[RetrievalHit],
               list[RetrievalHit]]:
        """Apply the PRIMARY diversity cap and fill the RESERVE pool.

        Candidates that exceed the reserve cap are returned separately
        so their traces can record why they are outside the active
        pools; they are never silently lost.
        """

        primary: list[RetrievalHit] = []
        reserve: list[RetrievalHit] = []
        per_source: dict[str, int] = {}
        for hit in ranked:
            if len(primary) < primary_cap:
                doc = hit.metadata.documentId
                if bypass_diversity or (
                    per_source.get(doc, 0) < DEFAULT_MAX_PRIMARY_PER_SOURCE
                ):
                    primary.append(hit)
                    per_source[doc] = per_source.get(doc, 0) + 1
                    continue
            reserve.append(hit)
        active_reserve = reserve[:reserve_cap]
        beyond = reserve[reserve_cap:]
        return primary, active_reserve, beyond

    def _build_traces(
        self, *, candidates: Sequence[RetrievalHit],
        winners: Sequence[RetrievalHit],
        protected: Sequence[tuple[RetrievalHit, str]],
        primary: Sequence[RetrievalHit],
        reserve: Sequence[RetrievalHit],
        dropped: Sequence[RetrievalHit],
        duplicate_of: dict[str, str],
        beyond_reserve: Sequence[RetrievalHit],
    ) -> list[CandidateTrace]:
        """Populate a :class:`CandidateTrace` for every input candidate."""

        protected_map = {h.chunkId: reason for h, reason in protected}
        primary_ids = {h.chunkId for h in primary}
        reserve_ids = {h.chunkId for h in reserve}
        dropped_ids = {h.chunkId for h in dropped}
        rrf_ranks = {h.chunkId: rank
                     for rank, h in enumerate(winners, start=1)}
        traces: list[CandidateTrace] = []
        for hit in candidates:
            chunk_id = hit.chunkId
            if chunk_id in dropped_ids:
                state = SelectionState.DROPPED_DUPLICATE
                reason = DROP_NEAR_DUPLICATE
                protected_reason = ""
                duplicate = duplicate_of.get(chunk_id, "")
            elif chunk_id in protected_map:
                state = SelectionState.PROTECTED
                reason = "protected"
                protected_reason = protected_map[chunk_id]
                duplicate = ""
            elif chunk_id in primary_ids:
                state = SelectionState.PRIMARY
                reason = "primary"
                protected_reason = ""
                duplicate = ""
            elif chunk_id in reserve_ids:
                state = SelectionState.RESERVE
                reason = "reserve"
                protected_reason = ""
                duplicate = ""
            else:
                state = SelectionState.RESERVE
                reason = "beyond_reserve_cap"
                protected_reason = ""
                duplicate = ""
            traces.append(CandidateTrace(
                chunk_id=chunk_id,
                exact_match=hit.source == "exact",
                rrf_rank=rrf_ranks.get(chunk_id, 0),
                rrf_score=hit.score,
                selection_state=state,
                protected_reason=protected_reason,
                duplicate_of=duplicate,
                source_document_id=hit.metadata.documentId,
                trace_reasons=(reason,),
            ))
        return traces
