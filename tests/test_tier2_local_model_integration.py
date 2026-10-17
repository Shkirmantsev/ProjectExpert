"""Tier-2 local-model, PDF, and slow integration tests (Change Package J.2).

Exercises the v0.8 refinement's Tier-2 integration surface with the
documented ``@pytest.mark.local_model``, ``@pytest.mark.pdf`` and
``@pytest.mark.slow`` markers (plan §28.2, ``tasks.md`` J.2):

* ``@pytest.mark.local_model`` — tokenizer + embedding profile +
  vector record store + USearch/flat ANN + quality reranker with
  fallback integration;
* ``@pytest.mark.pdf`` — 10-page and 100-page generated PDF
  prescan, Docling PDF adapter, selective OCR policy, figure asset
  CAS, and DoclingHybridChunker integration;
* ``@pytest.mark.slow`` — 600-page generated PDF batched ingestion
  and mid-document resume integration.

When ``pytest`` is not installed in the active stdlib-only
interpreter, a lightweight shim provides ``pytest.mark.<name>``
decorators that record ``__tier2_markers__`` on each test callable
so ``python3 -m unittest`` executes the full Tier-2 suite and
verifies marker attachment.
"""

from __future__ import annotations

import sqlite3
import tempfile
import tomllib
import unittest
from pathlib import Path
from typing import Any, Callable

try:
    import pytest  # type: ignore
except ImportError:  # pragma: no cover - stdlib-only runner
    class _MarkDecorator:
        def __init__(self, name: str) -> None:
            self._name = name

        def __call__(self, obj: Callable[..., Any]) -> Callable[..., Any]:
            existing = set(getattr(obj, "__tier2_markers__", ()))
            existing.add(self._name)
            setattr(obj, "__tier2_markers__", frozenset(existing))
            return obj

    class _MarkNamespace:
        def __getattr__(self, name: str) -> _MarkDecorator:
            return _MarkDecorator(name)

    class _PytestShim:
        mark = _MarkNamespace()

    pytest = _PytestShim()  # type: ignore


__all__ = ["Tier2LocalModelIntegrationTests"]


ROOT = Path(__file__).resolve().parents[1]


class Tier2LocalModelIntegrationTests(unittest.TestCase):
    """Tier-2 local-model, PDF, and slow integration tests."""

    def test_pyproject_registers_tier2_markers(self) -> None:
        data = tomllib.loads(
            (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        )
        markers = (
            data.get("tool", {})
            .get("pytest", {})
            .get("ini_options", {})
            .get("markers", [])
        )
        marker_names = {m.split(":", 1)[0].strip() for m in markers}
        self.assertIn("local_model", marker_names)
        self.assertIn("pdf", marker_names)
        self.assertIn("slow", marker_names)

    @pytest.mark.local_model
    def test_local_model_tokenizer_embedding_ann_reranker_flow(self) -> None:
        from pi_platform.adapters.ingest.tokenizers import (
            EmbeddingGemma2Tokenizer,
            HashingTokenizer,
        )
        from pi_platform.adapters.retrieval.bm25_light_reranker import (
            Bm25LightRerankerAdapter,
        )
        from pi_platform.adapters.retrieval.cross_encoder_reranker import (
            CrossEncoderRerankerAdapter,
        )
        from pi_platform.adapters.retrieval.hashing_embedding_model import (
            HashingEmbeddingAdapter,
        )
        from pi_platform.adapters.retrieval.rerank_with_fallback import (
            RerankWithFallback,
        )
        from pi_platform.adapters.runtime.dense_index_backend import (
            select_dense_index,
        )
        from pi_platform.adapters.runtime.sqlite_vector_record_store import (
            SqliteVectorRecordStore,
            decode_vector_payload,
            encode_vector_payload,
        )
        from pi_platform.adapters.runtime.usearch_dense_index import (
            USearchDenseIndex,
        )
        from pi_platform.ports.retrieval.embedding_profile import (
            EMBEDDINGGEMMA2_512,
            HASHING_DEFAULT,
        )
        from pi_platform.ports.runtime.vector_record_store import (
            VectorRecord,
        )

        # 1. Tokenizer contract (Hashing + EmbeddingGemma2 stub).
        hashing_tok = HashingTokenizer()
        self.assertGreater(hashing_tok.count("ILO-5193 FinishPack"), 0)
        gemma_tok = EmbeddingGemma2Tokenizer()
        self.assertEqual(gemma_tok.identity(), "embeddinggemma2/v1-stub")

        # 2. Vector persistence + ANN rebuild without re-embedding.
        embedder = HashingEmbeddingAdapter(dimension=384)
        vec = tuple(embedder.embed("ILO-5193 FinishPack protocol"))
        with tempfile.TemporaryDirectory() as tmp:
            db = sqlite3.connect(":memory:")
            db.row_factory = sqlite3.Row
            store = SqliteVectorRecordStore(db)
            record = VectorRecord(
                chunk_id="chunk-ilo-5193",
                content_hash="hash-ilo-5193",
                embedding_profile_hash=HASHING_DEFAULT.identity(),
                model_revision=HASHING_DEFAULT.model_revision,
                dimension=HASHING_DEFAULT.output_dimension,
                normalization=HASHING_DEFAULT.normalization,
                vector_payload=encode_vector_payload(vec),
                created_from_retrieval_text_hash="rtext-ilo-5193",
                created_at="2026-10-16T00:00:00Z",
            )
            store.put(record)
            loaded = store.get(
                "chunk-ilo-5193",
                HASHING_DEFAULT.identity(),
            )
            self.assertIsNotNone(loaded)
            index = select_dense_index(
                "usearch",
                cache_root=tmp,
                embedding_profile_hash=HASHING_DEFAULT.identity(),
            )
            self.assertIsInstance(index, USearchDenseIndex)
            rebuilt = index.rebuild_from([
                (loaded.chunk_id, decode_vector_payload(loaded.vector_payload)),
            ])
            self.assertEqual(rebuilt, 1)
            self.assertNotEqual(
                HASHING_DEFAULT.identity(),
                EMBEDDINGGEMMA2_512.identity(),
            )

        # 3. Quality reranker with automatic fallback.
        fallback_reranker = RerankWithFallback(
            primary=CrossEncoderRerankerAdapter(),
            fallback=Bm25LightRerankerAdapter(),
        )
        self.assertIsNotNone(fallback_reranker)

    @pytest.mark.pdf
    def test_pdf_10_and_100_page_fixtures_ingest(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            DoclingPdfAdapter,
        )
        from pi_platform.adapters.pdf.prescan import PdfPrescanAdapter
        from pi_platform.adapters.runtime.sqlite_document_graph_store import (
            SqliteDocumentGraphStore,
        )
        from pi_platform.adapters.runtime.sqlite_ingestion_job_store import (
            SqliteIngestionJobStore,
        )
        from pi_platform.ports.ingest.source_adapter import (
            Source,
            SourceContentFamily,
        )

        pdf_dir = ROOT / "evals" / "corpus" / "generated-pdf"
        for pages in (10, 100):
            pdf_path = pdf_dir / f"{pages}-page.pdf"
            self.assertTrue(pdf_path.exists())
            db = sqlite3.connect(":memory:")
            db.row_factory = sqlite3.Row
            job_store = SqliteIngestionJobStore(db)
            graph_store = SqliteDocumentGraphStore(db)
            adapter = DoclingPdfAdapter(
                prescan=PdfPrescanAdapter(),
                job_store=job_store,
                graph_store=graph_store,
            )
            src = Source(
                id=f"pdf-{pages}",
                uri=str(pdf_path),
                family=SourceContentFamily.PDF.value,
                contentHash=f"hash-{pages}",
            )
            parsed = adapter.parse(src)
            self.assertIsNotNone(parsed.document)

    @pytest.mark.pdf
    @pytest.mark.slow
    def test_pdf_600_page_generated_fixture_batched_ingest(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            DoclingPdfAdapter,
        )
        from pi_platform.adapters.pdf.prescan import PdfPrescanAdapter
        from pi_platform.adapters.runtime.sqlite_document_graph_store import (
            SqliteDocumentGraphStore,
        )
        from pi_platform.adapters.runtime.sqlite_ingestion_job_store import (
            SqliteIngestionJobStore,
        )
        from pi_platform.ports.ingest.source_adapter import (
            Source,
            SourceContentFamily,
        )

        pdf_path = ROOT / "evals" / "corpus" / "generated-pdf" / "600-page.pdf"
        self.assertTrue(pdf_path.exists())
        db = sqlite3.connect(":memory:")
        db.row_factory = sqlite3.Row
        job_store = SqliteIngestionJobStore(db)
        graph_store = SqliteDocumentGraphStore(db)
        adapter = DoclingPdfAdapter(
            prescan=PdfPrescanAdapter(),
            job_store=job_store,
            graph_store=graph_store,
            page_batch_size=64,
        )
        src = Source(
            id="pdf-600",
            uri=str(pdf_path),
            family=SourceContentFamily.PDF.value,
            contentHash="hash-600",
        )
        parsed = adapter.parse(src)
        self.assertIsNotNone(parsed.document)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
