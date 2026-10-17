"""Tests for the SQLite document graph store (E4)."""

from __future__ import annotations

import sqlite3
import unittest

from pi_platform.core.canonical.document_graph import (
    AssetRef,
    DocumentElement,
    DocumentRevision,
    ElementKind,
    Page,
    SourceAnchor,
    TableGrid,
)
from pi_platform.ports.runtime.document_graph_store import (
    DocumentGraphStoreError,
)
from pi_platform.adapters.runtime.sqlite_document_graph_store import (
    SqliteDocumentGraphStore,
    migration_v2_add_document_graph_tables,
)


def _new_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return db


class SqliteDocumentGraphStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._db = _new_db()
        self._store = SqliteDocumentGraphStore(self._db)

    def test_revision_round_trip(self) -> None:
        rev = DocumentRevision(
            revision_id="rev-1", source_id="src-1", byte_hash="h-1",
            strategy_version="docling-pdf-v1", ingested_at="2026-10-15T00:00:00Z",
            page_count=42, language="de", author="Alice",
        )
        self._store.put_revision(rev)
        got = self._store.get_revision("rev-1")
        self.assertEqual(got, rev)

    def test_list_revisions(self) -> None:
        self._store.put_revision(DocumentRevision(
            revision_id="rev-A", source_id="src-1", byte_hash="h-A",
            strategy_version="v", ingested_at="t",
        ))
        self._store.put_revision(DocumentRevision(
            revision_id="rev-B", source_id="src-1", byte_hash="h-B",
            strategy_version="v", ingested_at="t",
        ))
        self._store.put_revision(DocumentRevision(
            revision_id="rev-C", source_id="src-2", byte_hash="h-C",
            strategy_version="v", ingested_at="t",
        ))
        revs = self._store.list_revisions("src-1")
        self.assertEqual({r.revision_id for r in revs}, {"rev-A", "rev-B"})

    def test_pages_round_trip(self) -> None:
        self._store.put_page("rev-1", Page(
            page_no=1, bbox=(0.0, 0.0, 612.0, 792.0),
            native_text_present=True, ocr_used=False,
            rotation=0, language_hint="en",
        ))
        self._store.put_page("rev-1", Page(
            page_no=2, bbox=(0.0, 0.0, 612.0, 792.0),
            native_text_present=False, ocr_used=True,
            rotation=90, language_hint="de",
        ))
        pages = self._store.list_pages("rev-1")
        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[0].page_no, 1)
        self.assertTrue(pages[0].native_text_present)
        self.assertFalse(pages[0].ocr_used)
        self.assertEqual(pages[1].rotation, 90)
        self.assertTrue(pages[1].ocr_used)

    def test_elements_filtered_by_page(self) -> None:
        # Use unique element_ids so INSERT OR REPLACE doesn't dedupe.
        self._store.put_element("rev-1", DocumentElement(
            element_id="el-1", kind=ElementKind.PARAGRAPH, page=1,
        ))
        self._store.put_element("rev-1", DocumentElement(
            element_id="el-2a", kind=ElementKind.PARAGRAPH, page=2,
        ))
        self._store.put_element("rev-1", DocumentElement(
            element_id="el-2b", kind=ElementKind.HEADING, page=2,
        ))
        self._store.put_element("rev-1", DocumentElement(
            element_id="el-3", kind=ElementKind.PARAGRAPH, page=3,
        ))
        all_els = self._store.list_elements("rev-1")
        self.assertEqual(len(all_els), 4)
        page2_els = self._store.list_elements("rev-1", page=2)
        self.assertEqual(len(page2_els), 2)
        self.assertTrue(all(e.page == 2 for e in page2_els))

    def test_element_unknown_kind_from_db_raises_on_read(self) -> None:
        # Insert a row directly via raw SQL with an unknown kind.
        # The dataclass __post_init__ would reject this on the
        # Python side, so we go around it via SQLite to confirm the
        # adapter's defensive check fires on read.
        self._db.execute(
            "INSERT INTO document_elements (revision_id, element_id, "
            "kind, page) VALUES (?, ?, ?, ?)",
            ("rev-1", "el-bad", "nonsense", 1),
        )
        self._db.commit()
        with self.assertRaises(ValueError):
            self._store.list_elements("rev-1")

    def test_asset_round_trip(self) -> None:
        a = AssetRef(
            asset_id="asset-1", byte_hash="h-1", mime_type="image/png",
            cas_path="cas/h-1", page=7, bbox=(0.0, 0.0, 200.0, 100.0),
        )
        self._store.put_asset(a)
        got = self._store.get_asset("asset-1")
        self.assertEqual(got, a)

    def test_table_round_trip(self) -> None:
        t = TableGrid(
            headers=("Col A", "Col B"),
            rows=(("a1", "b1"), ("a2", "b2")),
            serialised_markdown="| Col A | Col B |\n| a1 | b1 |",
            repeat_header=True,
        )
        self._store.put_table("rev-1", "el-1", t)
        got = self._store.get_table("rev-1", "el-1")
        self.assertEqual(got, t)

    def test_chunk_anchor_round_trip(self) -> None:
        for i in range(3):
            self._store.put_chunk_anchor("chunk-1", SourceAnchor(
                revision_id="rev-1", page=i + 1, element_id=f"el-{i}",
                bbox=(0.0, 0.0, 100.0, 50.0), line=i * 10,
            ))
        anchors = self._store.list_chunk_anchors("chunk-1")
        self.assertEqual(len(anchors), 3)
        self.assertEqual([a.page for a in anchors], [1, 2, 3])
        self.assertEqual([a.line for a in anchors], [0, 10, 20])

    def test_migration_idempotent(self) -> None:
        migration_v2_add_document_graph_tables(self._db)
        migration_v2_add_document_graph_tables(self._db)
        # Store still works.
        self._store.put_revision(DocumentRevision(
            revision_id="rev-X", source_id="src-1", byte_hash="h",
            strategy_version="v", ingested_at="t",
        ))
        self.assertIsNotNone(self._store.get_revision("rev-X"))

    def test_stats_counts_records(self) -> None:
        self._store.put_revision(DocumentRevision(
            revision_id="rev-1", source_id="src-1", byte_hash="h",
            strategy_version="v", ingested_at="t",
        ))
        self._store.put_page("rev-1", Page(page_no=1))
        self._store.put_element("rev-1", DocumentElement(
            element_id="el-1", kind=ElementKind.PARAGRAPH, page=1,
        ))
        self._store.put_asset(AssetRef(
            asset_id="a-1", byte_hash="h", mime_type="image/png",
            cas_path="c/h",
        ))
        self._store.put_table("rev-1", "el-1", TableGrid())
        self._store.put_chunk_anchor("chunk-1", SourceAnchor(
            revision_id="rev-1", page=1, element_id="el-1",
        ))
        stats = self._store.stats()
        self.assertEqual(stats["document_revisions"], 1)
        self.assertEqual(stats["pages"], 1)
        self.assertEqual(stats["document_elements"], 1)
        self.assertEqual(stats["assets"], 1)
        self.assertEqual(stats["table_payloads"], 1)
        self.assertEqual(stats["chunk_anchors"], 1)


class DocumentGraphStorePortContractTests(unittest.TestCase):
    def test_port_is_abstract(self) -> None:
        from pi_platform.ports.runtime.document_graph_store import (
            DocumentGraphStorePort,
        )
        import inspect
        self.assertTrue(inspect.isabstract(DocumentGraphStorePort))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
