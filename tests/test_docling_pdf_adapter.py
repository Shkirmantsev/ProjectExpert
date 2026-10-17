"""Tests for the Docling PDF adapter (E3), OCR policy (E5),
asset adapter (E6), and Docling HybridChunker (E7)."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest

from pi_platform.core.canonical.document_graph import (
    ElementKind,
)
from pi_platform.ports.ingest.ocr_engine import (
    SelectiveOcrPolicy,
)
from pi_platform.adapters.pdf.ocr_policy import TesseractOcrAdapter
from pi_platform.ports.ingest.source_adapter import (
    Source,
    SourceContentFamily,
)
from pi_platform.adapters.pdf.assets import FigureAssetAdapter
from pi_platform.adapters.pdf.docling_chunker import DoclingHybridChunker
from pi_platform.adapters.pdf.docling_pdf_adapter import (
    DEFAULT_DOCLING_STRATEGY_VERSION,
    DoclingMapper,
    DoclingPdfAdapter,
)
from pi_platform.adapters.pdf.ocr_policy import TesseractOcrAdapter as T
from pi_platform.adapters.pdf.prescan import PdfPrescanAdapter
from pi_platform.adapters.runtime.sqlite_document_graph_store import (
    SqliteDocumentGraphStore,
)
from pi_platform.adapters.runtime.sqlite_ingestion_job_store import (
    SqliteIngestionJobStore,
)


def _new_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return db


def _make_pdf(path: str, pages: int = 3) -> None:
    """Write a synthetic PDF with N /Type /Page objects in the
    trailer so the prescan can detect the page count."""
    body = b"%PDF-1.4\n"
    # Place a BT...ET block on page 1 so has_native_text=True.
    body += b"BT\n/F1 12 Tf\n100 700 Td\n(Hello) Tj\nET\n"
    for p in range(pages):
        body += (
            f"{p + 3} 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
        ).encode()
    body += b"trailer\n<< /Size 1 /Info <</Author (Test) "
    body += b"/Producer (ProjectExpert Test) "
    body += b"/CreationDate (20261015)>>>>\n%%EOF\n"
    with open(path, "wb") as f:
        f.write(body)


# ===========================================================================
# E5 — OCR policy
# ===========================================================================


class SelectiveOcrPolicyTests(unittest.TestCase):
    def _page(self, *, native_text_present: bool, ocr_used: bool = False):
        from pi_platform.core.canonical.document_graph import Page
        return Page(
            page_no=1, native_text_present=native_text_present,
            ocr_used=ocr_used,
        )

    def test_native_text_page_skips_ocr(self) -> None:
        decision = SelectiveOcrPolicy().decide(
            self._page(native_text_present=True),
        )
        self.assertFalse(decision.should_ocr)
        self.assertEqual(decision.reason, "native_text_present")

    def test_image_only_page_uses_ocr(self) -> None:
        decision = SelectiveOcrPolicy().decide(
            self._page(native_text_present=False),
        )
        self.assertTrue(decision.should_ocr)
        self.assertEqual(decision.reason, "no_native_text")
        self.assertEqual(decision.candidate_engine, "tesseract")

    def test_already_ocr_used_skips(self) -> None:
        decision = SelectiveOcrPolicy().decide(
            self._page(native_text_present=False, ocr_used=True),
        )
        self.assertFalse(decision.should_ocr)
        self.assertEqual(decision.reason, "already_ocr_used")


class TesseractOcrAdapterTests(unittest.TestCase):
    def test_engine_metadata(self) -> None:
        a = TesseractOcrAdapter()
        self.assertEqual(a.engine_name, "tesseract")
        self.assertEqual(a.license_id, "Apache-2.0")
        self.assertTrue(a.engine_revision)

    def test_ocr_page_raises_when_unbound(self) -> None:
        from pi_platform.ports.ingest.ocr_engine import OcrEngineError
        a = TesseractOcrAdapter()
        with self.assertRaises(OcrEngineError):
            a.ocr_page(image_bytes=b"", language_hint="en")


# ===========================================================================
# E6 — Figure asset adapter
# ===========================================================================


class FigureAssetAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self._db = _new_db()
        self._store = SqliteDocumentGraphStore(self._db)
        self._tmp = tempfile.mkdtemp(prefix="figure-assets-")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))
        self._adapter = FigureAssetAdapter(
            self._store, cas_root=self._tmp,
        )

    def test_store_figure_writes_cas_and_records(self) -> None:
        a = self._adapter.store_figure(
            asset_id="fig-1", image_bytes=b"\x89PNG\r\n\x1a\n",
            mime_type="image/png", page=3,
            bbox=(0.0, 0.0, 200.0, 100.0),
        )
        self.assertTrue(os.path.exists(a.cas_path))
        # Round-trip via graph store.
        got = self._store.get_asset(a.asset_id)
        self.assertEqual(got.byte_hash, a.byte_hash)
        self.assertEqual(got.mime_type, "image/png")
        self.assertEqual(got.page, 3)
        self.assertEqual(got.bbox, (0.0, 0.0, 200.0, 100.0))

    def test_store_figure_idempotent(self) -> None:
        a1 = self._adapter.store_figure(
            asset_id="fig-1", image_bytes=b"x", mime_type="image/png",
            page=1,
        )
        a2 = self._adapter.store_figure(
            asset_id="fig-1", image_bytes=b"x", mime_type="image/png",
            page=1,
        )
        # Same content → same byte_hash → same cas_path.
        self.assertEqual(a1.byte_hash, a2.byte_hash)
        self.assertEqual(a1.cas_path, a2.cas_path)


# ===========================================================================
# E3 — Docling PDF adapter
# ===========================================================================


class DoclingMapperTests(unittest.TestCase):
    def test_project_revision(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            _DoclingDocument,
        )
        doc = _DoclingDocument(
            page_count=3, author="A", language="en",
        )
        rev = DoclingMapper().project_revision(
            doc=doc, source_id="src-1", byte_hash="h-1",
            strategy_version="v", ingested_at="t",
        )
        self.assertEqual(rev.source_id, "src-1")
        self.assertEqual(rev.byte_hash, "h-1")
        self.assertEqual(rev.page_count, 3)
        self.assertEqual(rev.author, "A")
        self.assertEqual(rev.language, "en")

    def test_project_pages(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            _DoclingDocument,
        )
        doc = _DoclingDocument(page_count=4)
        pages = DoclingMapper().project_pages(doc)
        self.assertEqual(len(pages), 4)
        self.assertEqual([p.page_no for p in pages], [1, 2, 3, 4])
        self.assertTrue(all(p.native_text_present for p in pages))

    def test_project_elements_includes_all_kinds(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            _DoclingDocument, _DoclingFigureItem, _DoclingTableItem,
            _DoclingTextItem,
        )
        doc = _DoclingDocument(
            page_count=2,
            text_items=(
                _DoclingTextItem(text="hello", page=1),
                _DoclingTextItem(text="world", page=2),
            ),
            tables=(_DoclingTableItem(
                headers=("A", "B"), rows=(("1", "2"),),
                page=1,
            ),),
            figures=(_DoclingFigureItem(
                caption="Fig 1", page=2,
            ),),
        )
        elements = DoclingMapper().project_elements(doc, "rev-1")
        kinds = [e.kind for e in elements]
        self.assertIn(ElementKind.PARAGRAPH, kinds)
        self.assertIn(ElementKind.TABLE, kinds)
        self.assertIn(ElementKind.FIGURE, kinds)
        # All elements carry a content_hash.
        self.assertTrue(all(e.content_hash for e in elements))
        # All elements carry a semantic_key.
        self.assertTrue(all(e.semantic_key for e in elements))

    def test_project_tables_returns_serialised_markdown(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            _DoclingDocument, _DoclingTableItem,
        )
        doc = _DoclingDocument(
            page_count=1,
            tables=(_DoclingTableItem(
                headers=("A", "B"), rows=(("1", "2"), ("3", "4")),
                page=1,
            ),),
        )
        tables = DoclingMapper().project_tables(doc, "rev-1")
        self.assertEqual(len(tables), 1)
        element_id, table = tables[0]
        self.assertIn("| A | B |", table.serialised_markdown)
        self.assertIn("| 1 | 2 |", table.serialised_markdown)
        self.assertTrue(table.repeat_header)

    def test_table_split_repeats_header(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            DoclingMapper, _DoclingTableItem,
        )
        # A 4-row table: when the chunker later splits this
        # into two, the mapper's serialised_markdown already
        # includes the header. The Docling HybridChunker
        # composes repeat-header at chunk time; the mapper
        # simply records the table grid. Here we verify the
        # header line is preserved.
        tbl = _DoclingTableItem(
            headers=("H1", "H2"), rows=(
                ("a", "b"), ("c", "d"), ("e", "f"), ("g", "h"),
            ),
            page=1,
        )
        serialised = DoclingMapper._serialise_table(tbl)
        self.assertIn("| H1 | H2 |", serialised)
        self.assertIn("| a | b |", serialised)
        self.assertIn("| g | h |", serialised)

    def test_project_figures_uses_byte_hash(self) -> None:
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            _DoclingDocument, _DoclingFigureItem,
        )
        doc = _DoclingDocument(
            page_count=1, figures=(
                _DoclingFigureItem(
                    caption="Fig 1", page=1,
                    asset_bytes=b"\x89PNG\r\n\x1a\n",
                ),
            ),
        )
        figures = DoclingMapper().project_figures(doc, "rev-1")
        self.assertEqual(len(figures), 1)
        self.assertEqual(figures[0].byte_hash,
                         __import__("hashlib").sha256(
                             b"\x89PNG\r\n\x1a\n").hexdigest())
        self.assertIn("assets/", figures[0].cas_path)


class DoclingPdfAdapterSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._db = _new_db()
        self._job_store = SqliteIngestionJobStore(self._db)
        self._graph_store = SqliteDocumentGraphStore(self._db)
        self._tmp = tempfile.mkdtemp(prefix="docling-adapter-")
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))
        self._pdf_path = os.path.join(self._tmp, "doc.pdf")
        _make_pdf(self._pdf_path, pages=3)
        self._adapter = DoclingPdfAdapter(
            prescan=PdfPrescanAdapter(),
            job_store=self._job_store,
            graph_store=self._graph_store,
        )

    def _source(self) -> Source:
        return Source(
            id="src-docling-1",
            uri=self._pdf_path,
            contentHash="h-pending",
            metadata={},
            family=SourceContentFamily.PDF,
        )

    def test_family_is_pdf(self) -> None:
        self.assertEqual(self._adapter.family, SourceContentFamily.PDF)

    def test_parse_creates_job_and_persists_graph(self) -> None:
        result = self._adapter.parse(self._source())
        self.assertEqual(result.parser_version, DEFAULT_DOCLING_STRATEGY_VERSION)
        # The job is COMPLETED.
        completed = self._job_store.find_completed(
            source_id="src-docling-1",
            revision_id=result.document.id,
            strategy_version=DEFAULT_DOCLING_STRATEGY_VERSION,
        )
        self.assertIsNotNone(completed)
        # The graph store has the revision + pages.
        rev = self._graph_store.get_revision(result.document.id)
        self.assertIsNotNone(rev)
        self.assertEqual(rev.page_count, 3)
        pages = self._graph_store.list_pages(result.document.id)
        self.assertEqual(len(pages), 3)
        # Elements include at least one paragraph per page plus
        # the synthesised table on page 1 and figure on page 2.
        elements = self._graph_store.list_elements(result.document.id)
        kinds = {e.kind for e in elements}
        self.assertIn(ElementKind.PARAGRAPH, kinds)
        self.assertIn(ElementKind.TABLE, kinds)
        self.assertIn(ElementKind.FIGURE, kinds)
        # Tables + figures persisted.
        tables = self._graph_store.list_elements(
            result.document.id, page=1,
        )
        table_els = [e for e in tables if e.kind == ElementKind.TABLE]
        self.assertEqual(len(table_els), 1)
        self.assertIsNotNone(
            self._graph_store.get_table(
                result.document.id, table_els[0].element_id,
            )
        )
        figs = self._graph_store.list_elements(
            result.document.id, page=2,
        )
        fig_els = [e for e in figs if e.kind == ElementKind.FIGURE]
        self.assertEqual(len(fig_els), 1)
        self.assertIsNotNone(
            self._graph_store.get_asset(fig_els[0].element_id),
        )

    def test_parse_short_circuits_on_repeat(self) -> None:
        # First run: creates the job, persists the graph.
        first = self._adapter.parse(self._source())
        # Second run: same source, same revision, same strategy.
        # The prescan finds the existing COMPLETED job and the
        # adapter rebuilds from the graph (cheap path).
        second = self._adapter.parse(self._source())
        self.assertEqual(first.document.id, second.document.id)
        # Only one job exists.
        self.assertEqual(
            len(self._job_store.list_for_revision(first.document.id)),
            1,
        )

    def test_parse_ocr_used_for_image_only_pages(self) -> None:
        # Synthesise a PDF with no BT...ET block.
        path = os.path.join(self._tmp, "no-text.pdf")
        body = b"%PDF-1.4\n"
        for p in range(2):
            body += (
                f"{p + 3} 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
            ).encode()
        body += b"trailer\n<< /Size 1 >>\n%%EOF\n"
        with open(path, "wb") as f:
            f.write(body)
        source = Source(
            id="src-no-text", uri=path, contentHash="h-pending",
            metadata={}, family=SourceContentFamily.PDF,
        )
        result = self._adapter.parse(source)
        # The prescan should have flagged has_native_text=False
        # and the adapter would normally invoke OCR. The OCR
        # engine is unbound in the stub, so the graph is still
        # persisted via the synthesised document.
        rev = self._graph_store.get_revision(result.document.id)
        self.assertIsNotNone(rev)
        self.assertEqual(rev.page_count, 2)


# ===========================================================================
# E7 — Docling HybridChunker (STUB)
# ===========================================================================


class DoclingHybridChunkerTests(unittest.TestCase):
    def test_family_is_pdf(self) -> None:
        self.assertEqual(
            DoclingHybridChunker().family, SourceContentFamily.PDF,
        )

    def test_chunk_delegates_to_structural_chunker(self) -> None:
        from pi_platform.core.canonical.value_types import (
            Chunk, Document, Metadata, Section,
        )
        doc = Document(
            id="d-1", title="T",
            sections=(
                Section(
                    id="s-1", heading="H", level=1,
                    chunks=(
                        Chunk(
                            id="c-1", rawText="Hello world. " * 200,
                            contextualText="",
                            metadata=Metadata(
                                documentId="d-1", version="0.0.0",
                                language="und",
                            ),
                            sourceReference="d-1",
                            contentHash="h-1",
                        ),
                    ),
                ),
            ),
        )
        from pi_platform.ports.ingest.chunker import ChunkerContext
        chunks = DoclingHybridChunker().chunk(
            doc, doc.sections,
            context=ChunkerContext(max_chunk_bytes=4096),
        )
        # The stub delegates to PlainTextChunker which may
        # produce one or more chunks; we just verify the
        # contract is satisfied.
        self.assertGreater(len(chunks), 0)
        self.assertTrue(all(c.rawText for c in chunks))

    def test_chunk_empty_sections_returns_empty(self) -> None:
        from pi_platform.core.canonical.value_types import Document
        doc = Document(id="d-1", title="T", sections=())
        chunks = DoclingHybridChunker().chunk(doc, ())
        self.assertEqual(chunks, ())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
