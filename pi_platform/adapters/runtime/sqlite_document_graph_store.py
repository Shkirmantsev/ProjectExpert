"""SQLite-backed document graph store (E4).

Stores the rich document graph (revisions, pages, elements,
assets, tables, chunk anchors) in dedicated SQLite tables inside
the existing ``runtime.db``. The schema is additive; the
existing ``runtime_entries`` table is not touched.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from pi_platform.core.canonical.document_graph import (
    AssetRef,
    DocumentElement,
    DocumentRevision,
    ElementKind,
    IngestionState,
    Page,
    SourceAnchor,
    TableGrid,
)
from pi_platform.ports.runtime.document_graph_store import (
    DocumentGraphStoreError,
    DocumentGraphStorePort,
)


__all__ = [
    "SqliteDocumentGraphStore",
    "migration_v2_add_document_graph_tables",
]


SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS document_revisions (
        revision_id      TEXT PRIMARY KEY,
        source_id        TEXT NOT NULL,
        byte_hash        TEXT NOT NULL,
        strategy_version TEXT NOT NULL,
        ingested_at       TEXT NOT NULL,
        page_count       INTEGER NOT NULL DEFAULT 0,
        language         TEXT NOT NULL DEFAULT 'und',
        author           TEXT NOT NULL DEFAULT ''
    )
    """,
    "CREATE INDEX IF NOT EXISTS document_revisions_by_source "
    "ON document_revisions (source_id)",
    """
    CREATE TABLE IF NOT EXISTS pages (
        revision_id          TEXT NOT NULL,
        page_no              INTEGER NOT NULL,
        bbox_json            TEXT NOT NULL DEFAULT '[]',
        native_text_present  INTEGER NOT NULL DEFAULT 1,
        ocr_used             INTEGER NOT NULL DEFAULT 0,
        rotation             INTEGER NOT NULL DEFAULT 0,
        language_hint        TEXT NOT NULL DEFAULT 'und',
        PRIMARY KEY (revision_id, page_no)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS document_elements (
        revision_id    TEXT NOT NULL,
        element_id     TEXT NOT NULL,
        kind           TEXT NOT NULL,
        page           INTEGER NOT NULL,
        bbox_json      TEXT NOT NULL DEFAULT '[]',
        content_hash   TEXT NOT NULL DEFAULT '',
        semantic_key   TEXT NOT NULL DEFAULT '',
        text           TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (revision_id, element_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS document_elements_by_page "
    "ON document_elements (revision_id, page)",
    """
    CREATE TABLE IF NOT EXISTS assets (
        asset_id  TEXT PRIMARY KEY,
        byte_hash TEXT NOT NULL,
        mime_type TEXT NOT NULL,
        cas_path  TEXT NOT NULL,
        page      INTEGER NOT NULL DEFAULT 0,
        bbox_json TEXT NOT NULL DEFAULT '[]'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS table_payloads (
        revision_id      TEXT NOT NULL,
        element_id       TEXT NOT NULL,
        headers_json     TEXT NOT NULL DEFAULT '[]',
        rows_json        TEXT NOT NULL DEFAULT '[]',
        serialised_md    TEXT NOT NULL DEFAULT '',
        repeat_header    INTEGER NOT NULL DEFAULT 1,
        PRIMARY KEY (revision_id, element_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunk_anchors (
        chunk_id     TEXT NOT NULL,
        ordinal      INTEGER NOT NULL,
        revision_id  TEXT NOT NULL,
        page         INTEGER NOT NULL DEFAULT 0,
        element_id   TEXT NOT NULL DEFAULT '',
        bbox_json    TEXT NOT NULL DEFAULT '[]',
        line         INTEGER NOT NULL DEFAULT 0,
        asset_id     TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (chunk_id, ordinal)
    )
    """,
    "CREATE INDEX IF NOT EXISTS chunk_anchors_by_chunk "
    "ON chunk_anchors (chunk_id)",
]


def migration_v2_add_document_graph_tables(
    db: sqlite3.Connection,
) -> None:
    """Additive migration: create the rich document graph tables
    and their indexes. Idempotent."""
    for stmt in SCHEMA:
        db.execute(stmt)
    db.commit()


def _bbox_to_json(bbox: Sequence[float]) -> str:
    return json.dumps([float(x) for x in bbox])


def _bbox_from_json(s: str) -> Tuple[float, ...]:
    if not s:
        return ()
    try:
        return tuple(float(x) for x in json.loads(s))
    except (json.JSONDecodeError, ValueError):
        return ()


def _headers_to_json(headers: Sequence[str]) -> str:
    return json.dumps([str(h) for h in headers])


def _rows_to_json(rows: Sequence[Sequence[str]]) -> str:
    return json.dumps([[str(c) for c in r] for r in rows])


class SqliteDocumentGraphStore(DocumentGraphStorePort):
    """SQLite adapter for the rich document graph store."""

    def __init__(self, db: sqlite3.Connection) -> None:
        if db is None:
            raise DocumentGraphStoreError("db connection is required")
        self._db = db
        migration_v2_add_document_graph_tables(db)

    # -- revisions ---------------------------------------------------

    def put_revision(self, rev: DocumentRevision) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO document_revisions (
                    revision_id, source_id, byte_hash, strategy_version,
                    ingested_at, page_count, language, author
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rev.revision_id, rev.source_id, rev.byte_hash,
                    rev.strategy_version, rev.ingested_at,
                    rev.page_count, rev.language, rev.author,
                ),
            )

    def get_revision(
        self, revision_id: str,
    ) -> Optional[DocumentRevision]:
        cur = self._db.execute(
            "SELECT * FROM document_revisions WHERE revision_id = ?",
            (revision_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return DocumentRevision(
            revision_id=row["revision_id"],
            source_id=row["source_id"],
            byte_hash=row["byte_hash"],
            strategy_version=row["strategy_version"],
            ingested_at=row["ingested_at"],
            page_count=int(row["page_count"]),
            language=row["language"],
            author=row["author"],
        )

    def list_revisions(
        self, source_id: str,
    ) -> Tuple[DocumentRevision, ...]:
        cur = self._db.execute(
            "SELECT * FROM document_revisions WHERE source_id = ? "
            "ORDER BY revision_id",
            (source_id,),
        )
        return tuple(
            DocumentRevision(
                revision_id=r["revision_id"],
                source_id=r["source_id"],
                byte_hash=r["byte_hash"],
                strategy_version=r["strategy_version"],
                ingested_at=r["ingested_at"],
                page_count=int(r["page_count"]),
                language=r["language"],
                author=r["author"],
            )
            for r in cur.fetchall()
        )

    # -- pages -------------------------------------------------------

    def put_page(self, revision_id: str, page: Page) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO pages (
                    revision_id, page_no, bbox_json,
                    native_text_present, ocr_used, rotation, language_hint
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id, page.page_no, _bbox_to_json(page.bbox),
                    int(bool(page.native_text_present)),
                    int(bool(page.ocr_used)),
                    page.rotation, page.language_hint,
                ),
            )

    def list_pages(self, revision_id: str) -> Tuple[Page, ...]:
        cur = self._db.execute(
            "SELECT * FROM pages WHERE revision_id = ? ORDER BY page_no",
            (revision_id,),
        )
        return tuple(self._row_to_page(r) for r in cur.fetchall())

    # -- elements ----------------------------------------------------

    def put_element(
        self, revision_id: str, element: DocumentElement,
    ) -> None:
        kind = element.kind.value if isinstance(
            element.kind, ElementKind,
        ) else str(element.kind)
        if not ElementKind.is_recognised(kind):
            raise DocumentGraphStoreError(
                f"unrecognised element kind: {kind!r}"
            )
        with self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO document_elements (
                    revision_id, element_id, kind, page, bbox_json,
                    content_hash, semantic_key, text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id, element.element_id, kind,
                    element.page, _bbox_to_json(element.bbox),
                    element.content_hash, element.semantic_key,
                    element.text,
                ),
            )

    def list_elements(
        self, revision_id: str, page: Optional[int] = None,
    ) -> Tuple[DocumentElement, ...]:
        if page is None:
            cur = self._db.execute(
                "SELECT * FROM document_elements WHERE revision_id = ? "
                "ORDER BY page, element_id",
                (revision_id,),
            )
        else:
            cur = self._db.execute(
                "SELECT * FROM document_elements WHERE revision_id = ? "
                "AND page = ? ORDER BY element_id",
                (revision_id, page),
            )
        return tuple(self._row_to_element(r) for r in cur.fetchall())

    # -- assets ------------------------------------------------------

    def put_asset(self, asset: AssetRef) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO assets (
                    asset_id, byte_hash, mime_type, cas_path, page,
                    bbox_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    asset.asset_id, asset.byte_hash, asset.mime_type,
                    asset.cas_path, asset.page,
                    _bbox_to_json(asset.bbox),
                ),
            )

    def get_asset(self, asset_id: str) -> Optional[AssetRef]:
        cur = self._db.execute(
            "SELECT * FROM assets WHERE asset_id = ?", (asset_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return AssetRef(
            asset_id=row["asset_id"],
            byte_hash=row["byte_hash"],
            mime_type=row["mime_type"],
            cas_path=row["cas_path"],
            page=int(row["page"]),
            bbox=_bbox_from_json(row["bbox_json"]),
        )

    # -- tables ------------------------------------------------------

    def put_table(
        self, revision_id: str, element_id: str, table: TableGrid,
    ) -> None:
        with self._db:
            self._db.execute(
                """
                INSERT OR REPLACE INTO table_payloads (
                    revision_id, element_id, headers_json, rows_json,
                    serialised_md, repeat_header
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    revision_id, element_id,
                    _headers_to_json(table.headers),
                    _rows_to_json(table.rows),
                    table.serialised_markdown,
                    int(bool(table.repeat_header)),
                ),
            )

    def get_table(
        self, revision_id: str, element_id: str,
    ) -> Optional[TableGrid]:
        cur = self._db.execute(
            "SELECT * FROM table_payloads "
            "WHERE revision_id = ? AND element_id = ?",
            (revision_id, element_id),
        )
        row = cur.fetchone()
        if row is None:
            return None
        return self._row_to_table(row)

    # -- chunk anchors -----------------------------------------------

    def put_chunk_anchor(
        self, chunk_id: str, anchor: SourceAnchor,
    ) -> None:
        cur = self._db.execute(
            "SELECT COALESCE(MAX(ordinal), -1) + 1 AS next "
            "FROM chunk_anchors WHERE chunk_id = ?",
            (chunk_id,),
        )
        ordinal = int(cur.fetchone()["next"])
        with self._db:
            self._db.execute(
                """
                INSERT INTO chunk_anchors (
                    chunk_id, ordinal, revision_id, page, element_id,
                    bbox_json, line, asset_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk_id, ordinal, anchor.revision_id, anchor.page,
                    anchor.element_id, _bbox_to_json(anchor.bbox),
                    anchor.line, anchor.asset_id,
                ),
            )

    def list_chunk_anchors(
        self, chunk_id: str,
    ) -> Tuple[SourceAnchor, ...]:
        cur = self._db.execute(
            "SELECT * FROM chunk_anchors WHERE chunk_id = ? "
            "ORDER BY ordinal",
            (chunk_id,),
        )
        return tuple(
            SourceAnchor(
                revision_id=r["revision_id"],
                page=int(r["page"]),
                element_id=r["element_id"],
                bbox=_bbox_from_json(r["bbox_json"]),
                line=int(r["line"]),
                asset_id=r["asset_id"],
            )
            for r in cur.fetchall()
        )

    def stats(self) -> Mapping[str, int]:
        out: Dict[str, int] = {}
        for table in (
            "document_revisions", "pages", "document_elements",
            "assets", "table_payloads", "chunk_anchors",
        ):
            cur = self._db.execute(f"SELECT COUNT(*) AS n FROM {table}")
            out[table] = int(cur.fetchone()["n"])
        return out

    # -- internal helpers --------------------------------------------

    def _row_to_page(self, row: sqlite3.Row) -> Page:
        return Page(
            page_no=int(row["page_no"]),
            bbox=_bbox_from_json(row["bbox_json"]),
            native_text_present=bool(int(row["native_text_present"])),
            ocr_used=bool(int(row["ocr_used"])),
            rotation=int(row["rotation"]),
            language_hint=row["language_hint"],
        )

    def _row_to_element(self, row: sqlite3.Row) -> DocumentElement:
        return DocumentElement(
            element_id=row["element_id"],
            kind=ElementKind(row["kind"]),
            page=int(row["page"]),
            bbox=_bbox_from_json(row["bbox_json"]),
            content_hash=row["content_hash"],
            semantic_key=row["semantic_key"],
            text=row["text"],
        )

    def _row_to_table(self, row: sqlite3.Row) -> TableGrid:
        try:
            headers = tuple(str(h) for h in json.loads(row["headers_json"]))
            rows = tuple(
                tuple(str(c) for c in r)
                for r in json.loads(row["rows_json"])
            )
        except (json.JSONDecodeError, ValueError, TypeError):
            headers = ()
            rows = ()
        return TableGrid(
            headers=headers,
            rows=rows,
            serialised_markdown=row["serialised_md"],
            repeat_header=bool(int(row["repeat_header"])),
        )
