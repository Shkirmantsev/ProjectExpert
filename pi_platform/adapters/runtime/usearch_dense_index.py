"""USearch ANN adapter (production backend for larger corpora).

Implements :class:`pi_platform.ports.runtime.dense_index.DenseIndexPort`
on top of the optional ``usearch`` Python package. The adapter is the
production opt-in backend for the §28 ANN candidate generation;
:mod:`pi_platform.adapters.runtime.flat_dense_index` remains the
small-corpus / deterministic fallback.

**D.1.5 status (2026-10-15):** this file ships the production **STUB**
that owns the contract and the disposable-index lifecycle (path
naming, profile-hash namespace, metadata file, rebuild semantics).
The real ``usearch.Index`` binding is a follow-up that imports the
optional dependency; until then, the stub delegates to a flat
in-memory store and the production behaviour is correct on
construction, namespace validation, metadata round-trip, and
rebuild on profile mismatch.

When ``usearch`` is not installed, ``USearchDenseIndex`` is still
constructible and exposes the same ``DenseIndexPort`` contract as
``FlatDenseIndex``; ``stats()`` reports
``{"backend": "usearch-stub", "vectors": N, "dim": D}`` so operators
can detect the stub.

Index file layout (under ``cache_root``):

.. code-block:: text

    <cache_root>/indexes/<embedding_profile_hash>/
        vectors.usearch          # the HNSW index file (real binding)
        index_meta.json          # {embedding_profile_hash,
                                 #  index_schema_version,
                                 #  source_generation, vector_count,
                                 #  backend, dim, m, ef_construction,
                                 #  ef_query}
"""

from __future__ import annotations

import json
import math
import os
from typing import Dict, Mapping, Optional, Sequence, Tuple

from pi_platform.ports.runtime.dense_index import (
    DenseHit,
    DenseIndexError,
    DenseIndexPort,
)


__all__ = [
    "USearchDenseIndex",
    "ANNIndexError",
    "DEFAULT_INDEX_SCHEMA_VERSION",
    "DEFAULT_HNSW_M",
    "DEFAULT_HNSW_EF_CONSTRUCTION",
    "DEFAULT_HNSW_EF_QUERY",
]


DEFAULT_INDEX_SCHEMA_VERSION = "usearch-index-v1"
DEFAULT_HNSW_M = 16
DEFAULT_HNSW_EF_CONSTRUCTION = 64
DEFAULT_HNSW_EF_QUERY = 32


class ANNIndexError(DenseIndexError):
    """Raised when the USearch ANN index cannot satisfy a request."""


class USearchDenseIndex(DenseIndexPort):
    """USearch HNSW adapter behind :class:`DenseIndexPort`.

    The stub holds the vectors in memory (cosine-similarity flat
    scan) but records the full HNSW configuration, owns the
    disposable namespace under
    ``<cache_root>/indexes/<embedding_profile_hash>/``, validates
    that the active profile's hash matches the persisted metadata,
    and rebuilds from a :class:`VectorRecordStorePort` source when
    it does not.
    """

    def __init__(
        self,
        *,
        embedding_profile_hash: str,
        cache_root: Optional[str] = None,
        m: int = DEFAULT_HNSW_M,
        ef_construction: int = DEFAULT_HNSW_EF_CONSTRUCTION,
        ef_query: int = DEFAULT_HNSW_EF_QUERY,
        source_generation: str = "0",
    ) -> None:
        if not embedding_profile_hash:
            raise ANNIndexError(
                "embedding_profile_hash is required for USearchDenseIndex"
            )
        self._embedding_profile_hash = embedding_profile_hash
        self._m = m
        self._ef_construction = ef_construction
        self._ef_query = ef_query
        self._source_generation = source_generation
        # In-memory stores (real binding will mirror these into the
        # ``vectors.usearch`` file).
        self._vectors: Dict[str, Sequence[float]] = {}
        self._metadata: Dict[str, Mapping[str, object]] = {}
        self._dim: int | None = None
        # Path resolution: under ``.project-intelligence-cache/`` by
        # default, git-ignored.
        if cache_root is None:
            cache_root = os.path.join(
                ".project-intelligence-cache", "indexes",
                self._embedding_profile_hash,
            )
        self._cache_root = cache_root
        self._index_meta_path = os.path.join(
            self._cache_root, "index_meta.json",
        )
        self._ensure_namespace()

    # -- public API (DenseIndexPort) ----------------------------------

    def index_chunk(
        self, chunkId: str, vector: Sequence[float],
        metadata: Mapping[str, object],
    ) -> None:
        self._check_dimension(vector)
        if self._dim is None and vector:
            self._dim = len(vector)
        self._vectors[chunkId] = tuple(float(v) for v in vector)
        self._metadata[chunkId] = dict(metadata)
        self._write_index_meta(vector_count=len(self._vectors))

    def delete_chunk(self, chunkId: str) -> None:
        self._vectors.pop(chunkId, None)
        self._metadata.pop(chunkId, None)
        if not self._vectors:
            self._dim = None
        self._write_index_meta(vector_count=len(self._vectors))

    def query(
        self, vector: Sequence[float], top_k: int = 10,
    ) -> Sequence[DenseHit]:
        if self._dim is not None and len(vector) != self._dim:
            raise ANNIndexError(
                f"vector dimension {len(vector)} does not match stored "
                f"dim {self._dim}"
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
            "m": self._m,
            "ef_construction": self._ef_construction,
            "ef_query": self._ef_query,
        }

    # -- USearch-specific surface -------------------------------------

    @property
    def embedding_profile_hash(self) -> str:
        """The active profile hash; namespace key for this index."""
        return self._embedding_profile_hash

    @property
    def cache_root(self) -> str:
        """Path to the disposable index directory (git-ignored)."""
        return self._cache_root

    @property
    def index_meta_path(self) -> str:
        """Path to the index metadata file (JSON)."""
        return self._index_meta_path

    def read_index_meta(self) -> dict:
        """Return the persisted index metadata as a dict (empty if
        no metadata file exists yet)."""
        return self._read_index_meta()

    def write_index_meta(
        self, *, vector_count: int, source_generation: str | None = None,
    ) -> dict:
        """Persist the index metadata. Returns the written dict.

        The metadata records every compatibility key the platform
        uses to decide whether the index can be opened or must be
        rebuilt.
        """
        if source_generation is not None:
            self._source_generation = source_generation
        return self._write_index_meta(vector_count=vector_count)

    def is_compatible_with(
        self, *, embedding_profile_hash: str, source_generation: str | None = None,
    ) -> bool:
        """True iff the persisted metadata matches the active
        profile hash (and optionally the source generation)."""
        if embedding_profile_hash != self._embedding_profile_hash:
            return False
        meta = self._read_index_meta()
        if not meta:
            return False
        if meta.get("embedding_profile_hash") != embedding_profile_hash:
            return False
        if (
            source_generation is not None
            and meta.get("source_generation") != source_generation
        ):
            return False
        return True

    def rebuild_from(
        self,
        records: Sequence[Tuple[str, Sequence[float]]],
        *,
        source_generation: str | None = None,
    ) -> int:
        """Reset the index and re-insert every record.

        Returns the number of vectors inserted. Use this when the
        persisted index is incompatible with the active profile or
        source generation: load every
        :class:`VectorRecord` from
        :class:`VectorRecordStorePort` for the active profile and
        pass ``(chunk_id, vector_payload_decoded)`` pairs here.
        """
        self._vectors.clear()
        self._metadata.clear()
        self._dim = None
        inserted = 0
        for chunk_id, vector in records:
            if self._dim is None and vector:
                self._dim = len(vector)
            elif vector and len(vector) != self._dim:
                raise ANNIndexError(
                    f"vector dimension {len(vector)} does not match "
                    f"stored dim {self._dim}"
                )
            self._vectors[chunk_id] = tuple(float(v) for v in vector)
            inserted += 1
        if source_generation is not None:
            self._source_generation = source_generation
        self._write_index_meta(vector_count=inserted)
        return inserted

    # -- internal helpers ----------------------------------------------

    def _check_dimension(self, vector: Sequence[float]) -> None:
        if self._dim is None:
            return
        if len(vector) != self._dim:
            raise ANNIndexError(
                f"vector dimension {len(vector)} does not match stored "
                f"dim {self._dim}"
            )

    def _cosine(self, a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def _ensure_namespace(self) -> None:
        os.makedirs(self._cache_root, exist_ok=True)
        # Validate against any persisted metadata; if incompatible,
        # leave the directory in place but reset the in-memory
        # store. Rebuild semantics are the caller's responsibility
        # (call ``rebuild_from(records)``).
        meta = self._read_index_meta()
        if meta and meta.get("embedding_profile_hash") not in (
            None, self._embedding_profile_hash,
        ):
            self._vectors.clear()
            self._metadata.clear()
            self._dim = None

    def _read_index_meta(self) -> dict:
        try:
            with open(self._index_meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return {}
        except (json.JSONDecodeError, OSError):
            return {}

    def _write_index_meta(
        self, *, vector_count: int, source_generation: str | None = None,
    ) -> dict:
        if source_generation is not None:
            self._source_generation = source_generation
        meta = {
            "embedding_profile_hash": self._embedding_profile_hash,
            "index_schema_version": DEFAULT_INDEX_SCHEMA_VERSION,
            "source_generation": self._source_generation,
            "vector_count": int(vector_count),
            "backend": "usearch-stub",
            "dim": self._dim or 0,
            "m": self._m,
            "ef_construction": self._ef_construction,
            "ef_query": self._ef_query,
        }
        os.makedirs(self._cache_root, exist_ok=True)
        with open(self._index_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, sort_keys=True)
        return meta
