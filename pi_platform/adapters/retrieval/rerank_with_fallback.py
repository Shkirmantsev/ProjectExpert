"""Rerank-with-fallback wrapper (F4).

Wraps a primary :class:`RerankerPort` (the cross-encoder or
Qwen3 adapter) and a fallback reranker (typically the
BM25-light core). On timeout or error from the primary, the
wrapper returns the fallback's RRF ordering of the pre-rerank
candidate pool. The fallback is recorded in the wrapper's
``stats()`` and surfaced through the retrieval trace.
"""

from __future__ import annotations

import time
from typing import Callable, Mapping, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.reranker import (
    RerankerError,
    RerankerPort,
)


__all__ = [
    "RerankWithFallback",
    "DEFAULT_FALLBACK_BUDGET",
]


DEFAULT_FALLBACK_BUDGET = 50


class RerankWithFallback(RerankerPort):
    """Wraps a primary reranker and a fallback reranker.

    The primary reranker is invoked first. If it raises
    :class:`RerankerError` (timeout or score error) or any
    unexpected exception, the wrapper catches it, increments
    the ``fallbacks`` counter, and delegates to the fallback.

    Both rerankers are bounded to ``budget`` candidates; the
    fallback's RRF ordering of the pool is the documented
    fallback path.
    """

    def __init__(
        self,
        primary: RerankerPort,
        fallback: RerankerPort,
        *,
        budget: int = DEFAULT_FALLBACK_BUDGET,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if primary is None:
            raise RerankerError("primary reranker is required")
        if fallback is None:
            raise RerankerError("fallback reranker is required")
        self._primary = primary
        self._fallback = fallback
        self.budget = budget
        self._clock = clock
        # Mirror the primary's timeouts.
        self._primary_timeout = getattr(
            primary, "_timeout_seconds", 8.0,
        )
        self._fallbacks = 0
        self._errors = 0
        self._primary_calls = 0
        self._fallback_calls = 0

    @property
    def primary(self) -> RerankerPort:
        return self._primary

    @property
    def fallback(self) -> RerankerPort:
        return self._fallback

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]:
        if not candidates:
            return ()
        if top_k <= 0:
            raise RerankerError(f"top_k must be positive, got {top_k}")
        pool = list(candidates[: self.budget])
        # Try the primary.
        try:
            self._primary_calls += 1
            result = self._primary.rerank(query, pool, top_k=top_k)
            return result
        except RerankerError:
            self._fallbacks += 1
        except Exception:
            self._fallbacks += 1
            self._errors += 1
        # Fallback: delegate to the fallback reranker.
        self._fallback_calls += 1
        return self._fallback.rerank(query, pool, top_k=top_k)

    def score(self, query: str, candidate: RetrievalHit) -> float:
        try:
            return self._primary.score(query, candidate)
        except RerankerError:
            self._fallbacks += 1
            return self._fallback.score(query, candidate)
        except Exception:
            self._fallbacks += 1
            self._errors += 1
            return self._fallback.score(query, candidate)

    def model_version(self) -> str:
        return self._primary.model_version()

    def license_id(self) -> str:
        return self._primary.license_id()

    def family(self) -> str:
        return f"{self._primary.family()}+fallback"

    def stats(self) -> Mapping[str, int]:
        primary_stats = self._primary.stats()
        fallback_stats = self._fallback.stats()
        out = {
            "primary_calls": self._primary_calls,
            "fallback_calls": self._fallback_calls,
            "fallbacks": self._fallbacks,
            "errors": self._errors,
            "primary_family": self._primary.family(),
            "fallback_family": self._fallback.family(),
        }
        for k, v in primary_stats.items():
            out[f"primary.{k}"] = v
        for k, v in fallback_stats.items():
            out[f"fallback.{k}"] = v
        return out
