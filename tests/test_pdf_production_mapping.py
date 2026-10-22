"""Production PDF regressions, independent of downloaded model weights."""
import io
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from pi_platform.adapters.pdf.docling_pdf_adapter import DoclingPdfAdapter, DoclingPdfAdapterError
from pi_platform.adapters.pdf.real_docling import RealDoclingConverter, RealDoclingConverterError, is_docling_available
from pi_platform.adapters.runtime.sqlite_document_graph_store import SqliteDocumentGraphStore
from pi_platform.adapters.runtime.sqlite_ingestion_job_store import SqliteIngestionJobStore
from pi_platform.ports.ingest.prescan import PrescanResult
from pi_platform.ports.ingest.source_adapter import Source, SourceContentFamily
from pi_platform.core.canonical.document_graph import ElementKind, IngestionState


def vendor_document(page):
    from docling_core.types.doc import (
        DoclingDocument, DocItemLabel, ProvenanceItem, BoundingBox, TableData,
        TableCell, ImageRef,
    )
    from PIL import Image
    doc = DoclingDocument(name="vendor")
    prov = ProvenanceItem(page_no=page, bbox=BoundingBox(l=10, t=20, r=100, b=120), charspan=(0, 5))
    doc.add_text(label=DocItemLabel.TEXT, text=f"Actual source page {page}", prov=prov)
    cells = [TableCell(text=value, column_header=r == 0,
                      start_row_offset_idx=r, end_row_offset_idx=r + 1,
                      start_col_offset_idx=c, end_col_offset_idx=c + 1)
             for r, row in enumerate((("Product", "Amount"), ("Widget", "42")))
             for c, value in enumerate(row)]
    doc.add_table(data=TableData(num_rows=2, num_cols=2, table_cells=cells), prov=prov)
    caption = doc.add_text(label=DocItemLabel.CAPTION, text="Source chart", prov=prov)
    doc.add_picture(image=ImageRef.from_pil(Image.new("RGB", (4, 4), "blue"), dpi=72),
                    caption=caption, prov=prov)
    return doc


@unittest.skipUnless(is_docling_available(), "documents optional dependencies unavailable")
class PdfProductionMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.graph = SqliteDocumentGraphStore(self.db)
        self.jobs = SqliteIngestionJobStore(self.db)
        self.prescan = NS(scan=lambda _: PrescanResult(page_count=3, byte_hash="a" * 64,
                                                     file_size=200, has_native_text=True))
        self.source = Source(id="pdf-source", uri="/project/real.pdf", contentHash="pending",
                             family=SourceContentFamily.PDF)

    def adapter(self, converter):
        return DoclingPdfAdapter(self.prescan, self.jobs, self.graph,
            docling_converter=converter, page_batch_size=1, boundary_context_pages=0,
            asset_root=self.temp.name)

    def test_vendor_cells_geometry_figures_and_chunk_text_are_preserved(self):
        calls = []
        def convert(path, *, page_range, do_ocr):
            calls.append((page_range, do_ocr))
            return vendor_document(page_range[0])
        parsed = self.adapter(NS(convert=convert)).parse(self.source)
        self.assertEqual(calls, [((1, 1), False), ((2, 2), False), ((3, 3), False)])
        elements = self.graph.list_elements(parsed.document.id)
        tables = [e for e in elements if e.kind == ElementKind.TABLE]
        table = self.graph.get_table(parsed.document.id, tables[0].element_id)
        self.assertEqual(table.headers, ("Product", "Amount"))
        self.assertEqual(table.rows, (("Widget", "42"),))
        self.assertEqual(tables[0].bbox, (10., 20., 100., 120.))
        figures = [e for e in elements if e.kind == ElementKind.FIGURE]
        self.assertEqual(len(figures), 3)
        asset = self.graph.get_asset(figures[0].element_id)
        self.assertTrue(Path(asset.cas_path).read_bytes().startswith(b"\x89PNG"))
        self.assertTrue(any("Widget" in c.rawText for s in parsed.sections for c in s.chunks))
        self.assertTrue(all(c.anchors and c.metadata.sourcePath == self.source.uri
                            for s in parsed.sections for c in s.chunks))

    def test_failure_never_fabricates_and_resumes_after_committed_pages(self):
        calls = []
        fail = [True]
        def convert(path, *, page_range, do_ocr):
            calls.append(page_range)
            if page_range[0] == 2 and fail[0]:
                raise ValueError("broken layout")
            return vendor_document(page_range[0])
        adapter = self.adapter(NS(convert=convert))
        with self.assertRaisesRegex(DoclingPdfAdapterError, "real.pdf.*pages 2-2.*broken layout"):
            adapter.parse(self.source)
        job = self.jobs.list_for_source(self.source.id)[0]
        self.assertEqual(job.state, IngestionState.FAILED_RETRYABLE)
        self.assertEqual(job.next_page, 2)
        self.assertEqual(len(self.graph.list_pages("a" * 64)), 1)
        fail[0] = False
        result = adapter.parse(self.source)
        self.assertEqual(calls, [(1, 1), (2, 2), (2, 2), (3, 3)])
        self.assertEqual(len(self.graph.list_pages(result.document.id)), 3)
        before = list(calls)
        adapter.parse(self.source)
        self.assertEqual(calls, before)

    def test_authoritative_page_inspection_reads_generated_real_pdf(self):
        from scripts.generate_pdf_fixtures import build_pdf
        path = Path(self.temp.name) / "native.pdf"
        path.write_bytes(build_pdf(page_count=7, title="Native PDF regression"))
        converter = RealDoclingConverter()
        layers = converter.inspect_pdf(str(path))
        self.assertEqual(len(layers), 7)
        self.assertTrue(all(layers))

    def test_tokenizer_cache_copy_is_removed_on_success_and_failure(self):
        import json
        from unittest.mock import patch
        from pi_platform.adapters.pdf.real_docling import HuggingFaceTokenizerAdapter
        cache = Path(self.temp.name) / ".cache/huggingface/hub/models--unit--test/snapshots/revision"
        cache.mkdir(parents=True)
        (cache / "tokenizer_config.json").write_text(json.dumps({"extra_special_tokens": []}))
        (cache / "tokenizer.json").write_text("{}")
        adapter = object.__new__(HuggingFaceTokenizerAdapter)
        adapter.tokenizer_id = "unit/test"
        directories = []
        def load(path):
            directories.append(Path(path))
            self.assertTrue(Path(path).is_dir())
            return object()
        with patch("huggingface_hub.snapshot_download", return_value=str(cache)), patch(
                "transformers.PreTrainedTokenizerFast.from_pretrained", side_effect=load):
            adapter._load_tokenizer_from_cache()
        self.assertTrue(directories)
        self.assertTrue(all(not path.exists() for path in directories))
        def fail(path):
            directories.append(Path(path))
            raise ValueError("bad tokenizer")
        with patch("huggingface_hub.snapshot_download", return_value=str(cache)), patch(
                "transformers.PreTrainedTokenizerFast.from_pretrained", side_effect=fail):
            with self.assertRaisesRegex(ValueError, "bad tokenizer"):
                adapter._load_tokenizer_from_cache()
        self.assertTrue(all(not path.exists() for path in directories))

    def test_legacy_synthetic_graph_is_not_reused(self):
        from pi_platform.core.canonical.document_graph import DocumentRevision
        self.graph.put_revision(DocumentRevision(revision_id="a" * 64,
            source_id=self.source.id, byte_hash="a" * 64, strategy_version="docling-pdf/v1",
            ingested_at="then", page_count=3))
        def forbidden(*args, **kwargs):
            self.fail("legacy graph must be rejected before appending real elements")
        with self.assertRaisesRegex(DoclingPdfAdapterError, "incompatible cached graph"):
            self.adapter(NS(convert=forbidden)).parse(self.source)

    def test_assets_use_only_inventoried_immutable_revisions(self):
        import json
        from unittest.mock import patch
        from pi_platform.adapters.pdf.real_docling import (
            _pinned_pdf_assets, DOCLING_LAYOUT_REVISION, DOCLING_TABLE_REVISION,
            DOCLING_OCR_REVISION,
        )
        snapshot = Path(self.temp.name) / "snapshot"
        snapshot.mkdir()
        with patch.dict("os.environ", {"PI_DOCLING_CACHE": str(Path(self.temp.name) / "cache")}), patch(
                "huggingface_hub.snapshot_download", return_value=str(snapshot)) as fetch:
            artifacts, ocr = _pinned_pdf_assets(do_ocr=True)
        expected = {
            "docling-project/docling-layout-heron": DOCLING_LAYOUT_REVISION,
            "docling-project/docling-models": DOCLING_TABLE_REVISION,
            "SWHL/RapidOCR": DOCLING_OCR_REVISION,
        }
        self.assertEqual({call.kwargs["repo_id"]: call.kwargs["revision"]
                          for call in fetch.call_args_list}, expected)
        self.assertEqual(len(ocr), 3)
        self.assertTrue((artifacts / "docling-project--docling-layout-heron").is_dir())
        inventory = json.loads((Path(__file__).resolve().parents[1] /
            "distribution/licenses/model-licenses.json").read_text())
        for model in inventory["models"]:
            if model["model_id"] in expected:
                self.assertEqual(model["revision"], expected.pop(model["model_id"]))
                self.assertTrue(model["document_processing_enabled"])
                self.assertNotEqual(model["spdx"], "NOASSERTION")
        self.assertFalse(expected, "every selected PDF checkpoint must be inventoried")

    def test_runtime_projection_uses_real_chunker_without_mutating_canonical_body(self):
        import copy
        from dataclasses import asdict
        from unittest.mock import patch
        from tokenizers import Tokenizer, models, pre_tokenizers
        from transformers import PreTrainedTokenizerFast
        from pi_platform.adapters.pdf.real_docling import HuggingFaceTokenizerAdapter
        from pi_platform.adapters.pdf.runtime_projection import PdfRuntimeProjection
        parsed = self.adapter(NS(convert=lambda _, **kw: vendor_document(kw["page_range"][0]))).parse(self.source)
        body = asdict(next(c for section in parsed.sections for c in section.chunks
                           if "Actual source" in c.rawText))
        body["rawText"] = "Actual source " * 80
        original = copy.deepcopy(body)
        tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0, "Actual": 1}, unk_token="[UNK]"))
        tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
        local = PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]")
        with patch.object(HuggingFaceTokenizerAdapter, "_load_pre_trained_tokenizer", return_value=local) as load:
            projection = PdfRuntimeProjection("offline-model", max_tokens=16)
            first = projection(body)
            second = projection(body)
            table_body = asdict(next(c for section in parsed.sections for c in section.chunks
                                     if "Widget" in c.rawText))
            table_body["metadata"]["extensions"]["table"]["rows"] = [
                [f"Widget{i}", "42"] for i in range(80)]
            table_segments = projection(table_body)
        self.assertGreater(len(table_segments), 1)
        self.assertTrue(all("Product" in text and "Amount" in text for text in table_segments))
        self.assertTrue(all(len(local.encode(text)) <= 16 for text in table_segments))
        self.assertEqual(body, original)
        self.assertEqual(first, second)
        self.assertGreater(len(first), 1)
        self.assertTrue(all(len(local.encode(text)) <= 16 for text in first))
        self.assertEqual(load.call_count, 1)
        self.assertEqual(type(projection._chunker._real_chunker._chunker).__name__, "HybridChunker")

    def test_partial_conversion_is_rejected(self):
        from unittest.mock import patch
        with patch("pi_platform.adapters.pdf.real_docling.is_docling_available", return_value=True):
            converter = RealDoclingConverter(_converter=NS(convert=lambda **kw: NS(
                status="partial_success", document=vendor_document(1), errors=["page failure"])))
        with self.assertRaisesRegex(RealDoclingConverterError, "partial_success"):
            converter.convert("/project/real.pdf")

    def test_real_hybrid_chunker_splits_using_an_offline_tokenizer(self):
        from unittest.mock import patch
        from tokenizers import Tokenizer, models, pre_tokenizers
        from transformers import PreTrainedTokenizerFast
        from pi_platform.adapters.pdf.real_docling import HuggingFaceTokenizerAdapter
        from pi_platform.adapters.pdf.docling_chunker import DoclingHybridChunker
        tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0, "Actual": 1}, unk_token="[UNK]"))
        tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
        local = PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]")
        parsed = self.adapter(NS(convert=lambda _, **kw: vendor_document(kw["page_range"][0]))).parse(self.source)
        with patch.object(HuggingFaceTokenizerAdapter, "_load_pre_trained_tokenizer", return_value=local):
            chunker = DoclingHybridChunker(max_tokens=16)
            chunks = chunker.chunk(parsed.document, parsed.sections)
        self.assertTrue(chunks)
        self.assertTrue(any("Widget" in c.rawText for c in chunks))
        self.assertTrue(all("Product" in c.rawText and "Amount" in c.rawText
                            for c in chunks if "Widget" in c.rawText))
        self.assertTrue(all(c.anchors for c in chunks))
        self.assertTrue(all(len(local.encode(c.rawText)) <= 16 for c in chunks))
        self.assertEqual(type(chunker._real_chunker._chunker).__name__, "HybridChunker")
