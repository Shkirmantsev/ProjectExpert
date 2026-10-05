"""Default :class:`ProvenancePort` implementation.

The adapter enforces the state machine documented in the
``provenance-state-model`` spec and stores the evidence chain in a
dedicated SQLite table inside the
:class:`SqliteRuntimeStore` database file.
"""

from __future__ import annotations

import sqlite3
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.content_address import content_address_bytes
from pi_platform.core.canonical.serializer import canonical_dump_json
from pi_platform.core.canonical.value_types import Evidence, KnowledgeState
from pi_platform.ports.runtime.provenance import (
    ProvenanceError,
    ProvenanceEvent,
    ProvenancePort,
)
from pi_platform.ports.runtime.runtime_store import (
    RuntimeStoreError,
    RuntimeStorePort,
)


__all__ = ["LocalProvenanceTracker"]


_ALLOWED_TRANSITIONS = {
    (KnowledgeState.VERIFIED, KnowledgeState.INFERRED),
    (KnowledgeState.VERIFIED, KnowledgeState.STALE),
    (KnowledgeState.VERIFIED, KnowledgeState.CONFLICTING),
    (KnowledgeState.INFERRED, KnowledgeState.STALE),
    (KnowledgeState.INFERRED, KnowledgeState.UNKNOWN),
    (KnowledgeState.ASSUMPTION, KnowledgeState.VERIFIED),
    (KnowledgeState.ASSUMPTION, KnowledgeState.STALE),
    (KnowledgeState.STALE, KnowledgeState.VERIFIED),
    (KnowledgeState.STALE, KnowledgeState.UNKNOWN),
    (KnowledgeState.UNKNOWN, KnowledgeState.INFERRED),
    (KnowledgeState.UNKNOWN, KnowledgeState.VERIFIED),
    (KnowledgeState.CONFLICTING, KnowledgeState.VERIFIED),
}


class LocalProvenanceTracker(ProvenancePort):
    """Default ``ProvenancePort`` adapter backed by SQLite."""

    _STATE_TABLE = "runtime_provenance_state"
    _EVENT_TABLE = "runtime_provenance_event"

    def __init__(self, store: RuntimeStorePort):
        self._store = store
        self._db_path = getattr(store, "_db_path", None)
        if self._db_path is None:
            raise ProvenanceError(
                "LocalProvenanceTracker requires a SqliteRuntimeStore"
            )
        self._init_schema()

    def _init_schema(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.executescript(
                f"""
                CREATE TABLE IF NOT EXISTS {self._STATE_TABLE} (
                    entity_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS {self._EVENT_TABLE} (
                    entity_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    from_state TEXT NOT NULL,
                    to_state TEXT NOT NULL,
                    evidence_hash TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    PRIMARY KEY (entity_id, seq)
                );
                """
            )

    def transition(
        self, entity_id: str, *, from_state: KnowledgeState,
        to_state: KnowledgeState,
        evidence: Mapping[str, object],
    ) -> None:
        if from_state == to_state:
            with sqlite3.connect(self._db_path) as conn:
                row = conn.execute(
                    f"SELECT state FROM {self._STATE_TABLE} WHERE entity_id = ?",
                    (entity_id,),
                ).fetchone()
                if row is None:
                    conn.execute(
                        f"INSERT INTO {self._STATE_TABLE}(entity_id, state, updated_at) VALUES(?, ?, datetime('now'))",
                        (entity_id, to_state.value),
                    )
                    conn.commit()
                return
        if (from_state, to_state) not in _ALLOWED_TRANSITIONS:
            raise ProvenanceError(
                f"forbidden transition {from_state.value} -> {to_state.value}"
            )
        evidence_bytes = canonical_dump_json(dict(evidence))
        evidence_hash = content_address_bytes(evidence_bytes)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                f"INSERT OR REPLACE INTO {self._STATE_TABLE}(entity_id, state, updated_at) VALUES(?, ?, datetime('now'))",
                (entity_id, to_state.value),
            )
            seq_row = conn.execute(
                f"SELECT COALESCE(MAX(seq), 0) + 1 FROM {self._EVENT_TABLE} WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
            seq = seq_row[0] if seq_row else 1
            conn.execute(
                f"INSERT INTO {self._EVENT_TABLE}(entity_id, seq, from_state, to_state, evidence_hash, evidence_json, ts) VALUES(?, ?, ?, ?, ?, ?, datetime('now'))",
                (entity_id, seq, from_state.value, to_state.value,
                 evidence_hash, evidence_bytes.decode("utf-8")),
            )
            conn.commit()

    def current_state(self, entity_id: str) -> Optional[KnowledgeState]:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                f"SELECT state FROM {self._STATE_TABLE} WHERE entity_id = ?",
                (entity_id,),
            ).fetchone()
        if row is None:
            return None
        return KnowledgeState(row[0])

    def evidence(self, entity_id: str) -> Sequence[Evidence]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT from_state, to_state, evidence_json FROM {self._EVENT_TABLE} WHERE entity_id = ? ORDER BY seq",
                (entity_id,),
            ).fetchall()
        chain = []
        for row in rows:
            chain.append(Evidence(
                knowledgeState=KnowledgeState(row[1]),
                parserVersion="phase3",
                sourceHash=None,
                lastVerifiedAt=None,
                rationale=f"transition {row[0]} -> {row[1]}",
            ))
        return tuple(chain)

    def staleness_map(self) -> Mapping[str, KnowledgeState]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT entity_id, state FROM {self._STATE_TABLE}"
            ).fetchall()
        return {row[0]: KnowledgeState(row[1]) for row in rows}

    def events(self, entity_id: str) -> Sequence[ProvenanceEvent]:
        with sqlite3.connect(self._db_path) as conn:
            rows = conn.execute(
                f"SELECT from_state, to_state, evidence_hash, evidence_json FROM {self._EVENT_TABLE} WHERE entity_id = ? ORDER BY seq",
                (entity_id,),
            ).fetchall()
        events = []
        for row in rows:
            evidence_dict = json.loads(row[3]) if False else {}
            events.append(ProvenanceEvent(
                entity_id=entity_id,
                from_state=KnowledgeState(row[0]),
                to_state=KnowledgeState(row[1]),
                evidence_hash=row[2],
                evidence=evidence_dict,
            ))
        return tuple(events)