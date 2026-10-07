"""Default :class:`FreshnessTrackerPort` implementation.

Records every ``mark_verified`` call in a SQLite table with the
``lastVerifiedAt`` timestamp and the ``source_hash``. The
``is_stale`` operation compares the recorded ``source_hash`` to the
supplied ``current_source_hash`` and returns ``True`` when they
differ. The ``derived_staleness`` operation delegates to the
:class:`ProvenancePort` for every upstream fact.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from contextlib import closing
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import (
    KnowledgeState,
    ProjectVersion,
)
from pi_platform.ports.runtime.freshness import (
    FreshnessError,
    FreshnessFact,
    FreshnessSnapshot,
    FreshnessTrackerPort,
)
from pi_platform.ports.runtime.provenance import ProvenancePort
from pi_platform.ports.runtime.runtime_store import RuntimeStorePort


__all__ = ["LastVerifiedFreshnessTracker"]


class LastVerifiedFreshnessTracker(FreshnessTrackerPort):
    """Default :class:`FreshnessTrackerPort` adapter."""

    _TABLE = "runtime_freshness_state"

    def __init__(self, store: RuntimeStorePort, provenance: Optional[ProvenancePort] = None):
        self._store = store
        self._db_path = getattr(store, "_db_path", None)
        if self._db_path is None:
            raise FreshnessError(
                "LastVerifiedFreshnessTracker requires a SqliteRuntimeStore"
            )
        self._provenance = provenance
        self._init_schema()

    def _init_schema(self) -> None:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            conn.execute(
                f"CREATE TABLE IF NOT EXISTS {self._TABLE} ("
                "fact_id TEXT PRIMARY KEY, "
                "source_hash TEXT NOT NULL, "
                "last_verified_at TEXT NOT NULL, "
                "git_head TEXT NOT NULL, "
                "working_tree_fingerprint TEXT NOT NULL"
                ")"
            )

    def mark_verified(
        self, fact_id: str, *, source_hash: str,
        version: ProjectVersion,
    ) -> None:
        ts = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            conn.execute(
                f"INSERT OR REPLACE INTO {self._TABLE}(fact_id, source_hash, last_verified_at, git_head, working_tree_fingerprint) VALUES(?, ?, ?, ?, ?)",
                (fact_id, source_hash, ts,
                 version.gitHead, version.workingTreeFingerprint),
            )
            conn.commit()

    def is_stale(self, fact_id: str, *, current_source_hash: str) -> bool:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            row = conn.execute(
                f"SELECT source_hash FROM {self._TABLE} WHERE fact_id = ?",
                (fact_id,),
            ).fetchone()
        if row is None:
            return True
        return row[0] != current_source_hash

    def derived_staleness(
        self, derived_fact_id: str, *, depends_on: Sequence[str],
    ) -> bool:
        if self._provenance is None:
            return False
        for upstream in depends_on:
            state = self._provenance.current_state(upstream)
            if state in (KnowledgeState.STALE, KnowledgeState.UNKNOWN):
                return True
        return False

    def snapshot(self) -> FreshnessSnapshot:
        captured = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            rows = conn.execute(
                f"SELECT fact_id, source_hash, last_verified_at, git_head, working_tree_fingerprint FROM {self._TABLE}"
            ).fetchall()
        facts = {}
        for row in rows:
            facts[row[0]] = FreshnessFact(
                fact_id=row[0],
                source_hash=row[1],
                last_verified_at=row[2],
                version=ProjectVersion(
                    gitHead=row[3],
                    workingTreeFingerprint=row[4],
                    knowledgeSchemaVersion="0.1.0",
                    embeddingModelVersion="unknown",
                    indexSchemaVersion="0.1.0",
                ),
            )
        return FreshnessSnapshot(facts=facts, captured_at=captured)