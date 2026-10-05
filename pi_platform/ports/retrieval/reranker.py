"""Reranker port for the v0.8 Phase 4 retrieval layer.

Covers architecture section §30 (Optional Advanced Reranking). The
:class:`RerankerPort` exposes the cross-encoder default, the BM25-
light fallback and the optional ColBERT-style adapter behind a
single pluggable surface that the multi-stage retrieval pipeline
invokes on the bounded candidate set produced by the candidate
generation, fusion, metadata filter and graph/hierarchy expansion
stages.

Rerankers operate on bounded candidate sets only. The pipeline
MUST enforce a :attr:`RerankerPort.budget` cap so a runaway
candidate set never reaches the reranker.
"""

from __future__ import annotations

import abc
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit


__all__ = [
    "RerankerPort",
    "RerankerError",
]


class RerankerError(RuntimeError):
    """Raised when a reranker cannot satisfy a request."""


# Maximum candidates a reranker is allowed to see in a single call.
# The multi-stage pipeline MUST pre-trim its candidate set to this
# budget before calling :meth:`RerankerPort.rerank`.
DEFAULT_RERANK_BUDGET = 50


class RerankerPort(abc.ABC):
    """Abstract pluggable reranker port."""

    #: Default candidate budget for the multi-stage pipeline.
    budget: int = DEFAULT_RERANK_BUDGET

    @abc.abstractmethod
    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]: ...

    @abc.abstractmethod
    def score(
        self, query: str, candidate: RetrievalHit,
    ) -> float: ...

    @abc.abstractmethod
    def model_version(self) -> str: ...

    @abc.abstractmethod
    def license_id(self) -> str: ...

    @abc.abstractmethod
    def family(self) -> str: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...