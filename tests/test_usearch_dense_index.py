"""Tests for the USearch ANN adapter (Change Package D)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest

from pi_platform.ports.runtime.dense_index import (
    DenseHit,
    DenseIndexError,
    DenseIndexPort,
)

from pi_platform.adapters.runtime.flat_dense_index import FlatDenseIndex
from pi_platform.adapters.runtime.usearch_dense_index import (
    ANNIndexError,
    DEFAULT_HNSW_EF_CONSTRUCTION,
    DEFAULT_HNSW_EF_QUERY,
    DEFAULT_HNSW_M,
    DEFAULT_INDEX_SCHEMA_VERSION,
    USearchDenseIndex,
)
from pi_platform.adapters.runtime.dense_index_backend import (
    AUTO_FLAT_CORPUS_THRESHOLD,
    AutoCorpusSizeError,
    DenseIndexBackend,
    select_dense_index,
)


def _vec(values):
    return tuple(float(v) for v in values)


class USearchDenseIndexConformsToPortTests(unittest.TestCase):
    """D1: USearchDenseIndex conforms to DenseIndexPort."""

    def test_is_dense_index_port(self) -> None:
        idx = USearchDenseIndex(embedding_profile_hash="ph-1")
        self.assertIsInstance(idx, DenseIndexPort)

    def test_required_profile_hash(self) -> None:
        with self.assertRaises(ANNIndexError):
            USearchDenseIndex(embedding_profile_hash="")

    def test_index_query_delete_round_trip(self) -> None:
        idx = USearchDenseIndex(embedding_profile_hash="ph-1")
        # a is the closest to the query; b and c are further
        # away. Use L2-normalised vectors so cosine similarity is
        # a direct dot product.
        import math
        def _normalise(v):
            n = math.sqrt(sum(x * x for x in v))
            return tuple(x / n for x in v)
        a = _normalise([1.0, 0.4, 0.0])
        b = _normalise([0.7, 0.0, 0.5])
        c = _normalise([0.4, 0.3, 0.6])
        idx.index_chunk("a", a, {"src": "a"})
        idx.index_chunk("b", b, {"src": "b"})
        idx.index_chunk("c", c, {"src": "c"})
        hits = idx.query(_normalise([1.0, 0.0, 0.0]), top_k=3)
        self.assertEqual(len(hits), 3)
        self.assertEqual(hits[0].chunkId, "a")
        self.assertGreater(hits[0].score, hits[1].score)
        idx.delete_chunk("b")
        self.assertEqual(idx.stats()["vectors"], 2)
        hits = idx.query(_normalise([1.0, 0.0, 0.0]), top_k=3)
        self.assertEqual([h.chunkId for h in hits], ["a", "c"])

    def test_dimension_mismatch_raises(self) -> None:
        idx = USearchDenseIndex(embedding_profile_hash="ph-1")
        idx.index_chunk("a", _vec([1.0, 0.0]), {"src": "a"})
        with self.assertRaises(ANNIndexError):
            idx.index_chunk("b", _vec([1.0, 0.0, 0.0]), {"src": "b"})
        with self.assertRaises(ANNIndexError):
            idx.query(_vec([1.0, 0.0, 0.0]), top_k=3)

    def test_stats_reports_hnsw_config(self) -> None:
        idx = USearchDenseIndex(
            embedding_profile_hash="ph-1",
            m=32,
            ef_construction=128,
            ef_query=64,
        )
        self.assertEqual(idx.stats()["m"], 32)
        self.assertEqual(idx.stats()["ef_construction"], 128)
        self.assertEqual(idx.stats()["ef_query"], 64)


class USearchIndexMetadataTests(unittest.TestCase):
    """D1+D3: index metadata round-trip, profile-hash namespace,
    compatibility check."""

    def _tmp_root(self) -> str:
        tmp = tempfile.mkdtemp(prefix="usearch-test-")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        return tmp

    def test_metadata_round_trip(self) -> None:
        root = self._tmp_root()
        idx = USearchDenseIndex(
            embedding_profile_hash="ph-1", cache_root=root,
        )
        idx.index_chunk("a", _vec([1.0, 0.0, 0.0]), {"src": "a"})
        idx.write_index_meta(vector_count=1, source_generation="gen-7")
        # Re-open: same root + same profile hash should reuse the
        # namespace; the in-memory store is fresh but the metadata
        # file is on disk.
        idx2 = USearchDenseIndex(
            embedding_profile_hash="ph-1", cache_root=root,
        )
        meta = idx2.read_index_meta()
        self.assertEqual(meta["embedding_profile_hash"], "ph-1")
        self.assertEqual(meta["index_schema_version"], DEFAULT_INDEX_SCHEMA_VERSION)
        self.assertEqual(meta["source_generation"], "gen-7")
        self.assertEqual(meta["vector_count"], 1)
        self.assertEqual(meta["backend"], "usearch")
        self.assertEqual(meta["m"], DEFAULT_HNSW_M)
        self.assertEqual(meta["ef_construction"], DEFAULT_HNSW_EF_CONSTRUCTION)
        self.assertEqual(meta["ef_query"], DEFAULT_HNSW_EF_QUERY)
        self.assertEqual(meta["dim"], 3)

    def test_incompatible_profile_clears_in_memory_store(self) -> None:
        root = self._tmp_root()
        a = USearchDenseIndex(embedding_profile_hash="ph-A", cache_root=root)
        a.index_chunk("x", _vec([1.0, 0.0, 0.0]), {"src": "x"})
        # A different profile hash opens the same directory; the
        # in-memory store must reset because the namespace is
        # incompatible.
        b = USearchDenseIndex(embedding_profile_hash="ph-B", cache_root=root)
        self.assertEqual(b.stats()["vectors"], 0)
        # The metadata file still records ph-A (the persisted
        # namespace). A rebuild is the caller's responsibility.
        self.assertEqual(b.read_index_meta()["embedding_profile_hash"], "ph-A")

    def test_is_compatible_with(self) -> None:
        root = self._tmp_root()
        idx = USearchDenseIndex(embedding_profile_hash="ph-1", cache_root=root)
        idx.write_index_meta(vector_count=0, source_generation="gen-7")
        # Same profile + same source generation: compatible.
        self.assertTrue(
            idx.is_compatible_with(
                embedding_profile_hash="ph-1", source_generation="gen-7",
            )
        )
        # Different profile hash: incompatible.
        self.assertFalse(
            idx.is_compatible_with(embedding_profile_hash="ph-2")
        )
        # Different source generation: incompatible.
        self.assertFalse(
            idx.is_compatible_with(
                embedding_profile_hash="ph-1", source_generation="gen-8",
            )
        )

    def test_is_compatible_with_no_meta_file(self) -> None:
        root = self._tmp_root()
        idx = USearchDenseIndex(embedding_profile_hash="ph-1", cache_root=root)
        # No metadata file yet → not compatible.
        self.assertFalse(idx.is_compatible_with(embedding_profile_hash="ph-1"))


class USearchRebuildTests(unittest.TestCase):
    """D3: rebuild from vector records on profile / source
    generation mismatch (no re-embedding required)."""

    def _tmp_root(self) -> str:
        tmp = tempfile.mkdtemp(prefix="usearch-rebuild-")
        self.addCleanup(lambda: __import__("shutil").rmtree(tmp, ignore_errors=True))
        return tmp

    def test_rebuild_from_records(self) -> None:
        root = self._tmp_root()
        idx = USearchDenseIndex(embedding_profile_hash="ph-1", cache_root=root)
        records = [
            ("a", _vec([1.0, 0.0, 0.0])),
            ("b", _vec([0.0, 1.0, 0.0])),
            ("c", _vec([0.0, 0.0, 1.0])),
        ]
        inserted = idx.rebuild_from(records, source_generation="gen-9")
        self.assertEqual(inserted, 3)
        self.assertEqual(idx.stats()["vectors"], 3)
        self.assertEqual(idx.read_index_meta()["source_generation"], "gen-9")
        self.assertEqual(idx.read_index_meta()["vector_count"], 3)
        hits = idx.query(_vec([1.0, 0.0, 0.0]), top_k=3)
        self.assertEqual(hits[0].chunkId, "a")

    def test_rebuild_clears_previous_state(self) -> None:
        root = self._tmp_root()
        idx = USearchDenseIndex(embedding_profile_hash="ph-1", cache_root=root)
        idx.index_chunk("old", _vec([1.0, 0.0, 0.0]), {"src": "old"})
        self.assertEqual(idx.stats()["vectors"], 1)
        idx.rebuild_from(
            [("a", _vec([1.0, 0.0, 0.0])), ("b", _vec([0.0, 1.0, 0.0]))],
            source_generation="gen-2",
        )
        self.assertEqual(idx.stats()["vectors"], 2)
        hits = idx.query(_vec([1.0, 0.0, 0.0]), top_k=5)
        self.assertNotIn("old", [h.chunkId for h in hits])

    def test_rebuild_dimension_mismatch_raises(self) -> None:
        root = self._tmp_root()
        idx = USearchDenseIndex(embedding_profile_hash="ph-1", cache_root=root)
        with self.assertRaises(ANNIndexError):
            idx.rebuild_from([
                ("a", _vec([1.0, 0.0, 0.0])),
                ("b", _vec([1.0, 0.0])),  # wrong dim
            ])


class USearchProductionStubTests(unittest.TestCase):
    """The production stub does not require ``usearch`` at
    import time; the real binding is a follow-up (D.1.5)."""

    def test_importable_without_usearch(self) -> None:
        # If usearch were not installed, the import would still
        # succeed. (We are in a stdlib-only environment so this is
        # a tautology; the test guards against future regressions
        # where someone imports usearch at module level.)
        import pi_platform.adapters.runtime.usearch_dense_index as m
        self.assertIsNotNone(m.USearchDenseIndex)

    def test_stats_distinguishes_stub(self) -> None:
        idx = USearchDenseIndex(embedding_profile_hash="ph-1")
        idx.index_chunk("a", _vec([1.0, 0.0, 0.0]), {"src": "a"})
        meta = idx.read_index_meta()
        self.assertEqual(meta["backend"], "usearch")
        self.assertEqual(meta["embedding_profile_hash"], "ph-1")


class DenseIndexBackendSelectionTests(unittest.TestCase):
    """D2: ``dense_index.backend ∈ {auto, flat, usearch}``
    configuration knob."""

    def test_flat_backend(self) -> None:
        idx = select_dense_index("flat", embedding_profile_hash="ph-1")
        self.assertIsInstance(idx, FlatDenseIndex)

    def test_usearch_backend(self) -> None:
        idx = select_dense_index(
            "usearch", embedding_profile_hash="ph-1",
        )
        self.assertIsInstance(idx, USearchDenseIndex)
        self.assertEqual(idx.embedding_profile_hash, "ph-1")

    def test_auto_small_corpus_uses_flat(self) -> None:
        idx = select_dense_index(
            "auto", embedding_profile_hash="ph-1", corpus_size=10,
        )
        self.assertIsInstance(idx, FlatDenseIndex)

    def test_auto_large_corpus_uses_usearch(self) -> None:
        idx = select_dense_index(
            "auto", embedding_profile_hash="ph-1",
            corpus_size=AUTO_FLAT_CORPUS_THRESHOLD + 1,
        )
        self.assertIsInstance(idx, USearchDenseIndex)

    def test_auto_at_threshold_uses_flat(self) -> None:
        # The threshold is INCLUSIVE on the Flat side; the
        # architectural invariant is "small corpora use Flat,
        # large corpora use USearch", not a specific number.
        idx = select_dense_index(
            "auto", embedding_profile_hash="ph-1",
            corpus_size=AUTO_FLAT_CORPUS_THRESHOLD,
        )
        self.assertIsInstance(idx, FlatDenseIndex)

    def test_auto_without_corpus_size_raises(self) -> None:
        with self.assertRaises(AutoCorpusSizeError):
            select_dense_index("auto", embedding_profile_hash="ph-1")

    def test_usearch_without_profile_hash_raises(self) -> None:
        with self.assertRaises(DenseIndexError):
            select_dense_index("usearch", embedding_profile_hash="")

    def test_unknown_backend_raises(self) -> None:
        with self.assertRaises(DenseIndexError):
            select_dense_index("postgres", embedding_profile_hash="ph-1")

    def test_allowed_values(self) -> None:
        self.assertEqual(
            set(DenseIndexBackend.ALLOWED), {"auto", "flat", "usearch"},
        )


class FlatDenseIndexByteIdenticalTests(unittest.TestCase):
    """The legacy FlatDenseIndex must continue to pass
    byte-identically (no accepted requirement body changes)."""

    def test_flat_unchanged(self) -> None:
        idx = FlatDenseIndex()
        idx.index_chunk("a", _vec([1.0, 0.0, 0.0]), {"src": "a"})
        idx.index_chunk("b", _vec([0.0, 1.0, 0.0]), {"src": "b"})
        hits = idx.query(_vec([1.0, 0.0, 0.0]), top_k=2)
        self.assertEqual(hits[0].chunkId, "a")
        self.assertEqual(idx.stats()["vectors"], 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
