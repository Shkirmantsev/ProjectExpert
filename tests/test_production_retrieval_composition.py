"""Tests for the production retrieval runtime composition (open spec change PR 7).

Covers the ``unified-production-retrieval-composition`` spec delta:
every consumer MUST receive the same retrieval services for the same
runtime configuration. The tests assert the structural invariants
the spec requires:

* all 12 collaborators are wired by the composition;
* the embedding profile hash is shared between the embedding model,
  the dense index and the semantic index service;
* the production backend reports ``"usearch"`` when the library is
  importable (the production-capability-gate reads that signal);
* the same composition can be invoked from the web UI and the MCP
  path and yields the same backend name and profile hash.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from pi_platform.adapters.runtime.usearch_dense_index import is_real_usearch_available
from pi_platform.core.orchestration.retrieval_composition import (
    DEFAULT_TOP_K,
    ProductionRetrievalRuntime,
    build_context_assembler,
    build_dense_index,
    build_graph_expansion,
    build_hybrid_retrieval,
    build_metadata_filter,
    build_multi_stage_retrieval,
    build_production_retrieval_runtime,
    build_reranker,
    build_semantic_index_service,
    build_sparse_index,
    vector_record_store_from_db,
)
from pi_platform.core.retrieval.hybrid_retrieval import HybridRetrievalCore
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)
from pi_platform.core.retrieval.semantic_index_service import (
    CountingEmbeddingModel,
    InMemoryVectorRecordStore,
    SemanticIndexService,
)
from pi_platform.ports.retrieval.context_assembler import ContextAssemblerPort
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelPort
from pi_platform.ports.runtime.graph_expansion import GraphExpansionPort
from pi_platform.ports.retrieval.hybrid_retrieval import HybridRetrievalPort
from pi_platform.ports.retrieval.metadata_filter import MetadataFilterPort
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalPort,
)
from pi_platform.ports.retrieval.reranker import RerankerPort
from pi_platform.ports.runtime.dense_index import DenseIndexPort
from pi_platform.ports.runtime.sparse_index import SparseIndexPort
from pi_platform.ports.runtime.vector_record_store import (
    VectorRecordStorePort,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
)


def _build_test_components(tmp: Path):
    """Helper that builds the test-side collaborators in one place."""
    profile = EMBEDDINGGEMMA2_512
    embedding_model = CountingEmbeddingModel(profile=profile)
    vector_record_store = InMemoryVectorRecordStore()
    dense_index = build_dense_index(
        embedding_profile_hash=profile.identity(),
        cache_root=str(tmp / "dense"),
        output_dimension=profile.output_dimension,
    )
    sparse = build_sparse_index()
    return {
        "profile": profile,
        "embedding_model": embedding_model,
        "vector_record_store": vector_record_store,
        "dense_index": dense_index,
        "sparse_index": sparse,
    }


class CompositionWiringTests(unittest.TestCase):
    """The composition MUST wire every documented collaborator."""

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="composition-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(
                self._tmp, ignore_errors=True,
            ),
        )

    def test_composition_builds_all_collaborators(self) -> None:
        components = _build_test_components(Path(self._tmp))
        runtime = build_production_retrieval_runtime(
            cache_root=Path(self._tmp),
            embedding_alias="gemma",
            embedding_model=components["embedding_model"],
            vector_record_store=components["vector_record_store"],
            dense_index=components["dense_index"],
            sparse_index=components["sparse_index"],
        )
        self.assertIsInstance(runtime, ProductionRetrievalRuntime)
        self.assertIsInstance(runtime.embedding_model, EmbeddingModelPort)
        self.assertIsInstance(runtime.vector_record_store, VectorRecordStorePort)
        self.assertIsInstance(runtime.dense_index, DenseIndexPort)
        self.assertIsInstance(runtime.sparse_index, SparseIndexPort)
        self.assertIsInstance(runtime.hybrid_retrieval, HybridRetrievalPort)
        self.assertIsInstance(runtime.metadata_filter, MetadataFilterPort)
        self.assertIsInstance(runtime.reranker, RerankerPort)
        self.assertIsInstance(runtime.graph_expansion, GraphExpansionPort)
        self.assertIsInstance(runtime.context_assembler, ContextAssemblerPort)
        self.assertIsInstance(runtime.multi_stage_retrieval, MultiStageRetrievalPort)
        self.assertIsInstance(runtime.semantic_index_service, SemanticIndexService)

    def test_embedding_profile_hash_is_shared(self) -> None:
        components = _build_test_components(Path(self._tmp))
        runtime = build_production_retrieval_runtime(
            cache_root=Path(self._tmp),
            embedding_alias="gemma",
            embedding_model=components["embedding_model"],
            vector_record_store=components["vector_record_store"],
            dense_index=components["dense_index"],
            sparse_index=components["sparse_index"],
        )
        self.assertEqual(
            runtime.embedding_profile_hash,
            components["profile"].identity(),
            "the embedding profile hash MUST be the source of truth "
            "for every collaborator",
        )
        # The semantic index service MUST agree on the hash; the
        # service uses the embedding model's profile() to derive it.
        self.assertEqual(
            runtime.semantic_index_service.embedding_profile_hash,
            runtime.embedding_profile_hash,
        )

    def test_default_rerank_budget_is_documented(self) -> None:
        self.assertEqual(
            DEFAULT_TOP_K, 50,
            "the documented default top_k is 50 (plan §29)",
        )

    def test_sparse_index_factory_returns_bm25(self) -> None:
        from pi_platform.adapters.runtime.bm25_sparse_index import Bm25SparseIndex
        sparse = build_sparse_index()
        self.assertIsInstance(sparse, Bm25SparseIndex)
        self.assertIsInstance(sparse, SparseIndexPort)

    def test_reranker_factory_returns_bm25_light(self) -> None:
        from pi_platform.adapters.retrieval.bm25_light_reranker import (
            Bm25LightRerankerAdapter,
        )
        reranker = build_reranker()
        self.assertIsInstance(reranker, Bm25LightRerankerAdapter)
        self.assertIsInstance(reranker, RerankerPort)

    def test_graph_expansion_factory_returns_production(self) -> None:
        from pi_platform.adapters.runtime.graph_expansion import (
            ProductionGraphExpansion,
        )
        graph = build_graph_expansion()
        self.assertIsInstance(graph, ProductionGraphExpansion)
        self.assertIsInstance(graph, GraphExpansionPort)

    def test_context_assembler_factory(self) -> None:
        from pi_platform.adapters.retrieval.context_assembler_adapter import (
            ContextAssemblerAdapter,
        )
        assembler = build_context_assembler()
        self.assertIsInstance(assembler, ContextAssemblerAdapter)
        self.assertIsInstance(assembler, ContextAssemblerPort)

    def test_metadata_filter_factory(self) -> None:
        from pi_platform.adapters.retrieval.metadata_filter_adapter import (
            MetadataFilterAdapter,
        )
        meta = build_metadata_filter()
        self.assertIsInstance(meta, MetadataFilterAdapter)
        self.assertIsInstance(meta, MetadataFilterPort)

    def test_hybrid_retrieval_factory_returns_hybrid_core(self) -> None:
        components = _build_test_components(Path(self._tmp))
        hybrid = build_hybrid_retrieval(
            dense_index=components["dense_index"],
            sparse_index=components["sparse_index"],
            exact_lookup=None,
        )
        # The production adapter extends HybridRetrievalCore; that
        # is the same class the original UI used so the semantics
        # match.
        self.assertIsInstance(hybrid, HybridRetrievalCore)

    def test_multi_stage_retrieval_factory(self) -> None:
        components = _build_test_components(Path(self._tmp))
        hybrid = build_hybrid_retrieval(
            dense_index=components["dense_index"],
            sparse_index=components["sparse_index"],
            exact_lookup=None,
        )
        multi = build_multi_stage_retrieval(
            hybrid_retrieval=hybrid,
            metadata_filter=build_metadata_filter(),
            graph_expansion=build_graph_expansion(),
            reranker=build_reranker(),
            context_assembler=build_context_assembler(),
        )
        self.assertIsInstance(multi, MultiStageRetrievalCore)
        self.assertIsInstance(multi, MultiStageRetrievalPort)

    def test_semantic_index_service_factory(self) -> None:
        from pi_platform.adapters.runtime.usearch_dense_index import (
            USearchDenseIndex,
        )
        from pi_platform.adapters.runtime.sqlite_vector_record_store import (
            SqliteVectorRecordStore,
        )
        import sqlite3
        # The factory requires the production USearch backend; the
        # SQLite vector record store is acceptable here.
        profile = EMBEDDINGGEMMA2_512
        db = sqlite3.connect(":memory:")
        vrs = SqliteVectorRecordStore(db=db)
        dense = USearchDenseIndex(
            embedding_profile_hash=profile.identity(),
            cache_root=os.path.join(self._tmp, "dense"),
            output_dimension=profile.output_dimension,
        )
        service = build_semantic_index_service(
            embedding_model=CountingEmbeddingModel(profile=profile),
            vector_record_store=vrs,
            dense_index=dense,
        )
        self.assertIsInstance(service, SemanticIndexService)
        self.assertEqual(
            service.embedding_profile_hash, profile.identity(),
        )


class CompositionConsistencyTests(unittest.TestCase):
    """Two compositions built with the same config MUST agree on
    backend name and embedding profile hash.

    This is the spec's "same query same semantics" contract: the web
    UI and the MCP server MUST NOT drift to different backends.
    """

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="composition-consistency-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(
                self._tmp, ignore_errors=True,
            ),
        )

    def test_two_compositions_agree_on_backend(self) -> None:
        components_a = _build_test_components(Path(self._tmp) / "a")
        components_b = _build_test_components(Path(self._tmp) / "b")
        runtime_a = build_production_retrieval_runtime(
            cache_root=Path(self._tmp) / "a",
            embedding_alias="gemma",
            embedding_model=components_a["embedding_model"],
            vector_record_store=components_a["vector_record_store"],
            dense_index=components_a["dense_index"],
            sparse_index=components_a["sparse_index"],
        )
        runtime_b = build_production_retrieval_runtime(
            cache_root=Path(self._tmp) / "b",
            embedding_alias="gemma",
            embedding_model=components_b["embedding_model"],
            vector_record_store=components_b["vector_record_store"],
            dense_index=components_b["dense_index"],
            sparse_index=components_b["sparse_index"],
        )
        self.assertEqual(
            runtime_a.embedding_profile_hash,
            runtime_b.embedding_profile_hash,
        )
        self.assertEqual(
            runtime_a.backend_name, runtime_b.backend_name,
            "the backend name MUST be identical across compositions "
            "for the same alias",
        )

    def test_runtime_stage_report_includes_truthful_backend(self) -> None:
        components = _build_test_components(Path(self._tmp))
        runtime = build_production_retrieval_runtime(
            cache_root=Path(self._tmp),
            embedding_alias="gemma",
            embedding_model=components["embedding_model"],
            vector_record_store=components["vector_record_store"],
            dense_index=components["dense_index"],
            sparse_index=components["sparse_index"],
        )
        report = runtime.stage_report()
        self.assertIn("embedding_profile_hash", report)
        self.assertIn("backend", report)
        if is_real_usearch_available():
            # The production-capability-gate reads backend="usearch"
            # to allow the build; the report MUST agree.
            self.assertEqual(report["backend"], "usearch")
            self.assertEqual(report["dense_backend"], "usearch")


class CompositionRefusesProductionStubTests(unittest.TestCase):
    """The composition MUST NOT accept an unknown alias silently."""

    def test_unknown_alias_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_production_retrieval_runtime(
                cache_root=Path(tempfile.mkdtemp()),
                embedding_alias="not-a-real-model",
            )

    def test_semantic_index_service_factory_refuses_flat_backend(self) -> None:
        from pi_platform.adapters.runtime.flat_dense_index import FlatDenseIndex
        profile = EMBEDDINGGEMMA2_512
        flat = FlatDenseIndex()
        flat._embedding_profile_hash = profile.identity()
        with self.assertRaises(Exception):
            build_semantic_index_service(
                embedding_model=CountingEmbeddingModel(profile=profile),
                vector_record_store=InMemoryVectorRecordStore(),
                dense_index=flat,
            )


class VectorRecordStoreFromDbTests(unittest.TestCase):
    """The production :class:`SqliteVectorRecordStore` is wired by
    :func:`vector_record_store_from_db`."""

    def test_round_trip_through_sqlite(self) -> None:
        from pi_platform.adapters.runtime.sqlite_vector_record_store import (
            encode_vector_payload,
            decode_vector_payload,
        )
        from pi_platform.ports.runtime.vector_record_store import (
            VectorRecord,
        )
        path = os.path.join(self._tmp, "v.sqlite")
        store = vector_record_store_from_db(path)
        rec = VectorRecord(
            chunk_id="c1",
            content_hash="abc",
            embedding_profile_hash="ph1",
            model_revision="rev1",
            dimension=4,
            normalization="l2",
            vector_payload=encode_vector_payload(
                [1.0, 2.0, 3.0, 4.0], dtype="f",
            ),
            created_from_retrieval_text_hash="rth",
        )
        store.put(rec)
        got = store.get("c1", "ph1")
        self.assertIsNotNone(got)
        self.assertEqual(got.dimension, 4)
        self.assertEqual(
            decode_vector_payload(got.vector_payload),
            [1.0, 2.0, 3.0, 4.0],
        )

    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="vrs-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(
                self._tmp, ignore_errors=True,
            ),
        )


if __name__ == "__main__":
    unittest.main()
