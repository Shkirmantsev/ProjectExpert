"""SQLite :class:`VectorRecordStorePort` implementation (Change Package C3).

Stores embedding vectors as raw BLOBs in a single additive
``embeddings`` table keyed by ``(chunk_id,
embedding_profile_hash)``. The table is created by the idempotent
additive migration :func:`migration_v2_add_embeddings_table` (the
v1 → v2 knowledge-schema migration narrative); existing rows in the
same database file are never rewritten.
:meth:`SqliteVectorRecordStore.put` overwrites on duplicate keys — the
simpler contract for the disposable ANN rebuild pattern.

Vector serialization is the caller's responsibility: convert a list
of floats to the BLOB with :func:`encode_vector_payload` (float32
``"f"`` preferred, float64 ``"d"`` supported). The adapter does not
commit; the caller that owns the connection owns the transaction.
"""

from __future__ import annotations

import array
import datetime as _dt
import sqlite3
from typing import Callable, Iterable, Mapping, Sequence

from pi_platform.ports.runtime.vector_record_store import (
    VectorRecord,
    VectorRecordStoreError,
    VectorRecordStorePort,
)


__all__ = [
    "SqliteVectorRecordStore",
    "migration_v2_add_embeddings_table",
    "encode_vector_payload",
    "decode_vector_payload",
]


_DTYPE_CODES = {"f": ("f", 4), "d": ("d", 8)}


def _default_clock() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def encode_vector_payload(
    vector: Sequence[float], *, dtype: str = "f",
) -> bytes:
    """Encode ``vector`` as a raw little-endian float array BLOB.

    ``dtype="f"`` (float32) is the preferred on-disk format;
    ``dtype="d"`` (float64) is supported for callers that need
    exact double round-trips. Never emits JSON.
    """

    try:
        typecode, _width = _DTYPE_CODES[dtype]
    except KeyError:
        raise VectorRecordStoreError(
            f"unsupported vector dtype {dtype!r}; use 'f' or 'd'"
        ) from None
    return array.array(typecode, vector).tobytes()


def decode_vector_payload(blob: bytes, *, dtype: str = "f") -> list[float]:
    """Decode a BLOB produced by :func:`encode_vector_payload`."""

    try:
        typecode, _width = _DTYPE_CODES[dtype]
    except KeyError:
        raise VectorRecordStoreError(
            f"unsupported vector dtype {dtype!r}; use 'f' or 'd'"
        ) from None
    values = array.array(typecode)
    if len(blob) % _width != 0:
        raise VectorRecordStoreError(
            f"vector payload length {len(blob)} is not a multiple of "
            f"{_width} for dtype {dtype!r}"
        )
    values.frombytes(blob)
    return list(values)


def migration_v2_add_embeddings_table(db: sqlite3.Connection) -> None:
    """Additive v1 → v2 migration: create the ``embeddings`` table.

    Idempotent (``IF NOT EXISTS``); existing tables and rows are
    never rewritten.
    """

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS embeddings (
            chunk_id TEXT NOT NULL,
            embedding_profile_hash TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            model_revision TEXT NOT NULL,
            dimension INTEGER NOT NULL,
            normalization TEXT NOT NULL,
            vector_payload BLOB NOT NULL,
            created_from_retrieval_text_hash TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (chunk_id, embedding_profile_hash)
        )
        """
    )


class SqliteVectorRecordStore(VectorRecordStorePort):
    """Default embedded :class:`VectorRecordStorePort` adapter.

    Binds an existing ``sqlite3.Connection``; ``__init__`` runs the
    additive ``embeddings`` migration so the adapter is self-contained.
    ``clock`` is injectable for deterministic tests; it must return an
    ISO 8601 UTC timestamp string.
    """

    def __init__(
        self,
        db: sqlite3.Connection,
        clock: Callable[[], str] = _default_clock,
    ) -> None:
        self._db = db
        self._clock = clock
        migration_v2_add_embeddings_table(db)

    def put(self, record: VectorRecord) -> None:
        """Persist ``record``, stamping ``created_at`` from the clock.

        A second ``put`` for the same ``(chunk_id,
        embedding_profile_hash)`` overwrites the row.
        """

        created_at = self._clock()
        try:
            self._db.execute(
                """
                INSERT OR REPLACE INTO embeddings (
                    chunk_id,
                    embedding_profile_hash,
                    content_hash,
                    model_revision,
                    dimension,
                    normalization,
                    vector_payload,
                    created_from_retrieval_text_hash,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.chunk_id,
                    record.embedding_profile_hash,
                    record.content_hash,
                    record.model_revision,
                    record.dimension,
                    record.normalization,
                    record.vector_payload,
                    record.created_from_retrieval_text_hash,
                    created_at,
                ),
            )
        except sqlite3.Error as exc:
            raise VectorRecordStoreError(f"failed to put vector record: {exc}") from exc

    def get(
        self, chunk_id: str, embedding_profile_hash: str,
    ) -> VectorRecord | None:
        row = self._db.execute(
            """
            SELECT chunk_id, embedding_profile_hash, content_hash,
                   model_revision, dimension, normalization,
                   vector_payload, created_from_retrieval_text_hash,
                   created_at
            FROM embeddings
            WHERE chunk_id = ? AND embedding_profile_hash = ?
            """,
            (chunk_id, embedding_profile_hash),
        ).fetchone()
        if row is None:
            return None
        return self._record_from_row(row)

    def delete(self, chunk_id: str, embedding_profile_hash: str) -> None:
        self._db.execute(
            """
            DELETE FROM embeddings
            WHERE chunk_id = ? AND embedding_profile_hash = ?
            """,
            (chunk_id, embedding_profile_hash),
        )

    def iter(self, embedding_profile_hash: str) -> Iterable[VectorRecord]:
        rows = self._db.execute(
            """
            SELECT chunk_id, embedding_profile_hash, content_hash,
                   model_revision, dimension, normalization,
                   vector_payload, created_from_retrieval_text_hash,
                   created_at
            FROM embeddings
            WHERE embedding_profile_hash = ?
            ORDER BY chunk_id
            """,
            (embedding_profile_hash,),
        ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def profile_hash_for(self, chunk_id: str) -> str | None:
        row = self._db.execute(
            """
            SELECT embedding_profile_hash
            FROM embeddings
            WHERE chunk_id = ?
            ORDER BY embedding_profile_hash
            LIMIT 1
            """,
            (chunk_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row[0])

    def stats(self) -> Mapping[str, int]:
        records, profiles = self._db.execute(
            """
            SELECT COUNT(*), COUNT(DISTINCT embedding_profile_hash)
            FROM embeddings
            """
        ).fetchone()
        return {"records": int(records), "profile_hashes": int(profiles)}

    @staticmethod
    def _record_from_row(row: Sequence[object]) -> VectorRecord:
        return VectorRecord(
            chunk_id=str(row[0]),
            embedding_profile_hash=str(row[1]),
            content_hash=str(row[2]),
            model_revision=str(row[3]),
            dimension=int(row[4]),  # type: ignore[arg-type]
            normalization=str(row[5]),
            vector_payload=bytes(row[6]),  # type: ignore[arg-type]
            created_from_retrieval_text_hash=str(row[7]),
            created_at=str(row[8]),
        )
