"""Default :class:`FullTextIndexPort` implementation (SQLite FTS5).

Reuses the SQLite FTS5 module that ships with the
:class:`SqliteRuntimeStore` backend. The full-text index is backed by
a dedicated virtual table inside the same SQLite database file.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import Mapping, Sequence

from pi_platform.ports.runtime.full_text_index import (
    FullTextHit,
    FullTextIndexError,
    FullTextIndexPort,
)
from pi_platform.ports.runtime.runtime_store import (
    RuntimeStorePort,
)


__all__ = ["SqliteFtsFullTextIndex"]


class SqliteFtsFullTextIndex(FullTextIndexPort):
    """SQLite FTS5 secondary full-text index adapter."""

    _TABLE = "runtime_fulltext_fts"

    def __init__(self, store: RuntimeStorePort):
        self._store = store
        self._db_path = getattr(store, "_db_path", None)
        if self._db_path is None:
            raise FullTextIndexError(
                "SqliteFtsFullTextIndex requires a SqliteRuntimeStore"
            )
        self._init_fts()

    def _init_fts(self) -> None:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            conn.execute(
                f"CREATE VIRTUAL TABLE IF NOT EXISTS {self._TABLE} USING fts5("
                "document_id UNINDEXED, family UNINDEXED, text"
                ")"
            )

    def index_document(
        self, family: str, documentId: str, text: str,
        metadata: Mapping[str, object],
    ) -> None:
        self.delete_document(documentId)
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            conn.execute(
                f"INSERT INTO {self._TABLE}(document_id, family, text) VALUES(?, ?, ?)",
                (documentId, family, text),
            )
            conn.commit()

    def delete_document(self, documentId: str) -> None:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            conn.execute(
                f"DELETE FROM {self._TABLE} WHERE document_id = ?",
                (documentId,),
            )
            conn.commit()

    def query(self, text: str, top_k: int = 10) -> Sequence[FullTextHit]:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            try:
                rows = conn.execute(
                    f"SELECT document_id, snippet({self._TABLE}, 2, '<', '>', '...', 16) "
                    f"FROM {self._TABLE} WHERE {self._TABLE} MATCH ? "
                    f"ORDER BY rank LIMIT ?",
                    (text, top_k),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        hits = []
        for row in rows:
            hits.append(FullTextHit(
                documentId=row[0],
                score=1.0,
                snippet=row[1] or "",
            ))
        return tuple(hits)

    def stats(self) -> Mapping[str, int]:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {self._TABLE}"
            ).fetchone()[0]
        return {"documents": count}