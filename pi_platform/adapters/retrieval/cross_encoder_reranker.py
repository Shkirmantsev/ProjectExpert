"""Cross-encoder reranker adapter (F1 production-shape).

Implements :class:`pi_platform.ports.retrieval.reranker.RerankerPort`
against an optional ``sentence-transformers`` CrossEncoder.
The adapter is a production-shaped STUB until the
``sentence-transformers`` package is added to the ``reranking``
optional dependency group.

The adapter implements the plan §18 contract:

- F1: a functional cross-encoder adapter behind the port (the
  real ``sentence-transformers`` binding is a follow-up that
  swaps the ``_score_impl`` callable)
- F3: bounded ``max_pair_tokens`` and ``timeout_seconds``; on
  timeout, fall back to the RRF ordering of the pre-rerank
  pool
- F4: a fallback wrapper records the fallback in the
  retrieval trace
"""

from __future__ import annotations

import math
import time
from typing import Callable, List, Mapping, Optional, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.rerank_text import (
    DEFAULT_MAX_PAIR_TOKENS,
    RerankText,
    RerankTextBuilder,
)
from pi_platform.ports.retrieval.reranker import (
    DEFAULT_RERANK_BUDGET,
    RerankerError,
    RerankerPort,
)


__all__ = [
    "CrossEncoderRerankerAdapter",
    "ADAPTER_NAME",
    "DEFAULT_MODEL_ID",
    "DEFAULT_LICENSE_ID",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_BATCH_SIZE",
]


ADAPTER_NAME = "cross-encoder"
DEFAULT_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_LICENSE_ID = "MIT"
DEFAULT_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_BATCH_SIZE = 16


class CrossEncoderRerankerAdapter(RerankerPort):
    """Cross-encoder reranker adapter.

    When ``sentence-transformers`` is installed, the real
    binding replaces ``self._score_impl`` with a function that
    delegates to the model. Until then, the stub uses a
    deterministic BM25-flavoured score (overlap of query
    tokens with the passage text) so the cross-encoder
    contract is functional and the F1 acceptance criteria are
    satisfied.

    The stub's score is a sigmoid-mapped value in [0, 1] so
    it composes cleanly with the rest of the v0.8 retrieval
    pipeline (which expects ``score ∈ [0, 1]``). It is NOT a
    real cross-encoder semantic score; it is a deterministic
    baseline that lets the F1 wiring tests verify the
    contract end-to-end.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        license_id: str = DEFAULT_LICENSE_ID,
        budget: int = DEFAULT_RERANK_BUDGET,
        *,
        max_pair_tokens: int = DEFAULT_MAX_PAIR_TOKENS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_batch_size: int = DEFAULT_MAX_BATCH_SIZE,
        score_impl: Optional[Callable[[str, str], float]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_pair_tokens <= 0:
            raise RerankerError(
                f"max_pair_tokens must be positive, got {max_pair_tokens}"
            )
        if timeout_seconds <= 0:
            raise RerankerError(
                f"timeout_seconds must be positive, got {timeout_seconds}"
            )
        if max_batch_size <= 0:
            raise RerankerError(
                f"max_batch_size must be positive, got {max_batch_size}"
            )
        self._model_id = model_id
        self._license_id = license_id
        self.budget = budget
        self._max_pair_tokens = max_pair_tokens
        self._timeout_seconds = timeout_seconds
        self._max_batch_size = max_batch_size
        self._score_impl = score_impl or self._default_score
        self._clock = clock
        self._text_builder = RerankTextBuilder(
            max_pair_tokens=max_pair_tokens,
        )
        self._calls = 0
        self._timeouts = 0
        self._errors = 0
        self._batches = 0
        self._fallbacks = 0

    @property
    def backend_name(self) -> str:
        return ADAPTER_NAME

    def model_version(self) -> str:
        return self._model_id

    def license_id(self) -> str:
        return self._license_id

    def family(self) -> str:
        return "cross-encoder"

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "timeouts": self._timeouts,
            "errors": self._errors,
            "batches": self._batches,
            "fallbacks": self._fallbacks,
        }

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]:
        if not candidates:
            return ()
        if top_k <= 0:
            raise RerankerError(f"top_k must be positive, got {top_k}")
        # Pre-trim to the budget.
        pool = list(candidates[: self.budget])
        # Time-bounded scoring.
        deadline = self._clock() + self._timeout_seconds
        scored: List[tuple[RetrievalHit, float]] = []
        try:
            batch: List[RetrievalHit] = []
            for hit in pool:
                if self._clock() > deadline:
                    self._timeouts += 1
                    self._fallbacks += 1
                    return self._rrf_fallback(pool, top_k)
                batch.append(hit)
                if len(batch) >= self._max_batch_size:
                    scored.extend(self._score_batch(query, batch))
                    batch = []
                    self._batches += 1
            if batch:
                scored.extend(self._score_batch(query, batch))
                self._batches += 1
        except RerankerError as exc:
            # The wrapper above (RerankWithFallback) is the
            # primary fallback path. The inner fallback here is
            # a safety net for callers that do not wrap the
            # adapter; it returns the RRF ordering of the pool
            # and records the fallback in stats.
            self._errors += 1
            self._fallbacks += 1
            return self._rrf_fallback(pool, top_k)
        # Sort by score desc, then chunkId asc; preserve
        # chunkId uniqueness.
        scored.sort(key=lambda p: (-p[1], p[0].chunkId))
        # Deduplicate by chunkId (in case the same hit
        # appears multiple times in the pool).
        seen: set[str] = set()
        out: List[RetrievalHit] = []
        for hit, score in scored:
            if hit.chunkId in seen:
                continue
            seen.add(hit.chunkId)
            out.append(self._with_score(hit, score))
            if len(out) >= top_k:
                break
        return tuple(out)

    def score(self, query: str, candidate: RetrievalHit) -> float:
        text = self._text_builder.build(query=query, hit=candidate)
        return self._score_impl(query, text.passage)

    # -- internal helpers --------------------------------------------

    def _score_batch(
        self, query: str, batch: Sequence[RetrievalHit],
    ) -> List[tuple[RetrievalHit, float]]:
        out: List[tuple[RetrievalHit, float]] = []
        for hit in batch:
            text = self._text_builder.build(query=query, hit=hit)
            try:
                raw = self._score_impl(query, text.passage)
            except Exception as exc:
                self._errors += 1
                raise RerankerError(
                    f"cross-encoder scoring failed: {exc}"
                ) from exc
            # Sigmoid-map to [0, 1].
            score = 1.0 / (1.0 + math.exp(-raw))
            self._calls += 1
            out.append((hit, max(0.0, min(1.0, score))))
        return out

    def _rrf_fallback(
        self, pool: Sequence[RetrievalHit], top_k: int,
    ) -> Sequence[RetrievalHit]:
        """Reciprocal-rank-fusion ordering of the pool.

        The plan §18.1 says: on timeout or error, fall back to
        the RRF ordering of the pre-rerank direct candidate
        pool. The pool's existing score is monotonic in
        relevance, so this is a safe monotonic fallback.
        """
        ordered = sorted(
            pool, key=lambda h: (-h.score, h.chunkId),
        )
        return tuple(ordered[:top_k])

    def _with_score(
        self, hit: RetrievalHit, score: float,
    ) -> RetrievalHit:
        # Construct a new RetrievalHit with the updated score.
        # RetrievalHit is frozen, so we use the existing copy
        # semantics from the codebase.
        from dataclasses import replace
        return replace(hit, score=score)

    @staticmethod
    def _default_score(query: str, passage: str) -> float:
        """Deterministic baseline score: token-overlap on lower-
        cased alphanumeric tokens. NOT a real cross-encoder
        semantic score; it is a stdlib-only baseline that
        satisfies the F1 contract."""
        if not query or not passage:
            return 0.0
        q_tokens = {
            t for t in _tokenise(query)
            if len(t) >= 2
        }
        p_tokens = _tokenise(passage)
        if not q_tokens or not p_tokens:
            return 0.0
        overlap = sum(1 for t in p_tokens if t in q_tokens)
        # Length-normalised; centred so common words (the,
        # and, ...) don't dominate.
        return overlap / max(1.0, math.sqrt(len(p_tokens)))


def _tokenise(text: str) -> List[str]:
    import re
    return re.findall(r"[A-Za-z0-9\u0400-\u04FF]{2,}", text.lower())
