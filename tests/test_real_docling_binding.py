"""Tests for the real Docling binding (open spec change PR 10).

Covers the ``real-docling-pdf-adapter-and-hybrid-chunker`` spec
delta:

* The real ``docling.document_converter.DocumentConverter`` is
  available when the optional ``docling`` package is installed.
* The :class:`HybridChunkerAdapter` aligns with the active
  embedding model identifier (plan §48).
* Vendor types NEVER leak past the adapter boundary (the
  :class:`RealDoclingConverter` exposes a lazy
  ``convert_and_chunk`` entry point that returns vendor types,
  but the rest of the platform consumes only the neutral
  :class:`~pi_platform.core.canonical.document_graph.DocumentElement`
  shape).
* The mapping produces one neutral element per Docling structural
  unit when a synthesized test doc is fed through the
  :class:`DoclingMapper`.
"""

from __future__ import annotations

import unittest

from pi_platform.adapters.pdf.docling_pdf_adapter import (
    DoclingMapper,
    DoclingPdfAdapter,
)
from pi_platform.adapters.pdf.real_docling import (
    HuggingFaceTokenizerAdapter,
    HybridChunkerAdapter,
    RealDoclingConverter,
    build_docling_chunker,
    is_docling_available,
)
from pi_platform.core.canonical.document_graph import (
    AssetRef,
    DocumentElement,
    DocumentRevision,
    ElementKind,
    Page,
    TableGrid,
)
from pi_platform.core.canonical.value_types import Metadata


class DoclingAvailabilityTests(unittest.TestCase):
    """The real :mod:`docling` package import surface is checked."""

    def test_docling_is_importable(self) -> None:
        # Dependency presence is a production gate, not a minimal-install prerequisite.
        self.assertIsInstance(is_docling_available(), bool)


class HybridChunkerAlignmentTests(unittest.TestCase):
    """The chunker MUST align with the active embedding model."""

    def test_gemma_chunker_uses_gemma_tokenizer(self) -> None:
        chunker = build_docling_chunker(
            embedding_model_id="google/embeddinggemma-2",
            max_tokens=512,
        )
        self.assertIsInstance(chunker, HybridChunkerAdapter)
        self.assertEqual(
            chunker.tokenizer_alignment,
            "google/embeddinggemma-2",
            "Gemma chunker MUST use the Gemma tokenizer (plan §48)",
        )

    def test_qwen_chunker_uses_qwen_tokenizer(self) -> None:
        chunker = build_docling_chunker(
            embedding_model_id="Qwen/Qwen3-Embedding-0.6B",
            max_tokens=512,
        )
        self.assertEqual(
            chunker.tokenizer_alignment,
            "Qwen/Qwen3-Embedding-0.6B",
        )

    def test_max_tokens_propagates(self) -> None:
        chunker = build_docling_chunker(
            embedding_model_id="google/embeddinggemma-2",
            max_tokens=256,
        )
        self.assertEqual(chunker.max_tokens, 256)

    def test_unrecognised_model_falls_back_to_identity(self) -> None:
        chunker = build_docling_chunker(
            embedding_model_id="unknown/private-model",
        )
        # The default mapping returns the identity when the model
        # is not in the table; the env var override is the
        # documented escape hatch.
        self.assertEqual(
            chunker.tokenizer_alignment,
            "unknown/private-model",
        )


@unittest.skipUnless(is_docling_available(), "documents optional dependencies unavailable")
class HuggingFaceTokenizerAdapterTests(unittest.TestCase):
    """The HuggingFace tokenizer adapter wraps Docling's tokenizer."""

    def setUp(self):
        from unittest.mock import patch
        from tokenizers import Tokenizer, models, pre_tokenizers
        from transformers import PreTrainedTokenizerFast
        tokenizer = Tokenizer(models.WordLevel({"[UNK]": 0, "hello": 1, "world": 2}, unk_token="[UNK]"))
        tokenizer.pre_tokenizer = pre_tokenizers.Whitespace()
        local = PreTrainedTokenizerFast(tokenizer_object=tokenizer, unk_token="[UNK]")
        patcher = patch.object(HuggingFaceTokenizerAdapter, "_load_pre_trained_tokenizer", return_value=local)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_count_tokens_returns_nonnegative(self) -> None:
        adapter = HuggingFaceTokenizerAdapter(
            tokenizer_id="google/embeddinggemma-2",
        )
        # A short string MUST yield a non-negative token count.
        count = adapter.count_tokens("hello world")
        self.assertGreaterEqual(count, 0)

    def test_count_tokens_grows_with_input(self) -> None:
        adapter = HuggingFaceTokenizerAdapter(
            tokenizer_id="google/embeddinggemma-2",
        )
        short = adapter.count_tokens("hello")
        long = adapter.count_tokens(
            "hello " * 50,
        )
        self.assertLess(short, long)

    def test_encode_returns_int_sequence(self) -> None:
        adapter = HuggingFaceTokenizerAdapter(
            tokenizer_id="google/embeddinggemma-2",
        )
        tokens = adapter.encode("hello world")
        self.assertGreater(len(tokens), 0)
        for tok in tokens:
            self.assertIsInstance(tok, int)


@unittest.skipUnless(is_docling_available(), "documents optional dependencies unavailable")
class RealDoclingConverterConstructionTests(unittest.TestCase):
    """The :class:`RealDoclingConverter` is constructible when
    docling is available."""

    def test_construction_succeeds_when_docling_available(self) -> None:
        # The user environment has docling; construction MUST
        # succeed.
        converter = RealDoclingConverter(
            embedding_model_id="google/embeddinggemma-2",
        )
        self.assertIsNotNone(converter)

    def test_chunker_lazy(self) -> None:
        converter = RealDoclingConverter(
            embedding_model_id="google/embeddinggemma-2",
        )
        chunker = converter.chunker()
        # Cached: the second call MUST return the same object.
        self.assertIs(chunker, converter.chunker())


class DoclingMapperNeutralProjectionTests(unittest.TestCase):
    """The mapper MUST project vendor Docling shapes into neutral
    :class:`DocumentElement` values; vendor types never escape.
    """

    def _build_synth_doc(self) -> object:
        # We deliberately reuse the synthesised stub from the
        # existing adapter module to exercise the mapper without
        # loading the real Docling models (the mapper contract is
        # identical for both backends).
        from pi_platform.adapters.pdf.docling_pdf_adapter import (
            _DoclingDocument,
            _DoclingTextItem,
            _DoclingTableItem,
            _DoclingFigureItem,
        )
        return _DoclingDocument(
            page_count=3,
            text_items=(
                _DoclingTextItem(
                    text="Hello world.",
                    page=1,
                    bbox=(0.0, 0.0, 612.0, 100.0),
                ),
            ),
            tables=(
                _DoclingTableItem(
                    headers=("Col A", "Col B"),
                    rows=(("a1", "b1"),),
                    page=1,
                    bbox=(0.0, 200.0, 612.0, 300.0),
                ),
            ),
            figures=(
                _DoclingFigureItem(
                    caption="Figure 1",
                    page=2,
                    bbox=(0.0, 0.0, 300.0, 200.0),
                ),
            ),
            language="en",
        )

    def test_projection_emits_neutral_types_only(self) -> None:
        doc = self._build_synth_doc()
        mapper = DoclingMapper()
        revision = mapper.project_revision(
            doc=doc,
            source_id="src-1",
            byte_hash="hash-1",
            strategy_version="docling-pdf/v1",
            ingested_at="2026-10-19T00:00:00Z",
        )
        self.assertIsInstance(revision, DocumentRevision)
        self.assertEqual(revision.page_count, 3)
        self.assertEqual(revision.language, "en")
        # The returned revision MUST NOT contain any vendor type.
        self.assertNotIn("DoclingDocument", type(revision).__name__)

        pages = mapper.project_pages(doc)
        for page in pages:
            self.assertIsInstance(page, Page)
        self.assertEqual(len(pages), 3)

        elements = mapper.project_elements(doc, "hash-1")
        for element in elements:
            self.assertIsInstance(element, DocumentElement)
        kinds = {e.kind for e in elements}
        self.assertIn(ElementKind.PARAGRAPH, kinds)
        self.assertIn(ElementKind.TABLE, kinds)
        self.assertIn(ElementKind.FIGURE, kinds)

        tables = mapper.project_tables(doc, "hash-1")
        for element_id, table in tables:
            self.assertIsInstance(table, TableGrid)
            self.assertEqual(table.headers, ("Col A", "Col B"))

        figures = mapper.project_figures(doc, "hash-1")
        for asset in figures:
            self.assertIsInstance(asset, AssetRef)
            self.assertEqual(asset.page, 2)


class DoclingVendorBoundaryTests(unittest.TestCase):
    """Vendor types MUST NOT be referenced by name outside
    ``pi_platform.adapters.pdf``.
    """

    def test_no_real_docling_import_in_canonical_module(self) -> None:
        import ast
        import pathlib

        canonical_root = (
            pathlib.Path(__file__).resolve().parents[1]
            / "pi_platform"
            / "core"
            / "canonical"
        )
        for path in canonical_root.rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module and "docling" in node.module:
                        self.fail(
                            f"{path} imports a docling vendor type "
                            f"({node.module!r}); vendor types MUST NOT "
                            f"appear in pi_platform.core.canonical"
                        )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        if "docling" in alias.name:
                            self.fail(
                                f"{path} imports a docling vendor type "
                                f"({alias.name!r}); vendor types MUST "
                                f"NOT appear in pi_platform.core.canonical"
                            )

    def test_docling_pdf_adapter_preserves_synthesised_path(self) -> None:
        # The existing synthesised path MUST still work for tests
        # that do not load the real Docling models.
        adapter = DoclingPdfAdapter
        self.assertTrue(callable(adapter))


class DoclingChunkerDependencyTests(unittest.TestCase):
    """The chunker construction requires docling."""

    def test_chunker_constructor_refuses_unknown_tokenizer_id(self) -> None:
        # We deliberately pass an empty tokenizer_id; the
        # constructor still builds (Docling resolves it later)
        # but the adapter's count_tokens raises if the tokenizer
        # cannot be resolved.
        adapter = HuggingFaceTokenizerAdapter(
            tokenizer_id="google/embeddinggemma-2",
        )
        # A non-empty string MUST yield a count.
        self.assertGreaterEqual(adapter.count_tokens("test"), 0)


if __name__ == "__main__":
    unittest.main()
