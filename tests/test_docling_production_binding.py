"""Opt-in real PDF inference acceptance; model/dependency failures are failures.

PI_RUN_PDF_TESTS=1 enables downloads/inference. No fabricated fixtures are
returned by the adapter. These tests require the documents dependency and
Docling OCR/layout assets; they do not turn load errors into skips.
"""
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from pi_platform.adapters.pdf.docling_pdf_adapter import build_real_docling_pdf_adapter
from pi_platform.adapters.pdf.prescan import PdfPrescanAdapter
from pi_platform.adapters.runtime.sqlite_document_graph_store import SqliteDocumentGraphStore
from pi_platform.adapters.runtime.sqlite_ingestion_job_store import SqliteIngestionJobStore
from pi_platform.core.canonical.document_graph import ElementKind
from pi_platform.ports.ingest.source_adapter import Source, SourceContentFamily
from scripts.generate_pdf_fixtures import build_pdf, _render_pdf


def rich_native_pdf(*, product="Widget", amount="42"):
    """Encode native cells plus a real embedded chart, rather than a manifest."""
    import zlib
    from PIL import Image, ImageDraw
    chart = Image.new("RGB", (240, 160), "white")
    draw = ImageDraw.Draw(chart)
    for x, height in ((30, 60), (90, 110), (150, 85)):
        draw.rectangle((x, 150 - height, x + 35, 150), fill="blue")
    pixels = zlib.compress(chart.tobytes())
    commands = ["BT /F1 18 Tf 72 740 Td (Quarterly production report) Tj ET"]
    for y in (690, 650, 610, 570):
        commands.append(f"72 {y} m 500 {y} l S")
    for x in (72, 285, 500):
        commands.append(f"{x} 570 m {x} 690 l S")
    for y, values in ((665, ("Product", "Amount")), (625, (product, amount)), (585, ("Gadget", "81"))):
        for x, value in zip((85, 300), values):
            commands.append(f"BT /F1 16 Tf {x} {y} Td ({value}) Tj ET")
    commands.extend(["q 360 0 0 240 100 230 cm /Im1 Do Q",
                     "BT /F1 14 Tf 100 205 Td (Figure 1: Quarterly output chart) Tj ET"])
    content = ("\n".join(commands) + "\n").encode()
    return _render_pdf([
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n",
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> /XObject << /Im1 6 0 R >> >> >> endobj\n",
        f"4 0 obj << /Length {len(content)} >> stream\n".encode() + content + b"endstream endobj\n",
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n",
        f"6 0 obj << /Type /XObject /Subtype /Image /Width 240 /Height 160 /ColorSpace /DeviceRGB "
        f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(pixels)} >> stream\n".encode()
        + pixels + b"\nendstream endobj\n",
    ])


def scanned_pdf():
    import io
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1200, 1600), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=44)
    draw.text((80, 150), "SCANNED PROJECTEXPERT REPORT", fill="black", font=font)
    draw.text((80, 240), "Portable document processing works.", fill="black", font=font)
    buf = io.BytesIO()
    image.save(buf, format="PDF", resolution=144)
    return buf.getvalue()


def join_pdf_pages(*parts):
    import io
    import pypdfium2 as pdfium
    merged = pdfium.PdfDocument.new()
    try:
        for data in parts:
            source = pdfium.PdfDocument(data)
            try:
                merged.import_pages(source)
            finally:
                source.close()
        output = io.BytesIO()
        merged.save(output)
        return output.getvalue()
    finally:
        merged.close()


@unittest.skipUnless(os.environ.get("PI_RUN_PDF_TESTS") == "1", "set PI_RUN_PDF_TESTS=1 for real PDF inference")
class DoclingProductionBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.graph = SqliteDocumentGraphStore(self.db)
        self.jobs = SqliteIngestionJobStore(self.db)
        self.adapter = build_real_docling_pdf_adapter(
            PdfPrescanAdapter(), self.jobs, self.graph, page_batch_size=16,
            boundary_context_pages=0, asset_root=self.temp.name)

    def parse(self, name, data):
        path = Path(self.temp.name) / name
        path.write_bytes(data)
        source = Source(id=name, uri=str(path), contentHash="pending", family=SourceContentFamily.PDF)
        return self.adapter.parse(source)

    def test_native_long_document_converts_actual_page_text(self):
        count = int(os.environ.get("PI_DOCLING_LONG_PAGES", "100"))
        self.assertGreaterEqual(count, 100)
        windows = []
        convert = self.adapter._docling_converter.convert
        def observe(*args, **kwargs):
            windows.append(kwargs["page_range"])
            return convert(*args, **kwargs)
        self.adapter._docling_converter.convert = observe
        parsed = self.parse("long.pdf", build_pdf(page_count=count, title="REAL NATIVE ACCEPTANCE"))
        self.assertEqual(len(windows), (count + 15) // 16)
        self.assertTrue(all(last - first + 1 <= 16 for first, last in windows))
        import json
        metrics = {"pages": count, "windows": len(windows), "max_window_pages":
                   max(last - first + 1 for first, last in windows)}
        try:
            import resource
            import sys
            metrics["max_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (
                1024 if sys.platform == "darwin" else 1)
        except ImportError:
            metrics["max_rss_kib"] = None
        print("PDF_RESOURCE_PROOF=" + json.dumps(metrics), flush=True)
        self.assertEqual(len(self.graph.list_pages(parsed.document.id)), count)
        chunks = [c for s in parsed.sections for c in s.chunks]
        self.assertTrue(any("REAL NATIVE ACCEPTANCE" in c.rawText for c in chunks))
        self.assertTrue(any(f"Page {count}" in c.rawText for c in chunks))
        self.assertTrue(all(c.anchors for c in chunks))

    def test_native_table_cells_and_real_picture_are_mapped(self):
        parsed = self.parse("rich.pdf", rich_native_pdf())
        elements = self.graph.list_elements(parsed.document.id)
        tables = [e for e in elements if e.kind == ElementKind.TABLE]
        self.assertTrue(tables, "real layout inference must detect the encoded table")
        self.assertTrue(any("Widget" in e.text and "42" in e.text for e in tables))
        figures = [e for e in elements if e.kind == ElementKind.FIGURE]
        self.assertTrue(figures, "real layout inference must detect the embedded chart")
        self.assertTrue(any(self.graph.get_asset(e.element_id) for e in figures))

    def test_scanned_pdf_uses_real_ocr(self):
        parsed = self.parse("scanned.pdf", scanned_pdf())
        text = "\n".join(c.rawText for s in parsed.sections for c in s.chunks).upper()
        self.assertIn("PROJECTEXPERT", text)
        pages = self.graph.list_pages(parsed.document.id)
        self.assertTrue(pages[0].ocr_used)
        self.assertFalse(pages[0].native_text_present)

    def test_mixed_native_and_scanned_pages_preserve_selective_ocr(self):
        parsed = self.parse("mixed.pdf", join_pdf_pages(
            build_pdf(page_count=1, title="NATIVE MIXED PAGE"), scanned_pdf()))
        pages = self.graph.list_pages(parsed.document.id)
        self.assertEqual([page.native_text_present for page in pages], [True, False])
        self.assertEqual([page.ocr_used for page in pages], [False, True])
        text = "\n".join(c.rawText for section in parsed.sections for c in section.chunks).upper()
        self.assertIn("NATIVE MIXED PAGE", text)
        self.assertIn("PROJECTEXPERT", text)

    def test_multi_page_table_headers_survive_real_conversion_and_runtime_splits(self):
        from unittest.mock import patch
        from tokenizers import Tokenizer, models, pre_tokenizers
        from transformers import PreTrainedTokenizerFast
        from pi_platform.adapters.pdf.real_docling import HuggingFaceTokenizerAdapter
        from pi_platform.adapters.pdf.docling_chunker import DoclingHybridChunker
        parsed = self.parse("tables.pdf", join_pdf_pages(
            rich_native_pdf(), rich_native_pdf(product="Gizmo", amount="95")))
        elements = self.graph.list_elements(parsed.document.id)
        tables = [element for element in elements if element.kind == ElementKind.TABLE]
        self.assertEqual({element.page for element in tables}, {1, 2})
        self.assertTrue(any("Widget" in element.text for element in tables))
        self.assertTrue(any("Gizmo" in element.text for element in tables))
        local = Tokenizer(models.WordLevel({"[UNK]": 0}, unk_token="[UNK]"))
        local.pre_tokenizer = pre_tokenizers.Whitespace()
        tokenizer = PreTrainedTokenizerFast(tokenizer_object=local, unk_token="[UNK]")
        with patch.object(HuggingFaceTokenizerAdapter, "_load_pre_trained_tokenizer", return_value=tokenizer):
            chunks = DoclingHybridChunker(max_tokens=20).chunk(parsed.document, parsed.sections)
        rows = [chunk for chunk in chunks if "Widget" in chunk.rawText or "Gizmo" in chunk.rawText]
        self.assertGreaterEqual(len(rows), 2)
        self.assertTrue(all("Product" in chunk.rawText and "Amount" in chunk.rawText for chunk in rows))
        self.assertTrue(all(len(tokenizer.encode(chunk.rawText)) <= 20 for chunk in rows))


@unittest.skipUnless(os.environ.get("PI_RUN_PDF_TESTS") == "1" and
                     os.environ.get("PI_RUN_MODEL_TESTS") == "1",
                     "enable real PDF and embedding acceptance")
class PdfRepositoryProductionTests(unittest.TestCase):
    def test_real_pdf_runtime_projection_indexes_with_real_embedding_and_native_ann(self):
        import hashlib
        from unittest.mock import patch
        from pi_platform.core.control.retrieval_settings import RetrievalSettings
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        from pi_platform.core.orchestration.repository_indexing import index_repository
        from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
        from pi_platform.adapters.pdf.runtime_projection import PdfRuntimeProjection
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "report.pdf").write_bytes(rich_native_pdf())
            original = (root / "report.pdf").read_bytes()
            calls = []
            project = PdfRuntimeProjection.__call__
            def observe(projection, body):
                result = project(projection, body)
                calls.append((body["id"], result))
                return result
            with patch.dict(os.environ, {"PI_STARTUP_PROFILE": "production",
                    "PI_EMBEDDING_MODEL": "gemma", "PI_EMBEDDING_DEVICE": "cpu",
                    "PI_DENSE_INDEX": "usearch", "PI_DOCLING_ENABLED": "1"}), patch.object(
                        PdfRuntimeProjection, "__call__", new=observe):
                discovery = RepositorySourceDiscovery()
                def build():
                    return index_repository(target=root, cache_root=root / ".project-intelligence-cache",
                        inventory=discovery.discover(root), previous_inventory=None,
                        settings=RetrievalSettings())
                first = build()
                self.assertTrue(calls, "the production PDF path must invoke actual HybridChunker projection")
                self.assertTrue(all(segments for _, segments in calls))
                self.assertEqual(first.backend_name, "usearch")
                self.assertGreater(first.extra["indexing_report"].embedded_count, 0)
                self.assertTrue(first.multi_stage_retrieval.retrieve(RetrievalQuery(text="Widget amount 42")).hits)
                pdf_hits = [hit for hit in first.extra["chunk_catalog"].values()
                            if hit.metadata.sourcePath.endswith(".pdf")]
                self.assertTrue(pdf_hits)
                self.assertTrue(all(hit.metadata.page == 1 for hit in pdf_hits))
                ids = first.extra["chunk_ids"]
                second = build()
                self.assertEqual(second.extra["chunk_ids"], ids)
                self.assertEqual(second.extra["indexing_report"].embedded_count, 0)
                self.assertGreater(second.extra["indexing_report"].reused_count, 0)
            self.assertEqual(original, (root / "report.pdf").read_bytes())
            self.assertFalse((root / "project-knowledge").exists())
