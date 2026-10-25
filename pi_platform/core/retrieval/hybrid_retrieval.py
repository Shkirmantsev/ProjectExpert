"""Default hybrid retrieval composition core.

Implements :class:`pi_platform.ports.retrieval.hybrid_retrieval.HybridRetrievalPort`
with reciprocal-rank-fusion (RRF) of the dense and sparse candidate
streams and an identifier-recognition pre-pass that routes
engineering identifiers to the exact lookup.

The core is intentionally minimal: it consumes a dense candidate
generator, a sparse candidate generator and an identifier detector
through duck-typed callables so adapters can plug in the Phase 3
``DenseIndexPort`` / ``SparseIndexPort`` (or in-memory fakes for
tests) without the core importing any specific backend.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import (
    HIT_SOURCE_DENSE,
    HIT_SOURCE_EXACT,
    HIT_SOURCE_HYBRID,
    HIT_SOURCE_SPARSE,
    HybridRetrievalError,
    HybridRetrievalPort,
    RetrievalHit,
)

if TYPE_CHECKING:
    # Import for typing only: ``query_features`` imports
    # ``IDENTIFIER_PATTERN`` from this module at runtime, so a
    # runtime import here would create a circular dependency.
    from pi_platform.core.retrieval.query_features import QueryFeatures


__all__ = [
    "HybridRetrievalCore",
    "IDENTIFIER_PATTERN",
    "RRF_K",
    "SELECTION_STATE_PROTECTED",
]


# PROTECTED marker for exact candidates retained on the mixed
# identifier + free-text path (Change Package A1).
SELECTION_STATE_PROTECTED = "PROTECTED"


# Engineering identifier grammar from §26 + §27 spec. Matches tokens
# such as ``GEN_3.0.03``, ``ILO-5193``, ``RpaVaryToteJpaMapper``,
# ``PSB_FINISH_PACK``, ``0x84721`` and similar PascalCase /
# snake_case / alphanumeric-with-separator forms. The grammar is
# intentionally permissive so identifier recognition succeeds on
# canonical engineering names without leaking into prose.
IDENTIFIER_PATTERN = re.compile(
    r"\b("
    r"0x[0-9A-Fa-f]+"
    r"|[A-Z]+(?:_[A-Z0-9]+){1,}"
    r"|[A-Z][A-Za-z0-9]{2,}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*"
    r"|(?:[A-Z][a-z]+){3,}[A-Za-z0-9]*"
    r")\b"
)


# RRF (reciprocal rank fusion) constant. The score for a hit at
# rank ``r`` is ``1 / (RRF_K + r)``. The standard Cordonnier et al.
# 2020 / Cormack et al. 2009 value is ``60``.
RRF_K = 60


# Public alias kept for callers that already use this name. The
# identifier pattern grammar lives in IDENTIFIER_PATTERN above.
IDENTIFIER_GRAMMAR = IDENTIFIER_PATTERN


class HybridRetrievalCore(HybridRetrievalPort):
    """RRF-fused hybrid retrieval core."""

    def __init__(
        self,
        dense_query: Callable[[str, int], Sequence[RetrievalHit]],
        sparse_query: Callable[[str, int], Sequence[RetrievalHit]],
        identifier_detector: Callable[[str], bool] | None = None,
        exact_lookup: Callable[[str], Sequence[RetrievalHit]] | None = None,
        fusion_strategy: str = "rrf",
        level: int = 0,
        protected_extractor: Callable[[QueryFeatures], frozenset[str]]
        | None = None,
    ) -> None:
        self._dense_query = dense_query
        self._sparse_query = sparse_query
        self._identifier_detector = (
            identifier_detector
            or (lambda text: bool(IDENTIFIER_PATTERN.search(text or "")))
        )
        self._exact_lookup = exact_lookup
        self._fusion_strategy = fusion_strategy
        self._level = level
        self._protected_extractor = protected_extractor
        self._calls = 0
        self._dense_calls = 0
        self._sparse_calls = 0
        self._exact_calls = 0
        self._fusion_strategy_value = fusion_strategy

    def query(
        self, text: str, *, top_k: int = 50,
        dense_weight: float = 0.5, sparse_weight: float = 0.5,
        filters: object = None,
        query_features: QueryFeatures | None = None,
    ) -> Sequence[RetrievalHit]:
        self._calls += 1
        if top_k <= 0:
            raise HybridRetrievalError(
                f"top_k must be positive, got {top_k}"
            )
        if query_features is not None:
            return self._features_query(
                text, query_features, top_k, dense_weight, sparse_weight,
            )
        if self._identifier_detector(text):
            identifier = IDENTIFIER_PATTERN.search(text).group(1)
            self._exact_calls += 1
            return list(self._exact_lookup(identifier)) if self._exact_lookup else []
        if self._fusion_strategy == "rrf":
            return self._rrf_query(text, top_k, dense_weight, sparse_weight)
        if self._fusion_strategy == "linear":
            return self._linear_query(text, top_k, dense_weight, sparse_weight)
        raise HybridRetrievalError(
            f"unknown fusion_strategy: {self._fusion_strategy!r}"
        )

    def exact_id(
        self, identifier: str, *, filters: object = None,
    ) -> Sequence[RetrievalHit]:
        self._calls += 1
        self._exact_calls += 1
        if not self._exact_lookup:
            return []
        return list(self._exact_lookup(identifier))

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "dense_calls": self._dense_calls,
            "sparse_calls": self._sparse_calls,
            "exact_calls": self._exact_calls,
            "level": self._level,
        }

    # -- internal helpers --------------------------------------------------

    def _features_query(
        self, text: str, query_features: QueryFeatures, top_k: int,
        dense_weight: float, sparse_weight: float,
    ) -> list[RetrievalHit]:
        """Route a query through the explicit ``QueryFeatures`` contract.

        Pure-identifier queries (identifiers present, no free text)
        take the exact-only fast path. Identifier + free-text queries
        run the exact lookup for every identifier AND the semantic
        channels; exact hits are marked ``PROTECTED`` so they survive
        downstream selection. Queries without identifiers run the
        normal fusion path.
        """

        identifiers = tuple(query_features.identifiers)
        if identifiers and not query_features.has_free_text:
            self._exact_calls += 1
            if not self._exact_lookup:
                return []
            return list(self._exact_lookup(identifiers[0]))
        if identifiers and query_features.has_free_text:
            return self._mixed_identifier_query(
                text, query_features, identifiers, top_k,
                dense_weight, sparse_weight,
            )
        if self._fusion_strategy == "linear":
            return self._linear_query(text, top_k, dense_weight, sparse_weight)
        return self._rrf_query(text, top_k, dense_weight, sparse_weight)

    def _mixed_identifier_query(
        self, text: str, query_features: QueryFeatures,
        identifiers: tuple[str, ...], top_k: int,
        dense_weight: float, sparse_weight: float,
    ) -> list[RetrievalHit]:
        """Run exact lookup + dense + sparse for mixed queries.

        Exact hits are kept at the front of the result and marked
        ``PROTECTED`` (or by the configured ``protected_extractor``)
        so the exact candidate is never silently lost; the semantic
        channels run through the configured fusion strategy.
        """

        protected_ids: frozenset[str] | None = None
        if self._protected_extractor is not None:
            protected_ids = self._protected_extractor(query_features)
        exact_hits: list[RetrievalHit] = []
        if self._exact_lookup:
            for identifier in identifiers:
                self._exact_calls += 1
                for hit in self._exact_lookup(identifier):
                    if protected_ids is None:
                        hit = _replace_hit(
                            hit, score=hit.score, source=hit.source,
                            selection_state=SELECTION_STATE_PROTECTED,
                        )
                    exact_hits.append(hit)
        if self._fusion_strategy == "linear":
            fused = self._linear_query(
                text, top_k, dense_weight, sparse_weight,
            )
        else:
            fused = self._rrf_query(text, top_k, dense_weight, sparse_weight)
        seen = {hit.chunkId for hit in exact_hits}
        merged = list(exact_hits)
        for hit in fused:
            if hit.chunkId in seen:
                continue
            seen.add(hit.chunkId)
            merged.append(hit)
        if protected_ids is not None:
            merged = [
                _replace_hit(
                    hit, score=hit.score, source=hit.source,
                    selection_state=(
                        SELECTION_STATE_PROTECTED
                        if hit.chunkId in protected_ids else ""
                    ),
                )
                for hit in merged
            ]
        return merged[:top_k]

    def _rrf_query(
        self, text: str, top_k: int,
        dense_weight: float, sparse_weight: float,
    ) -> list[RetrievalHit]:
        self._dense_calls += 1
        dense_hits = list(self._dense_query(text, top_k))
        self._sparse_calls += 1
        sparse_hits = list(self._sparse_query(text, top_k))

        scored: dict[str, RetrievalHit] = {}
        rrf_scores: dict[str, float] = {}
        for rank, hit in enumerate(dense_hits, start=1):
            rrf_scores[hit.chunkId] = (
                rrf_scores.get(hit.chunkId, 0.0)
                + dense_weight * (1.0 / (RRF_K + rank))
            )
            scored.setdefault(hit.chunkId, hit)
        for rank, hit in enumerate(sparse_hits, start=1):
            rrf_scores[hit.chunkId] = (
                rrf_scores.get(hit.chunkId, 0.0)
                + sparse_weight * (1.0 / (RRF_K + rank))
            )
            existing = scored.get(hit.chunkId)
            if existing is None:
                scored[hit.chunkId] = hit
            elif existing.source == HIT_SOURCE_DENSE and hit.source != HIT_SOURCE_DENSE:
                scored[hit.chunkId] = hit

        ranked: list[RetrievalHit] = []
        for chunkId, score in sorted(
            rrf_scores.items(), key=lambda item: (-item[1], item[0]),
        ):
            base = scored[chunkId]
            in_dense = any(h.chunkId == chunkId for h in dense_hits)
            in_sparse = any(h.chunkId == chunkId for h in sparse_hits)
            if in_dense and in_sparse:
                source = HIT_SOURCE_HYBRID
            elif in_dense:
                source = HIT_SOURCE_DENSE
            else:
                source = HIT_SOURCE_SPARSE
            ranked.append(_replace_hit(base, score=min(max(score, 0.0), 1.0),
                                        source=source))
        return ranked[:top_k]

    def _linear_query(
        self, text: str, top_k: int,
        dense_weight: float, sparse_weight: float,
    ) -> list[RetrievalHit]:
        self._dense_calls += 1
        dense_hits = list(self._dense_query(text, top_k))
        self._sparse_calls += 1
        sparse_hits = list(self._sparse_query(text, top_k))
        scored: dict[str, RetrievalHit] = {}
        weights: dict[str, tuple[float, bool, bool]] = {}
        for hit in dense_hits:
            scored.setdefault(hit.chunkId, hit)
            weights.setdefault(
                hit.chunkId, (0.0, False, False),
            )
            cur = weights[hit.chunkId]
            weights[hit.chunkId] = (
                cur[0] + dense_weight * hit.score, True, cur[2],
            )
        for hit in sparse_hits:
            scored.setdefault(hit.chunkId, hit)
            cur = weights.get(hit.chunkId, (0.0, False, False))
            weights[hit.chunkId] = (
                cur[0] + sparse_weight * hit.score, cur[1], True,
            )
        ranked: list[RetrievalHit] = []
        for chunkId, (score, in_dense, in_sparse) in sorted(
            weights.items(), key=lambda item: (-item[1][0], item[0]),
        ):
            base = scored[chunkId]
            if in_dense and in_sparse:
                source = HIT_SOURCE_HYBRID
            elif in_dense:
                source = HIT_SOURCE_DENSE
            else:
                source = HIT_SOURCE_SPARSE
            ranked.append(_replace_hit(
                base, score=min(max(score, 0.0), 1.0), source=source,
            ))
        return ranked[:top_k]


def _replace_hit(
    hit: RetrievalHit, *, score: float, source: str,
    selection_state: str = "",
) -> RetrievalHit:
    return RetrievalHit(
        chunkId=hit.chunkId,
        score=score,
        source=source,
        snippet=hit.snippet,
        contentHash=hit.contentHash,
        metadata=hit.metadata,
        knowledgeState=hit.knowledgeState,
        tokenEstimate=hit.tokenEstimate,
        dropReason=hit.dropReason,
        evidenceWeight=hit.evidenceWeight,
        selection_state=selection_state,
        rerankScore=hit.rerankScore,
        rerankRank=hit.rerankRank,
    )


# Ensure the source constants are still considered used at runtime.
_ = (HIT_SOURCE_EXACT, HIT_SOURCE_DENSE, HIT_SOURCE_SPARSE, HIT_SOURCE_HYBRID)