"""DenseIndex port for the v0.8 Phase 3 storage layer.

Covers architecture section §64 (Suggested Repository Layout — ANN
index), §28 (ANN Candidate Generation) and §17 (ANN Graphs vs
Knowledge Graphs).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence


__all__ = [
    "DenseIndexPort",
    "DenseIndexError",
    "DenseHit",
]


class DenseIndexError(RuntimeError):
    """Raised when a dense index cannot satisfy a request."""


@dataclass(frozen=True)
class DenseHit:
    chunkId: str
    score: float
    #: The chunk metadata the index stored with the vector. It is
    #: additive: an index MAY return an empty mapping. It lets a
    #: consumer recover facts that are only known at indexing time
    #: (for example that the chunk was embedded together with an
    #: image) without re-running the ingestion pipeline.
    metadata: Mapping[str, object] = field(default_factory=dict)


class DenseIndexPort(abc.ABC):
    """Abstract ANN / dense-vector index port."""

    @abc.abstractmethod
    def index_chunk(
        self, chunkId: str, vector: Sequence[float],
        metadata: Mapping[str, object],
    ) -> None: ...

    @abc.abstractmethod
    def delete_chunk(self, chunkId: str) -> None: ...

    @abc.abstractmethod
    def query(
        self, vector: Sequence[float], top_k: int = 10,
    ) -> Sequence[DenseHit]: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...