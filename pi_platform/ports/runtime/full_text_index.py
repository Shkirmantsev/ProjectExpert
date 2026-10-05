"""FullTextIndex port for the v0.8 Phase 3 storage layer.

Covers architecture section §65 (License-Aware Configuration Example
— durable secondary text index) and §26 (Sparse and Exact Retrieval
— exact identifier lookup).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence


__all__ = [
    "FullTextIndexPort",
    "FullTextIndexError",
    "FullTextHit",
]


class FullTextIndexError(RuntimeError):
    """Raised when a full-text index cannot satisfy a request."""


@dataclass(frozen=True)
class FullTextHit:
    documentId: str
    score: float
    snippet: Optional[str] = None


class FullTextIndexPort(abc.ABC):
    """Abstract secondary full-text index port."""

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
    ) -> Sequence[FullTextHit]: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...