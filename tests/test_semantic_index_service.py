"""Tests for the SemanticIndexService (open spec change PR 5).

These are the structural tests for the persistent semantic indexing
service. They use the test doubles from
:mod:`pi_platform.core.retrieval.semantic_index_service` and the real
:class:`USearchDenseIndex` from
:mod:`pi_platform.adapters.runtime.usearch_dense_index` so the
dense-backend round-trip is exercised end to end.

The tests cover the spec delta
``specs/2026-10-18-semantic-index-service/spec.md``:

* stored vectors are authoritative (no re-embed of unchanged text);
* embed only misses (changed text → fresh embedding);
* one namespace per profile identity (cross-profile rejection);
* reuse key = (retrieval_text_hash, profile_hash);
* count validation (count mismatch blocks activation).
"""

from __future__ import annotations

import os
import tempfile
import unittest

from pi_platform.adapters.runtime.usearch_dense_index import (
    DenseKeyStore,
    USearchDenseIndex,
)
from pi_platform.core.retrieval.semantic_index_service import (
    ActiveChunk,
    CountingEmbeddingModel,
    CrossProfileInsertRejected,
    InMemoryVectorRecordStore,
    IndexingReport,
    SemanticIndexService,
    SemanticIndexServiceError,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    EmbeddingProfile,
)


def _hash(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _make_chunk(chunk_id: str, retrieval_text: str) -> ActiveChunk:
    return ActiveChunk(
        chunk_id=chunk_id,
        content_hash=_hash(retrieval_text + "|source"),
        retrieval_text=retrieval_text,
        retrieval_text_hash=_hash(retrieval_text),
        metadata={"src": chunk_id},
    )


def _build_dense_index(
    tmp: str, *, profile_hash: str, dim: int,
) -> USearchDenseIndex:
    return USearchDenseIndex(
        embedding_profile_hash=profile_hash,
        cache_root=tmp,
        output_dimension=dim,
    )


class SemanticIndexServiceReuseTests(unittest.TestCase):
    """Stored vectors are authoritative; unchanged text is reused."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="semantic-index-test-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(self._tmp, ignore_errors=True),
        )
        self.profile = EMBEDDINGGEMMA2_512
        self.profile_hash = self.profile.identity()
        self.model = CountingEmbeddingModel(profile=self.profile)
        self.store = InMemoryVectorRecordStore()
        self.dense = _build_dense_index(
            self._tmp, profile_hash=self.profile_hash, dim=512,
        )
        self.service = SemanticIndexService(
            embedding_model=self.model,
            vector_record_store=self.store,
            dense_index=self.dense,
        )

    def test_unchanged_text_is_reused(self) -> None:
        chunks = [
            _make_chunk("c1", "alpha"),
            _make_chunk("c2", "beta"),
        ]
        first = self.service.embed_active_chunks(chunks)
        self.assertEqual(first.embedded_count, 2)
        self.assertEqual(first.reused_count, 0)
        self.assertEqual(
            len(self.model.embed_request_calls), 2,
            "the first call MUST embed every chunk",
        )
        # Second call with identical retrieval text: ZERO embed calls.
        self.model.embed_request_calls.clear()
        second = self.service.embed_active_chunks(chunks)
        self.assertEqual(second.embedded_count, 0)
        self.assertEqual(second.reused_count, 2)
        self.assertEqual(
            len(self.model.embed_request_calls), 0,
            "unchanged retrieval text MUST NOT trigger re-embedding"
        )
        # The source_generation is stable across identical inputs.
        self.assertEqual(first.source_generation, second.source_generation)

    def test_changed_text_is_reembedded(self) -> None:
        chunks = [_make_chunk("c1", "alpha")]
        first = self.service.embed_active_chunks(chunks)
        self.assertEqual(first.embedded_count, 1)
        # Capture the count of embed calls BEFORE the second call.
        before = len(self.model.embed_request_calls)
        # Now change the retrieval text (different hash).
        second_input = [_make_chunk("c1", "alpha-changed")]
        second = self.service.embed_active_chunks(second_input)
        self.assertEqual(second.embedded_count, 1)
        self.assertEqual(second.reused_count, 0)
        self.assertEqual(
            len(self.model.embed_request_calls) - before, 1,
            "the second call MUST trigger exactly one fresh embedding "
            "because the retrieval-text hash changed",
        )
        # The source_generation MUST change when retrieval text changes.
        self.assertNotEqual(
            first.source_generation, second.source_generation,
            "retrieval-text change MUST invalidate the source "
            "generation identifier",
        )

    def test_added_chunk_increments_generation(self) -> None:
        first = self.service.embed_active_chunks(
            [_make_chunk("c1", "alpha")],
        )
        second = self.service.embed_active_chunks(
            [_make_chunk("c1", "alpha"), _make_chunk("c2", "beta")],
        )
        self.assertNotEqual(
            first.source_generation, second.source_generation,
            "an added chunk MUST invalidate the generation"
        )
        self.assertEqual(second.embedded_count, 1)
        self.assertEqual(second.reused_count, 1)

    def test_removed_chunk_increments_generation(self) -> None:
        first = self.service.embed_active_chunks(
            [_make_chunk("c1", "alpha"), _make_chunk("c2", "beta")],
        )
        # Reconciliation step: caller drops c2 before calling
        # the service again. The service exposes ``remove_chunks``
        # for the REMOVED handling (open spec change PR 8).
        self.service.remove_chunks(["c2"])
        second = self.service.embed_active_chunks(
            [_make_chunk("c1", "alpha")],
        )
        self.assertNotEqual(
            first.source_generation, second.source_generation,
            "a removed chunk MUST invalidate the generation"
        )
        self.assertEqual(second.embedded_count, 0)
        self.assertEqual(second.reused_count, 1)

    def test_count_validation_matches_active_chunks(self) -> None:
        chunks = [_make_chunk("c1", "alpha"), _make_chunk("c2", "beta")]
        report = self.service.embed_active_chunks(chunks)
        self.assertEqual(report.expected_vector_count, 2)
        self.assertEqual(self.dense.stats()["vectors"], 2)

    def test_source_generation_is_deterministic(self) -> None:
        # Two services processing the same chunks must produce the
        # same source_generation identifier (plan §29, §42).
        other_tmp = tempfile.mkdtemp(
            prefix="semantic-index-second-",
        )
        self.addCleanup(
            lambda: __import__("shutil").rmtree(other_tmp, ignore_errors=True),
        )
        other_dense = _build_dense_index(
            other_tmp, profile_hash=self.profile_hash, dim=512,
        )
        other_model = CountingEmbeddingModel(profile=self.profile)
        other_service = SemanticIndexService(
            embedding_model=other_model,
            vector_record_store=InMemoryVectorRecordStore(),
            dense_index=other_dense,
        )
        chunks = [_make_chunk("c1", "alpha"), _make_chunk("c2", "beta")]
        first = self.service.embed_active_chunks(chunks)
        second = other_service.embed_active_chunks(chunks)
        self.assertEqual(
            first.source_generation, second.source_generation,
        )


class SemanticIndexServiceNamespaceTests(unittest.TestCase):
    """Each profile identity owns exactly one namespace."""

    def test_cross_profile_insert_is_rejected(self) -> None:
        # The init-time check refuses to construct a service whose
        # embedding model profile hash differs from the dense
        # index namespace. This is the spec-required structural
        # guard: a vector produced under profile B MUST NOT be
        # silently inserted into profile A's namespace.
        tmp = tempfile.mkdtemp(prefix="semantic-cross-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(tmp, ignore_errors=True),
        )
        gemma_profile = EMBEDDINGGEMMA2_512
        qwen_profile = EmbeddingProfile(
            provider="qwen3-embedding-0.6b",
            model_id="Qwen/Qwen3-Embedding-0.6B",
            model_revision="97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3",
            modality="text",
            output_dimension=1024,
            normalization="l2",
            instruction_profile="project-expert-qwen-query-v1",
            tokenizer_id="Qwen/Qwen3-Embedding-0.6B@97b0",
            strategy_version="embedding-profile-v1",
        )
        qwen_dense = _build_dense_index(
            tmp, profile_hash=qwen_profile.identity(),
            dim=qwen_profile.output_dimension,
        )
        with self.assertRaises(CrossProfileInsertRejected):
            SemanticIndexService(
                embedding_model=CountingEmbeddingModel(profile=gemma_profile),
                vector_record_store=InMemoryVectorRecordStore(),
                dense_index=qwen_dense,
            )

    def test_per_insert_profile_check_also_rejects(self) -> None:
        # The per-insert guard refuses to allow a chunk whose
        # persisted vector record was produced under a different
        # profile identity (the vector_record_store is keyed by
        # profile hash so this is a stronger guarantee; we
        # verify by intentionally mutating the dense index's
        # profile hash to a different value after construction).
        tmp = tempfile.mkdtemp(prefix="semantic-runtime-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(tmp, ignore_errors=True),
        )
        profile = EMBEDDINGGEMMA2_512
        dense = _build_dense_index(
            tmp, profile_hash=profile.identity(),
            dim=profile.output_dimension,
        )
        service = SemanticIndexService(
            embedding_model=CountingEmbeddingModel(profile=profile),
            vector_record_store=InMemoryVectorRecordStore(),
            dense_index=dense,
        )
        # Force the runtime cross-profile check by swapping the
        # dense index's profile hash after construction.
        dense._embedding_profile_hash = "deadbeef" * 8
        with self.assertRaises(CrossProfileInsertRejected):
            service.embed_active_chunks([_make_chunk("c1", "alpha")])

    def test_dimension_mismatch_raises(self) -> None:
        tmp = tempfile.mkdtemp(prefix="semantic-dim-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(tmp, ignore_errors=True),
        )
        # Embedding profile is 512d but the dense index is 4d:
        # the count-validation guard refuses to activate.
        dense = USearchDenseIndex(
            embedding_profile_hash=EMBEDDINGGEMMA2_512.identity(),
            cache_root=tmp, output_dimension=4,
        )
        service = SemanticIndexService(
            embedding_model=CountingEmbeddingModel(
                profile=EMBEDDINGGEMMA2_512,
            ),
            vector_record_store=InMemoryVectorRecordStore(),
            dense_index=dense,
        )
        with self.assertRaises(SemanticIndexServiceError):
            service.embed_active_chunks(
                [_make_chunk("c1", "alpha")],
            )


class SemanticIndexServiceKeyStoreTests(unittest.TestCase):
    """The service tolerates a :class:`DenseKeyStore` and reuses
    the same numeric key across rebuilds."""

    def test_dense_key_store_persists_mapping(self) -> None:
        tmp = tempfile.mkdtemp(prefix="semantic-keystore-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(tmp, ignore_errors=True),
        )
        key_store = DenseKeyStore(os.path.join(tmp, "keys.sqlite"))
        profile = EMBEDDINGGEMMA2_512
        dense = USearchDenseIndex(
            embedding_profile_hash=profile.identity(),
            cache_root=tmp,
            dense_key_store=key_store,
            output_dimension=512,
        )
        service = SemanticIndexService(
            embedding_model=CountingEmbeddingModel(profile=profile),
            vector_record_store=InMemoryVectorRecordStore(),
            dense_index=dense,
            dense_key_store=key_store,
        )
        service.embed_active_chunks(
            [_make_chunk("c1", "alpha"), _make_chunk("c2", "beta")],
        )
        # Reopening the key store in a fresh handle preserves the
        # mapping.
        new_store = DenseKeyStore(os.path.join(tmp, "keys.sqlite"))
        for cid in ("c1", "c2"):
            self.assertIsNotNone(
                new_store.resolve(profile.identity(), cid),
                f"key store MUST remember chunk {cid!r} across restart",
            )


if __name__ == "__main__":
    unittest.main()
