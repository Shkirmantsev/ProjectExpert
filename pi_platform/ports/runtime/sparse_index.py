"""SparseIndex port for the v0.8 Phase 3 storage layer.

Covers architecture section §63 (Durable Knowledge Save / Commit
Flow — durable metadata index) and §26 (Sparse and Exact Retrieval).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence


__all__ = [
    "SparseIndexPort",
    "SparseIndexError",
    "SparseHit",
]


class SparseIndexError(RuntimeError):
    """Raised when a sparse index cannot satisfy a request."""


@dataclass(frozen=True)
class SparseHit:
    documentId: str
    score: float
    snippet: Optional[str] = None


class SparseIndexPort(abc.ABC):
    """Abstract BM25-style sparse index port."""

    @abc.abstractmethod
    def index_document(
        self, family: str, documentId: str, text: str,
        metadata: Mapping[str, object],
    ) -> None: ...

    @abc.abstractmethod
    def delete_document(self, documentId: str) -> None: ...

    @abc.abstractmethod
    def query(
        self, text: str, top_k: int = 10,
        metadata: Optional[Mapping[str, object]] = None,
    ) -> Sequence[SparseHit]: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...