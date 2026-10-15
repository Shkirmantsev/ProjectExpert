"""Vector record persistence port (Change Package C3).

Covers the ``embedding-execution-profile`` spec delta: the platform
persists embedding vectors through :class:`VectorRecordStorePort`
keyed by ``(chunk_id, embedding_profile_hash)`` so each profile owns
its own namespace and a disposable ANN index can always be rebuilt
from these records without re-embedding. Vectors are stored as raw
BLOBs (float32 little-endian preferred), never as JSON arrays;
serialization to/from the BLOB is the caller's responsibility via
:func:`encode_vector_payload` / :func:`decode_vector_payload` in the
SQLite adapter.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Iterable, Mapping


__all__ = [
    "VectorRecord",
    "VectorRecordStorePort",
    "VectorRecordStoreError",
]


class VectorRecordStoreError(RuntimeError):
    """Raised when a vector record store cannot satisfy a request."""


@dataclass(frozen=True)
class VectorRecord:
    """One persisted embedding vector for a chunk under one profile.

    ``created_at`` is stamped by the store at ``put()`` time (ISO 8601
    UTC) and is never taken from the caller.
    """

    chunk_id: str
    content_hash: str
    embedding_profile_hash: str
    model_revision: str
    dimension: int
    normalization: str
    vector_payload: bytes = field(repr=False)
    created_from_retrieval_text_hash: str
    created_at: str = ""


class VectorRecordStorePort(abc.ABC):
    """Abstract vector record store keyed by chunk + profile identity."""

    @abc.abstractmethod
    def put(self, record: VectorRecord) -> None:
        """Persist ``record``; a second ``put`` for the same
        ``(chunk_id, embedding_profile_hash)`` overwrites the row."""

    @abc.abstractmethod
    def get(
        self, chunk_id: str, embedding_profile_hash: str,
    ) -> VectorRecord | None:
        """Return the record or ``None`` when unknown."""

    @abc.abstractmethod
    def delete(self, chunk_id: str, embedding_profile_hash: str) -> None:
        """Delete the record; deleting an unknown key is a no-op."""

    @abc.abstractmethod
    def iter(self, embedding_profile_hash: str) -> Iterable[VectorRecord]:
        """Iterate all records under one profile namespace."""

    @abc.abstractmethod
    def profile_hash_for(self, chunk_id: str) -> str | None:
        """Return one profile hash the chunk is stored under, if any."""

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]:
        """Return ``{"records": N, "profile_hashes": M}``."""
