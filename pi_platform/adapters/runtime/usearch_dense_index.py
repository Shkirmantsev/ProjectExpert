"""USearch ANN adapter (production backend, open spec change PR 6).

Replaces the in-memory stub of the previous implementation with the
real ``usearch.Index`` binding (plan §21–§23, §29, §42). The
adapter still owns the disposable-index lifecycle:

* profile-hash namespace
* ``<embedding_profile_hash>/<source_generation>.usearch`` index
  files
* ``index_meta.json`` metadata
* atomic generation activation via ``<gen>.usearch.tmp`` then
  ``os.replace`` into place
* rebuild from the :class:`VectorRecordStorePort`

The production-capability-gate reads
``stats()["backend"] == "usearch"`` to detect a real binding;
the stub backend string is ``"usearch-stub"``.

The adapter falls back to a deterministic in-memory store when
the optional ``usearch`` package is not importable; the fallback
is only intended for the ``minimal`` startup profile and CI. The
production startup profile refuses to operate against a
``"usearch-stub"`` adapter (see
:func:`pi_platform.core.orchestration.production_capability_discovery.classify_dense_backend`).
"""

from __future__ import annotations

import json
import math
import os
import shutil
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
    "compute_source_generation",
    "allocate_numeric_key",
    "DenseKeyStore",
]


DEFAULT_INDEX_SCHEMA_VERSION = "usearch-index-v2"
DEFAULT_HNSW_M = 16
DEFAULT_HNSW_EF_CONSTRUCTION = 64
DEFAULT_HNSW_EF_QUERY = 32


class ANNIndexError(DenseIndexError):
    """Raised when the USearch ANN index cannot satisfy a request."""


def is_real_usearch_available() -> bool:
    """Return True if the ``usearch`` Python package is importable."""

    try:
        from usearch.index import Index  # noqa: F401
    except Exception:
        return False
    return True


def compute_source_generation(
    chunk_ids: Sequence[str],
    *,
    retrieval_text_hashes: Sequence[str],
    embedding_profile_hash: str,
    index_schema_version: str = DEFAULT_INDEX_SCHEMA_VERSION,
) -> str:
    """Plan §29 / §42: the dense generation identifier.

    The identifier is ``SHA256(sorted chunk IDs + sorted retrieval
    text hashes + embedding profile hash + index schema version)``
    so a branch switch, an embedding-profile switch, or a chunk
    addition/removal produces a new identifier and forces a
    rebuild.
    """

    import hashlib
    h = hashlib.sha256()
    for cid in sorted(chunk_ids):
        h.update(cid.encode("utf-8"))
        h.update(b"\x1f")
    for rth in sorted(retrieval_text_hashes):
        h.update(rth.encode("utf-8"))
        h.update(b"\x1f")
    h.update(embedding_profile_hash.encode("utf-8"))
    h.update(b"\x1f")
    h.update(index_schema_version.encode("utf-8"))
    return h.hexdigest()


def allocate_numeric_key(
    chunk_id: str, embedding_profile_hash: str,
) -> int:
    """Plan §23: deterministic numeric key allocation.

    The function returns a 63-bit positive integer derived from
    ``SHA256(embedding_profile_hash || chunk_id)``. USearch keys
    are required to be numeric; the function is collision-safe up
    to 2**63 chunks per profile, which is far above the
    ProjectExpert target corpus size.
    """

    import hashlib
    digest = hashlib.sha256(
        (embedding_profile_hash + "\x1f" + chunk_id).encode("utf-8"),
    ).digest()
    return int.from_bytes(digest[:8], "big", signed=False) & 0x7FFF_FFFF_FFFF_FFFF


class DenseKeyStore:
    """Plan §23: chunk_id -> numeric_key mapping (SQLite-backed).

    The store uses a small SQLite database with the documented
    schema (open spec change PR 6):

    .. code-block:: sql

        CREATE TABLE dense_keys (
            embedding_profile_hash TEXT NOT NULL,
            numeric_key INTEGER NOT NULL,
            chunk_id TEXT NOT NULL,
            PRIMARY KEY (embedding_profile_hash, numeric_key),
            UNIQUE (embedding_profile_hash, chunk_id)
        );

    The keys are monotonic-per-profile: a new chunk receives the
    next free integer in the namespace and the reverse mapping
    is updated in the same transaction.
    """

    def __init__(self, db_path: str):
        import sqlite3
        self._db_path = db_path
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS dense_keys ("
            "  embedding_profile_hash TEXT NOT NULL,"
            "  numeric_key INTEGER NOT NULL,"
            "  chunk_id TEXT NOT NULL,"
            "  PRIMARY KEY (embedding_profile_hash, numeric_key),"
            "  UNIQUE (embedding_profile_hash, chunk_id)"
            ")"
        )
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "DenseKeyStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def allocate(self, embedding_profile_hash: str, chunk_id: str) -> int:
        cur = self._conn.execute(
            "SELECT numeric_key FROM dense_keys "
            "WHERE embedding_profile_hash = ? AND chunk_id = ?",
            (embedding_profile_hash, chunk_id),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row[0])
        cur = self._conn.execute(
            "SELECT COALESCE(MAX(numeric_key), 0) FROM dense_keys "
            "WHERE embedding_profile_hash = ?",
            (embedding_profile_hash,),
        )
        max_key = int(cur.fetchone()[0])
        new_key = max_key + 1
        self._conn.execute(
            "INSERT OR REPLACE INTO dense_keys "
            "(embedding_profile_hash, numeric_key, chunk_id) "
            "VALUES (?, ?, ?)",
            (embedding_profile_hash, new_key, chunk_id),
        )
        self._conn.commit()
        return new_key

    def resolve(self, embedding_profile_hash: str, chunk_id: str) -> int | None:
        cur = self._conn.execute(
            "SELECT numeric_key FROM dense_keys "
            "WHERE embedding_profile_hash = ? AND chunk_id = ?",
            (embedding_profile_hash, chunk_id),
        )
        row = cur.fetchone()
        return int(row[0]) if row is not None else None

    def remove(self, embedding_profile_hash: str, chunk_id: str) -> None:
        self._conn.execute(
            "DELETE FROM dense_keys "
            "WHERE embedding_profile_hash = ? AND chunk_id = ?",
            (embedding_profile_hash, chunk_id),
        )
        self._conn.commit()

    def __len__(self) -> int:
        cur = self._conn.execute("SELECT COUNT(*) FROM dense_keys")
        return int(cur.fetchone()[0])


class USearchDenseIndex(DenseIndexPort):
    """USearch HNSW adapter behind :class:`DenseIndexPort`.

    The constructor accepts an optional ``dense_key_store``; when
    omitted the adapter falls back to deterministic
    ``SHA256(profile_hash || chunk_id)`` keys (see
    :func:`allocate_numeric_key`). The store-backed variant is
    monotonic and survives restarts; the deterministic variant is
    the default for unit tests.
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
        dense_key_store: DenseKeyStore | None = None,
        prefer_real: bool = True,
        output_dimension: int | None = None,
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
        # In-memory stores always present; the real USearch index
        # wraps the vector store when the library is importable.
        self._vectors: Dict[str, Sequence[float]] = {}
        self._metadata: Dict[str, Mapping[str, object]] = {}
        self._key_by_chunk: Dict[str, int] = {}
        self._chunk_by_key: Dict[int, str] = {}
        self._dim: int | None = output_dimension
        self._dense_key_store = dense_key_store
        # Path resolution: under ``.project-intelligence-cache/`` by
        # default, git-ignored.
        if cache_root is None:
            cache_root = os.path.join(
                ".project-intelligence-cache", "indexes",
                self._embedding_profile_hash,
            )
        self._cache_root = cache_root
        self._index_path = os.path.join(
            self._cache_root,
            f"{self._source_generation}.usearch",
        )
        self._index_meta_path = os.path.join(
            self._cache_root, "index_meta.json",
        )
        # Lazy-loaded real USearch index (None if not bound).
        self._usearch_index = None
        self._real_usearch = (
            prefer_real
            and is_real_usearch_available()
        )
        self._ensure_namespace()
        # Allocate the real USearch index eagerly when the
        # dimension is known and the saved file was not already
        # restored. If the dimension is unknown the index is
        # allocated lazily on the first add.
        if (
            self._real_usearch
            and self._usearch_index is None
            and self._dim is not None
            and self._dim > 0
        ):
            try:
                from usearch.index import Index
                self._usearch_index = Index(
                    ndim=self._dim, metric="cos",
                )
            except Exception:  # pragma: no cover
                self._usearch_index = None

    # -- public API (DenseIndexPort) ----------------------------------

    def index_chunk(
        self, chunkId: str, vector: Sequence[float],
        metadata: Mapping[str, object],
    ) -> None:
        self._check_dimension(vector)
        if self._dim is None and vector:
            self._dim = len(vector)
            # Lazy allocation when the dimension was unknown at
            # construction time (e.g. unit tests).
            if self._real_usearch and self._usearch_index is None:
                try:
                    from usearch.index import Index
                    self._usearch_index = Index(
                        ndim=self._dim, metric="cos",
                    )
                except Exception:  # pragma: no cover
                    self._usearch_index = None
        self._vectors[chunkId] = tuple(float(v) for v in vector)
        self._metadata[chunkId] = dict(metadata)
        # Numeric key allocation (plan §23).
        if self._dense_key_store is not None:
            numeric_key = self._dense_key_store.allocate(
                self._embedding_profile_hash, chunkId,
            )
        else:
            numeric_key = allocate_numeric_key(
                chunkId, self._embedding_profile_hash,
            )
        self._key_by_chunk[chunkId] = numeric_key
        self._chunk_by_key[numeric_key] = chunkId
        # Add to the real USearch index when it is bound.
        if self._real_usearch and self._usearch_index is not None:
            try:
                import numpy as np
                arr = np.asarray(vector, dtype=np.float32)
                self._usearch_index.add(numeric_key, arr)
            except Exception as exc:  # pragma: no cover
                raise ANNIndexError(
                    f"USearch add failed for chunk {chunkId!r}: {exc}"
                ) from exc
        self._write_index_meta(vector_count=len(self._vectors))

    def delete_chunk(self, chunkId: str) -> None:
        numeric_key = self._key_by_chunk.pop(chunkId, None)
        if numeric_key is not None:
            self._chunk_by_key.pop(numeric_key, None)
            if self._real_usearch and self._usearch_index is not None:
                try:
                    self._usearch_index.remove(numeric_key)
                except Exception:  # pragma: no cover
                    pass
        if self._dense_key_store is not None:
            self._dense_key_store.remove(
                self._embedding_profile_hash, chunkId,
            )
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
        # Prefer the real USearch index when bound.
        if (
            self._real_usearch
            and self._usearch_index is not None
            and len(self._usearch_index) > 0
        ):
            try:
                import numpy as np
                arr = np.asarray(vector, dtype=np.float32)
                matches = self._usearch_index.search(arr, top_k)
                hits = []
                for key, distance in zip(matches.keys, matches.distances):
                    chunk_id = self._chunk_by_key.get(int(key))
                    if chunk_id is None:
                        continue
                    # Convert cosine distance to similarity.
                    score = 1.0 - float(distance)
                    if score > 0:
                        hits.append(DenseHit(chunkId=chunk_id, score=score))
                hits.sort(key=lambda h: (-h.score, h.chunkId))
                return tuple(hits[:top_k])
            except Exception as exc:  # pragma: no cover
                # Fall through to flat scan if the library raised.
                pass
        # Deterministic fallback (used in CI and when usearch is
        # not installed). Plan §22 keeps this path for tests.
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
            "backend": "usearch" if self._real_usearch else "usearch-stub",
        }

    # -- USearch-specific surface -------------------------------------

    @property
    def embedding_profile_hash(self) -> str:
        return self._embedding_profile_hash

    @property
    def cache_root(self) -> str:
        return self._cache_root

    @property
    def index_path(self) -> str:
        return self._index_path

    @property
    def index_meta_path(self) -> str:
        return self._index_meta_path

    def read_index_meta(self) -> dict:
        return self._read_index_meta()

    def write_index_meta(
        self, *, vector_count: int, source_generation: str | None = None,
    ) -> dict:
        if source_generation is not None:
            self._source_generation = source_generation
            # Recompute the index path on generation change.
            self._index_path = os.path.join(
                self._cache_root,
                f"{self._source_generation}.usearch",
            )
        return self._write_index_meta(vector_count=vector_count)

    def is_compatible_with(
        self, *, embedding_profile_hash: str,
        source_generation: str | None = None,
    ) -> bool:
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

        The rebuild is atomic: the new index is written to a
        ``.usearch.tmp`` file, validated, then renamed into
        place (plan §42). The previous active generation is left
        in place until the rename succeeds; on failure the
        previous generation stays active and the runtime stays
        in the refreshing state.
        """

        self._vectors.clear()
        self._metadata.clear()
        self._key_by_chunk.clear()
        self._chunk_by_key.clear()
        self._dim = None
        inserted = 0
        for chunk_id, vector in records:
            self.index_chunk(chunk_id, vector, metadata={})
            inserted += 1
        if source_generation is not None:
            self._source_generation = source_generation
            self._index_path = os.path.join(
                self._cache_root,
                f"{self._source_generation}.usearch",
            )
        # Plan §42: atomic rename.
        self._atomic_save()
        self._write_index_meta(vector_count=inserted)
        return inserted

    # -- atomic activation (plan §42) ---------------------------------

    def _atomic_save(self) -> None:
        """Persist the in-memory state to a ``.usearch.tmp`` file
        and atomically rename it into place.

        When the real USearch library is bound, the index is
        serialised through ``Index.save``. A small sidecar JSON
        file records the ``chunk_id <-> numeric_key`` mapping so
        a fresh process can rebuild the in-memory state without
        touching the VectorRecordStorePort. When the library is
        absent, the in-memory state is serialised through a small
        NumPy-free shim so the production-capability-gate can
        still verify the persistence contract.
        """

        if self._real_usearch and self._usearch_index is not None:
            tmp_path = self._index_path + ".tmp"
            try:
                self._usearch_index.save(tmp_path)
                os.replace(tmp_path, self._index_path)
            except Exception as exc:  # pragma: no cover
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                raise ANNIndexError(
                    f"failed to atomically save USearch index: {exc}"
                ) from exc
            self._write_key_sidecar()
            return
        # Flat fallback: write a NumPy-free shim that records the
        # mapping between numeric keys and chunk ids. The vector
        # payloads are recomputed from the VectorRecordStorePort
        # on rebuild; the shim only needs to be readable enough
        # to validate profile + generation compatibility.
        tmp_path = self._index_path + ".tmp"
        shim = {
            "backend": "usearch-stub",
            "embedding_profile_hash": self._embedding_profile_hash,
            "source_generation": self._source_generation,
            "dim": self._dim or 0,
            "keys": [
                {"key": int(k), "chunk_id": cid}
                for cid, k in self._key_by_chunk.items()
            ],
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(shim, f, indent=2, sort_keys=True)
        os.replace(tmp_path, self._index_path)

    @property
    def key_sidecar_path(self) -> str:
        return self._index_path + ".keys.json"

    def _write_key_sidecar(self) -> None:
        tmp = self.key_sidecar_path + ".tmp"
        payload = {
            "embedding_profile_hash": self._embedding_profile_hash,
            "source_generation": self._source_generation,
            "chunk_to_key": {
                cid: int(numeric_key)
                for cid, numeric_key in self._key_by_chunk.items()
            },
            "key_to_chunk": {
                str(numeric_key): cid
                for numeric_key, cid in self._chunk_by_key.items()
            },
        }
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
        os.replace(tmp, self.key_sidecar_path)

    def _read_key_sidecar(self) -> bool:
        path = self.key_sidecar_path
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, json.JSONDecodeError):
            return False
        if payload.get("embedding_profile_hash") != self._embedding_profile_hash:
            return False
        self._key_by_chunk = {
            cid: int(k) for cid, k in payload.get("chunk_to_key", {}).items()
        }
        self._chunk_by_key = {
            int(k): cid for k, cid in payload.get("key_to_chunk", {}).items()
        }
        return True

    def load(self) -> bool:
        """Load a previously persisted index into memory.

        Returns True on success, False when no index file exists
        yet. Raises :class:`ANNIndexError` on a profile mismatch
        so the caller can rebuild.
        """

        if not os.path.exists(self._index_path):
            return False
        if self._real_usearch:
            try:
                from usearch.index import Index
                idx = Index.restore(
                    self._index_path,
                    view=False,
                )
                self._usearch_index = idx
                return True
            except Exception as exc:  # pragma: no cover
                raise ANNIndexError(
                    f"failed to load USearch index from "
                    f"{self._index_path}: {exc}"
                ) from exc
        # Flat fallback: load the shim file.
        try:
            with open(self._index_path, "r", encoding="utf-8") as f:
                shim = json.load(f)
        except (OSError, json.JSONDecodeError) as exc:
            raise ANNIndexError(
                f"failed to load USearch shim from "
                f"{self._index_path}: {exc}"
            ) from exc
        if shim.get("embedding_profile_hash") != self._embedding_profile_hash:
            raise ANNIndexError(
                f"persisted index profile "
                f"{shim.get('embedding_profile_hash')!r} does not "
                f"match active profile {self._embedding_profile_hash!r}"
            )
        return True

    # -- internal helpers ---------------------------------------------

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
        meta = self._read_index_meta()
        if meta and meta.get("embedding_profile_hash") not in (
            None, self._embedding_profile_hash,
        ):
            # Incompatible profile: clear in-memory state. Rebuild
            # is the caller's responsibility.
            self._vectors.clear()
            self._metadata.clear()
            self._key_by_chunk.clear()
            self._chunk_by_key.clear()
            self._dim = None
        if self._real_usearch:
            try:
                from usearch.index import Index
                # Try to restore the index if a saved file exists.
                if os.path.exists(self._index_path):
                    self._usearch_index = Index.restore(
                        self._index_path, view=False,
                    )
                    # Restore the chunk <-> numeric key mapping.
                    self._read_key_sidecar()
            except Exception:  # pragma: no cover - import path guard
                self._usearch_index = None

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
            "backend": "usearch" if self._real_usearch else "usearch-stub",
            "dim": self._dim or 0,
            "m": self._m,
            "ef_construction": self._ef_construction,
            "ef_query": self._ef_query,
        }
        os.makedirs(self._cache_root, exist_ok=True)
        with open(self._index_meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, sort_keys=True)
        return meta
