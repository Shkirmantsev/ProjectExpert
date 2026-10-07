"""Default :class:`DenseIndexPort` implementation (in-process flat
search fallback).

The implementation keeps the embeddings in memory and computes cosine
similarity by brute force. The HNSW adapter is the future opt-in
backend; this implementation is the default that ships without an
extra dependency.
"""

from __future__ import annotations

import math
from typing import Dict, Mapping, Sequence, Tuple

from pi_platform.ports.runtime.dense_index import (
    DenseHit,
    DenseIndexError,
    DenseIndexPort,
)


__all__ = ["FlatDenseIndex"]


class FlatDenseIndex(DenseIndexPort):
    """In-process flat-search dense index."""

    def __init__(self):
        self._vectors: Dict[str, Sequence[float]] = {}
        self._metadata: Dict[str, Mapping[str, object]] = {}
        self._dim: int | None = None

    def _check_dimension(self, vector: Sequence[float]) -> None:
        if self._dim is None:
            return
        if len(vector) != self._dim:
            raise DenseIndexError(
                f"vector dimension {len(vector)} does not match stored dim "
                f"{self._dim}"
            )

    def index_chunk(
        self, chunkId: str, vector: Sequence[float],
        metadata: Mapping[str, object],
    ) -> None:
        self._check_dimension(vector)
        if self._dim is None and vector:
            self._dim = len(vector)
        self._vectors[chunkId] = tuple(float(v) for v in vector)
        self._metadata[chunkId] = dict(metadata)

    def delete_chunk(self, chunkId: str) -> None:
        self._vectors.pop(chunkId, None)
        self._metadata.pop(chunkId, None)
        if not self._vectors:
            self._dim = None

    def _cosine(self, a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def query(self, vector: Sequence[float], top_k: int = 10) -> Sequence[DenseHit]:
        if self._dim is not None and len(vector) != self._dim:
            raise DenseIndexError(
                f"vector dimension {len(vector)} does not match stored dim "
                f"{self._dim}"
            )
        scored: list[Tuple[str, float]] = []
        for chunk_id, stored in self._vectors.items():
            score = self._cosine(vector, stored)
            scored.append((chunk_id, score))
        scored.sort(key=lambda x: (-x[1], x[0]))
        return tuple(
            DenseHit(chunkId=cid, score=score)
            for cid, score in scored[:top_k]
            if score > 0
        )

    def stats(self) -> Mapping[str, int]:
        return {
            "vectors": len(self._vectors),
            "dim": self._dim or 0,
        }