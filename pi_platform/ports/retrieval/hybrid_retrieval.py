"""Hybrid retrieval port for the v0.8 Phase 4 retrieval layer.

Covers architecture sections §26 (Sparse and Exact Retrieval), §27
(Hybrid Retrieval), §28 (ANN Candidate Generation) and the §33
retrieval-first agent access policy. The :class:`HybridRetrievalPort`
composes the Phase 3 :class:`pi_platform.ports.runtime.sparse_index.SparseIndexPort`,
:class:`pi_platform.ports.runtime.dense_index.DenseIndexPort` and
exact-identifier lookup into a single ranked candidate set.

The :class:`RetrievalHit` value type is the lingua-franca record
exchanged across every Phase 4 stage.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Final, Mapping, Sequence

from pi_platform.core.canonical.value_types import KnowledgeState, Metadata


__all__ = [
    "RetrievalHit",
    "HybridRetrievalPort",
    "HybridRetrievalError",
]


class HybridRetrievalError(RuntimeError):
    """Raised when hybrid retrieval cannot satisfy a request."""


HIT_SOURCE_DENSE = "dense"
HIT_SOURCE_SPARSE = "sparse"
HIT_SOURCE_EXACT = "exact"
HIT_SOURCE_HYBRID = "hybrid"
HIT_SOURCE_ALLOWED: Final = (HIT_SOURCE_DENSE, HIT_SOURCE_SPARSE,
                            HIT_SOURCE_EXACT, HIT_SOURCE_HYBRID)


@dataclass(frozen=True)
class RetrievalHit:
    """A single retrieval hit exchanged between Phase 4 stages."""

    chunkId: str
    score: float
    source: str
    snippet: str = ""
    contentHash: str = ""
    metadata: Metadata = field(
        default_factory=lambda: Metadata(
            documentId="", version="0.0.0", language="und",
        ),
    )
    knowledgeState: KnowledgeState = KnowledgeState.UNKNOWN
    tokenEstimate: int = 0
    dropReason: str = ""
    evidenceWeight: float = 1.0

    def __post_init__(self) -> None:
        if self.source not in HIT_SOURCE_ALLOWED:
            raise ValueError(
                f"RetrievalHit.source must be one of {HIT_SOURCE_ALLOWED}, "
                f"got {self.source!r}"
            )
        if not (0.0 <= self.score <= 1.0):
            raise ValueError(
                f"RetrievalHit.score must be in [0.0, 1.0], got {self.score}"
            )
        if self.tokenEstimate < 0:
            raise ValueError(
                f"RetrievalHit.tokenEstimate must be non-negative, got "
                f"{self.tokenEstimate}"
            )


class HybridRetrievalPort(abc.ABC):
    """Abstract hybrid-retrieval port."""

    @abc.abstractmethod
    def query(
        self, text: str, *, top_k: int = 50,
        dense_weight: float = 0.5, sparse_weight: float = 0.5,
        filters: object = None,
    ) -> Sequence[RetrievalHit]: ...

    @abc.abstractmethod
    def exact_id(
        self, identifier: str, *, filters: object = None,
    ) -> Sequence[RetrievalHit]: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...