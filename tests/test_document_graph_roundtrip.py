"""Tests for the rich canonical document graph types (E1)."""

from __future__ import annotations

import dataclasses
import unittest

from pi_platform.core.canonical.document_graph import (
    AssetRef,
    DocumentElement,
    DocumentRevision,
    ElementKind,
    IngestionCheckpoint,
    IngestionState,
    Page,
    SourceAnchor,
    TableGrid,
)
from pi_platform.core.canonical.value_types import Chunk


class SourceAnchorTests(unittest.TestCase):
    def test_value_object(self) -> None:
        a = SourceAnchor(
            revision_id="rev-1", page=3, element_id="el-1",
            bbox=(0.0, 0.0, 100.0, 50.0), line=42, asset_id="asset-1",
        )
        self.assertEqual(a.revision_id, "rev-1")
        self.assertEqual(a.page, 3)
        self.assertEqual(a.element_id, "el-1")
        self.assertEqual(a.bbox, (0.0, 0.0, 100.0, 50.0))
        self.assertEqual(a.line, 42)
        self.assertEqual(a.asset_id, "asset-1")

    def test_defaults(self) -> None:
        a = SourceAnchor(revision_id="r")
        self.assertEqual(a.page, 0)
        self.assertEqual(a.element_id, "")
        self.assertEqual(a.bbox, ())
        self.assertEqual(a.line, 0)
        self.assertEqual(a.asset_id, "")

    def test_is_frozen(self) -> None:
        a = SourceAnchor(revision_id="r")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            a.page = 5  # type: ignore[misc]


class AssetRefTests(unittest.TestCase):
    def test_value_object(self) -> None:
        a = AssetRef(
            asset_id="asset-1", byte_hash="h-1", mime_type="image/png",
            cas_path=".project-intelligence-cache/assets/h-1",
            page=7, bbox=(0.0, 0.0, 200.0, 100.0),
        )
        self.assertEqual(a.asset_id, "asset-1")
        self.assertEqual(a.byte_hash, "h-1")
        self.assertEqual(a.mime_type, "image/png")
        self.assertEqual(a.page, 7)

    def test_defaults(self) -> None:
        a = AssetRef(asset_id="x", byte_hash="h", mime_type="m", cas_path="c")
        self.assertEqual(a.page, 0)
        self.assertEqual(a.bbox, ())


class DocumentRevisionTests(unittest.TestCase):
    def test_value_object(self) -> None:
        r = DocumentRevision(
            revision_id="rev-1", source_id="src-1", byte_hash="h-1",
            strategy_version="docling-pdf-v1", ingested_at="2026-10-15T00:00:00Z",
            page_count=600, language="de", author="Alice",
        )
        self.assertEqual(r.revision_id, "rev-1")
        self.assertEqual(r.page_count, 600)
        self.assertEqual(r.language, "de")
        self.assertEqual(r.author, "Alice")

    def test_defaults(self) -> None:
        r = DocumentRevision(
            revision_id="r", source_id="s", byte_hash="h",
            strategy_version="v", ingested_at="t",
        )
        self.assertEqual(r.page_count, 0)
        self.assertEqual(r.language, "und")
        self.assertEqual(r.author, "")


class PageTests(unittest.TestCase):
    def test_value_object(self) -> None:
        p = Page(
            page_no=12, bbox=(0.0, 0.0, 612.0, 792.0),
            native_text_present=True, ocr_used=False,
            rotation=0, language_hint="en",
        )
        self.assertEqual(p.page_no, 12)
        self.assertTrue(p.native_text_present)
        self.assertFalse(p.ocr_used)
        self.assertEqual(p.language_hint, "en")

    def test_defaults(self) -> None:
        p = Page(page_no=1)
        self.assertTrue(p.native_text_present)
        self.assertFalse(p.ocr_used)
        self.assertEqual(p.rotation, 0)
        self.assertEqual(p.language_hint, "und")


class DocumentElementTests(unittest.TestCase):
    def test_value_object(self) -> None:
        e = DocumentElement(
            element_id="el-1", kind=ElementKind.HEADING, page=3,
            bbox=(0.0, 0.0, 200.0, 30.0), content_hash="h-1",
            semantic_key="Chapter 1 / 1.2 / 1", text="1.2 Scope",
        )
        self.assertEqual(e.element_id, "el-1")
        self.assertEqual(e.kind, ElementKind.HEADING)
        self.assertEqual(e.text, "1.2 Scope")
        self.assertEqual(e.semantic_key, "Chapter 1 / 1.2 / 1")

    def test_invalid_kind_rejected(self) -> None:
        with self.assertRaises(ValueError):
            DocumentElement(
                element_id="el-1", kind="nonsense", page=1,
            )

    def test_all_kinds_accepted(self) -> None:
        for kind in ElementKind:
            e = DocumentElement(element_id="x", kind=kind, page=1)
            self.assertEqual(e.kind, kind)

    def test_is_recognised(self) -> None:
        for k in ("heading", "paragraph", "list", "table",
                  "figure", "formula"):
            self.assertTrue(ElementKind.is_recognised(k))
        self.assertFalse(ElementKind.is_recognised("nonsense"))


class TableGridTests(unittest.TestCase):
    def test_value_object(self) -> None:
        t = TableGrid(
            headers=("Col A", "Col B"),
            rows=(("a1", "b1"), ("a2", "b2")),
            serialised_markdown="| Col A | Col B |\n| a1 | b1 |\n| a2 | b2 |",
            repeat_header=True,
        )
        self.assertEqual(t.headers, ("Col A", "Col B"))
        self.assertEqual(t.rows, (("a1", "b1"), ("a2", "b2")))
        self.assertTrue(t.repeat_header)

    def test_defaults(self) -> None:
        t = TableGrid()
        self.assertEqual(t.headers, ())
        self.assertEqual(t.rows, ())
        self.assertEqual(t.serialised_markdown, "")
        self.assertTrue(t.repeat_header)


class IngestionCheckpointTests(unittest.TestCase):
    def test_value_object(self) -> None:
        c = IngestionCheckpoint(
            job_id="job-1", source_id="src-1", revision_id="rev-1",
            strategy_version="docling-pdf-v1",
            state=IngestionState.RUNNING,
            next_page=33, completed_ranges=((1, 32),),
            failed_range=(), error="", started_at="t0", updated_at="t1",
        )
        self.assertEqual(c.state, IngestionState.RUNNING)
        self.assertEqual(c.next_page, 33)
        self.assertEqual(c.completed_ranges, ((1, 32),))

    def test_all_states_accepted(self) -> None:
        for state in IngestionState:
            c = IngestionCheckpoint(
                job_id="x", source_id="s", revision_id="r",
                strategy_version="v", state=state,
            )
            self.assertEqual(c.state, state)

    def test_invalid_state_rejected(self) -> None:
        with self.assertRaises(ValueError):
            IngestionCheckpoint(
                job_id="x", source_id="s", revision_id="r",
                strategy_version="v", state="nonsense",
            )


class ChunkAnchorsTests(unittest.TestCase):
    def test_chunk_carries_anchors(self) -> None:
        a = SourceAnchor(revision_id="rev-1", page=3, element_id="el-1")
        c = Chunk(
            id="c-1", rawText="Hello", contextualText="",
            metadata=None,  # type: ignore[arg-type]
            sourceReference="doc.pdf", contentHash="h-1",
            anchors=(a,),
        )
        self.assertEqual(len(c.anchors), 1)
        self.assertEqual(c.anchors[0].element_id, "el-1")

    def test_chunk_legacy_no_anchors(self) -> None:
        # Legacy chunk (no anchors passed) deserialises with
        # anchors=() and is queryable.
        c = Chunk(
            id="c-1", rawText="Hello", contextualText="",
            metadata=None,  # type: ignore[arg-type]
            sourceReference="doc.pdf", contentHash="h-1",
        )
        self.assertEqual(c.anchors, ())
        self.assertEqual(c.id, "c-1")

    def test_anchors_default_is_empty_tuple(self) -> None:
        # The field default is `tuple` so callers that build
        # chunks without anchors do not share state.
        c = Chunk(
            id="c-1", rawText="x", contextualText="",
            metadata=None,  # type: ignore[arg-type]
            sourceReference="r", contentHash="h",
        )
        self.assertIsInstance(c.anchors, tuple)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
