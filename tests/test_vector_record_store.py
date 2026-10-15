"""Vector record persistence tests (Change Package C3).

Covers the ``VectorRecordStorePort`` contract against the SQLite
adapter: put/get round-trip, profile-scoped iteration, overwrite
semantics, BLOB (non-JSON) payloads, the additive migration, and
stats.
"""

from __future__ import annotations

import dataclasses
import sqlite3
import unittest

from pi_platform.adapters.runtime.sqlite_vector_record_store import (
    SqliteVectorRecordStore,
    decode_vector_payload,
    encode_vector_payload,
    migration_v2_add_embeddings_table,
)
from pi_platform.ports.runtime.vector_record_store import (
    VectorRecord,
    VectorRecordStoreError,
    VectorRecordStorePort,
)


FIXED_CLOCK_VALUE = "2026-10-14T00:00:00+00:00"
PROFILE_A = "a" * 64
PROFILE_B = "b" * 64


def _fixed_clock() -> str:
    return FIXED_CLOCK_VALUE


def _record(
    chunk_id: str = "chunk-1",
    profile_hash: str = PROFILE_A,
    vector=(0.25, 0.5, 0.75, 1.0),
    dtype: str = "f",
) -> VectorRecord:
    return VectorRecord(
        chunk_id=chunk_id,
        content_hash="c" * 64,
        embedding_profile_hash=profile_hash,
        model_revision="v1",
        dimension=len(vector),
        normalization="l2",
        vector_payload=encode_vector_payload(vector, dtype=dtype),
        created_from_retrieval_text_hash="r" * 64,
    )


class VectorRecordStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.store = SqliteVectorRecordStore(self.db, clock=_fixed_clock)

    def test_implements_port(self):
        self.assertIsInstance(self.store, VectorRecordStorePort)

    def test_put_and_get_roundtrip(self):
        record = _record()
        self.store.put(record)
        loaded = self.store.get(record.chunk_id, record.embedding_profile_hash)
        expected = dataclasses.replace(record, created_at=FIXED_CLOCK_VALUE)
        self.assertEqual(loaded, expected)
        self.assertEqual(loaded.created_at, FIXED_CLOCK_VALUE)
        self.assertEqual(loaded.content_hash, record.content_hash)
        self.assertEqual(loaded.model_revision, record.model_revision)
        self.assertEqual(loaded.dimension, record.dimension)
        self.assertEqual(loaded.normalization, record.normalization)
        self.assertEqual(
            loaded.created_from_retrieval_text_hash,
            record.created_from_retrieval_text_hash,
        )

    def test_created_at_is_stamped_at_put_time(self):
        record = VectorRecord(
            chunk_id="chunk-1",
            content_hash="c" * 64,
            embedding_profile_hash=PROFILE_A,
            model_revision="v1",
            dimension=4,
            normalization="l2",
            vector_payload=b"\x00\x00\x80\x3e",
            created_from_retrieval_text_hash="r" * 64,
            created_at="",  # never trusted; the store stamps it
        )
        self.store.put(record)
        loaded = self.store.get(record.chunk_id, record.embedding_profile_hash)
        self.assertEqual(loaded.created_at, FIXED_CLOCK_VALUE)

    def test_get_unknown_returns_none(self):
        self.assertIsNone(self.store.get("missing", PROFILE_A))

    def test_delete(self):
        record = _record()
        self.store.put(record)
        self.store.delete(record.chunk_id, record.embedding_profile_hash)
        self.assertIsNone(self.store.get(record.chunk_id, record.embedding_profile_hash))
        self.assertEqual(list(self.store.iter(record.embedding_profile_hash)), [])

    def test_delete_unknown_is_noop(self):
        self.store.delete("missing", PROFILE_A)  # must not raise

    def test_iter_filters_by_profile(self):
        self.store.put(_record(chunk_id="chunk-a", profile_hash=PROFILE_A))
        self.store.put(_record(chunk_id="chunk-b", profile_hash=PROFILE_B))
        only_a = list(self.store.iter(PROFILE_A))
        only_b = list(self.store.iter(PROFILE_B))
        self.assertEqual([r.chunk_id for r in only_a], ["chunk-a"])
        self.assertEqual([r.chunk_id for r in only_b], ["chunk-b"])

    def test_primary_key_uniqueness_overwrites(self):
        # Documented contract: a second put for the same
        # (chunk_id, profile) overwrites the row.
        first = _record(vector=(1.0, 0.0))
        self.store.put(first)
        second = VectorRecord(
            chunk_id=first.chunk_id,
            content_hash="d" * 64,
            embedding_profile_hash=first.embedding_profile_hash,
            model_revision="v2",
            dimension=2,
            normalization="none",
            vector_payload=encode_vector_payload((0.0, 1.0)),
            created_from_retrieval_text_hash="s" * 64,
        )
        self.store.put(second)
        loaded = self.store.get(first.chunk_id, first.embedding_profile_hash)
        self.assertEqual(loaded.content_hash, "d" * 64)
        self.assertEqual(loaded.model_revision, "v2")
        self.assertEqual(loaded.normalization, "none")
        self.assertEqual(self.store.stats()["records"], 1)

    def test_vector_payload_not_json(self):
        vector = (0.1, 0.2, 0.3, 0.4, 0.5)
        record = _record(vector=vector)
        self.store.put(record)
        loaded = self.store.get(record.chunk_id, record.embedding_profile_hash)
        self.assertIsInstance(loaded.vector_payload, bytes)
        self.assertNotIn(b"[", loaded.vector_payload)
        decoded = decode_vector_payload(loaded.vector_payload)
        for expected, actual in zip(vector, decoded):
            self.assertAlmostEqual(expected, actual, places=6)

    def test_profile_hash_for(self):
        self.store.put(_record(chunk_id="chunk-1", profile_hash=PROFILE_A))
        self.store.put(_record(chunk_id="chunk-1", profile_hash=PROFILE_B))
        self.assertEqual(self.store.profile_hash_for("chunk-1"), PROFILE_A)
        self.assertIsNone(self.store.profile_hash_for("missing"))

    def test_stats_counts_records_and_profiles(self):
        self.store.put(_record(chunk_id="chunk-1", profile_hash=PROFILE_A))
        self.store.put(_record(chunk_id="chunk-2", profile_hash=PROFILE_A))
        self.store.put(_record(chunk_id="chunk-3", profile_hash=PROFILE_B))
        self.assertEqual(
            self.store.stats(), {"records": 3, "profile_hashes": 2}
        )

    def test_unsupported_dtype_raises(self):
        with self.assertRaises(VectorRecordStoreError):
            encode_vector_payload((1.0,), dtype="i")
        with self.assertRaises(VectorRecordStoreError):
            decode_vector_payload(b"\x00\x00\x00\x00", dtype="i")

    def test_malformed_payload_raises(self):
        with self.assertRaises(VectorRecordStoreError):
            decode_vector_payload(b"\x00\x00\x00", dtype="f")


class EncodeDecodeRoundtripTests(unittest.TestCase):
    def test_encode_decode_roundtrip_float32(self):
        vector = [0.0, 1.0, -1.0, 0.5, -0.25]
        blob = encode_vector_payload(vector, dtype="f")
        self.assertIsInstance(blob, bytes)
        self.assertEqual(len(blob), 4 * len(vector))
        decoded = decode_vector_payload(blob, dtype="f")
        for expected, actual in zip(vector, decoded):
            self.assertAlmostEqual(expected, actual, places=6)

    def test_encode_decode_roundtrip_float64(self):
        vector = [0.1, 0.2, 0.3]
        blob = encode_vector_payload(vector, dtype="d")
        self.assertEqual(len(blob), 8 * len(vector))
        self.assertEqual(decode_vector_payload(blob, dtype="d"), vector)


class MigrationTests(unittest.TestCase):
    def test_migration_creates_table(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        migration_v2_add_embeddings_table(db)
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'embeddings'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_migration_idempotent(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        migration_v2_add_embeddings_table(db)
        migration_v2_add_embeddings_table(db)  # must not raise
        row = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'embeddings'"
        ).fetchone()
        self.assertIsNotNone(row)

    def test_migration_preserves_existing_rows(self):
        db = sqlite3.connect(":memory:")
        self.addCleanup(db.close)
        db.execute("CREATE TABLE legacy (id INTEGER PRIMARY KEY)")
        db.execute("INSERT INTO legacy (id) VALUES (1)")
        migration_v2_add_embeddings_table(db)
        self.assertEqual(
            db.execute("SELECT COUNT(*) FROM legacy").fetchone()[0], 1
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
