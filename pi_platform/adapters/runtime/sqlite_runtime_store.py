"""Default :class:`RuntimeStorePort` implementation backed by
SQLite (stdlib ``sqlite3``).

The Phase 3 default backend uses Python stdlib ``sqlite3`` only — no
extra runtime dependency is required. The PostgreSQL backend is the
opt-in enterprise-scale replacement; this change ships the port
contract and the SQLite default adapter, and the PostgreSQL adapter
is added by a future change after the SPDX-tracked ``psycopg``
Apache-2.0 entry passes ``LicenseGate``.

The store mirrors the §10.2 ``objects/<prefix>/<hash>.json``
sharding pattern (256 hash-prefix directories) and reuses the Phase 1
advisory file lock from :mod:`pi_platform.core.sync.project_lock`.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from contextlib import closing
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional

from pi_platform.core.canonical.content_address import (
    content_address_bytes,
    content_address_for_canonical,
    object_path,
)
from pi_platform.core.canonical.serializer import canonical_dump_json
from pi_platform.core.canonical.value_types import ProjectVersion
from pi_platform.core.sync.project_lock import ProjectLock
from pi_platform.ports.runtime.runtime_store import (
    KnowledgeStatePolicy,
    RuntimeEntry,
    RuntimeStatusReport,
    RuntimeStoreError,
    RuntimeStorePort,
    WALTailCorrupt,
)


__all__ = ["SqliteRuntimeStore"]


SCHEMA_VERSION = "0.1.0"


def _utc_now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class _WALRecord:
    family: str
    content_hash: str
    ts: str
    op: str
    payload: Mapping[str, Any] = field(default_factory=dict)


class SqliteRuntimeStore(RuntimeStorePort):
    """Default embedded :class:`RuntimeStorePort` adapter."""

    def __init__(self, cache_root: Path, *, version: ProjectVersion):
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self._version = version
        self._wal_path = self.cache_root / "wal.jsonl"
        self._objects_dir = self.cache_root / "objects"
        self._objects_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self.cache_root / "index.json"
        self._db_path = self.cache_root / "runtime.db"
        lock_id = "phase3-runtime-store-" + content_address_bytes(
            str(cache_root.resolve()).encode("utf-8")
        )[:16]
        self._lock = ProjectLock(lock_id)
        self._init_db()

    def _init_db(self) -> None:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runtime_entries (
                    content_hash TEXT PRIMARY KEY,
                    family TEXT NOT NULL,
                    body_json TEXT NOT NULL,
                    version_id TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS runtime_families (
                    family TEXT PRIMARY KEY,
                    count INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS runtime_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS runtime_entries_family_idx
                    ON runtime_entries(family);
                """
            )
            conn.execute(
                "INSERT OR REPLACE INTO runtime_metadata(key, value) VALUES(?, ?)",
                ("schema_version", SCHEMA_VERSION),
            )
            conn.execute(
                "INSERT OR REPLACE INTO runtime_metadata(key, value) VALUES(?, ?)",
                ("bound_git_head", self._version.gitHead),
            )
            conn.execute(
                "INSERT OR REPLACE INTO runtime_metadata(key, value) VALUES(?, ?)",
                ("bound_working_tree_fingerprint", self._version.workingTreeFingerprint),
            )
            conn.execute(
                "INSERT OR REPLACE INTO runtime_metadata(key, value) VALUES(?, ?)",
                ("bound_knowledge_schema_version", self._version.knowledgeSchemaVersion),
            )
            conn.execute(
                "INSERT OR REPLACE INTO runtime_metadata(key, value) VALUES(?, ?)",
                ("bound_index_schema_version", self._version.indexSchemaVersion),
            )

    def _content_path(self, content_hash: str) -> Path:
        return self._objects_dir / object_path(content_hash)

    def _load_index(self) -> dict[str, dict[str, str]]:
        if not self._index_path.exists():
            return {}
        try:
            return json.loads(self._index_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise WALTailCorrupt(str(self._index_path)) from exc

    def _save_index(self, index: Mapping[str, Mapping[str, str]]) -> None:
        body = canonical_dump_json(index)
        self._index_path.write_bytes(body)

    def _append_wal(self, record: _WALRecord) -> None:
        with self._wal_path.open("a", encoding="utf-8") as fh:
            fh.write(canonical_dump_json({
                "family": record.family,
                "content_hash": record.content_hash,
                "ts": record.ts,
                "op": record.op,
                "payload": dict(record.payload),
            }).decode("utf-8"))
            fh.write("\n")

    def _load_wal(self) -> list[_WALRecord]:
        if not self._wal_path.exists():
            return []
        records: list[_WALRecord] = []
        for line in self._wal_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            records.append(_WALRecord(
                family=data["family"],
                content_hash=data["content_hash"],
                ts=data["ts"],
                op=data["op"],
                payload=data.get("payload", {}),
            ))
        return records

    def backend_name(self) -> str:
        return "sqlite"

    def supports_postgres(self) -> bool:
        return False

    def put(self, family: str, body: Mapping[str, Any]) -> str:
        body_bytes = canonical_dump_json(body)
        content_hash = content_address_bytes(body_bytes)
        path = self._content_path(content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock.acquire():
            with closing(sqlite3.connect(self._db_path)) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                try:
                    conn.execute(
                        "INSERT OR REPLACE INTO runtime_entries(content_hash, family, body_json, version_id, created_at) VALUES(?, ?, ?, ?, ?)",
                        (
                            content_hash,
                            family,
                            body_bytes.decode("utf-8"),
                            f"{self._version.gitHead}:{self._version.workingTreeFingerprint}",
                            _utc_now_iso(),
                        ),
                    )
                    conn.execute(
                        "INSERT INTO runtime_families(family, count) VALUES(?, 1) "
                        "ON CONFLICT(family) DO UPDATE SET count = count + 1",
                        (family,),
                    )
                    conn.commit()
                except sqlite3.IntegrityError as exc:
                    conn.rollback()
                    raise RuntimeStoreError(f"insert failed: {exc}") from exc
            if not path.exists():
                path.write_bytes(body_bytes)
            index = self._load_index()
            index[content_hash] = {
                "family": family,
                "path": str(path.relative_to(self.cache_root)),
            }
            self._save_index(index)
            self._append_wal(_WALRecord(
                family=family,
                content_hash=content_hash,
                ts=_utc_now_iso(),
                op="put",
                payload={"body_keys": sorted(body.keys())},
            ))
        return content_hash

    def get(self, content_hash: str) -> RuntimeEntry:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            row = conn.execute(
                "SELECT content_hash, family, body_json FROM runtime_entries WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
        if row is None:
            raise RuntimeStoreError(f"cache miss for {content_hash}")
        body = json.loads(row[2])
        return RuntimeEntry(content_hash=row[0], family=row[1], body=body)

    def has(self, content_hash: str) -> bool:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            row = conn.execute(
                "SELECT 1 FROM runtime_entries WHERE content_hash = ?",
                (content_hash,),
            ).fetchone()
        return row is not None

    def evict(self, content_hash: str) -> None:
        with self._lock.acquire():
            with closing(sqlite3.connect(self._db_path)) as conn, conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT family FROM runtime_entries WHERE content_hash = ?",
                    (content_hash,),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    return
                family = row[0]
                conn.execute(
                    "DELETE FROM runtime_entries WHERE content_hash = ?",
                    (content_hash,),
                )
                conn.execute(
                    "UPDATE runtime_families SET count = MAX(count - 1, 0) WHERE family = ?",
                    (family,),
                )
                conn.commit()
            path = self._content_path(content_hash)
            if path.exists():
                path.unlink()
            index = self._load_index()
            index.pop(content_hash, None)
            self._save_index(index)

    def stats(self) -> Mapping[str, int]:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            total = conn.execute("SELECT COUNT(*) FROM runtime_entries").fetchone()[0]
        return {"entries": total, "wal_tail_length": self.wal_tail_length()}

    def runtime_status(
        self, *, policy: str = KnowledgeStatePolicy.DURABLE,
    ) -> RuntimeStatusReport:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            rows = conn.execute(
                "SELECT family, COUNT(*) FROM runtime_entries GROUP BY family"
            ).fetchall()
        family_counts = {row[0]: row[1] for row in rows}
        families = sorted(family_counts.keys())
        if policy == KnowledgeStatePolicy.DURABLE:
            local_only = family_counts.pop("local_only_chunk", 0)
            family_counts_filtered = dict(family_counts)
        else:
            local_only = 0
            family_counts_filtered = dict(family_counts)
        total = sum(family_counts_filtered.values())
        return RuntimeStatusReport(
            bound_version=self._version,
            backend=self.backend_name(),
            cache_entries=total,
            wal_tail_length=self.wal_tail_length(),
            families=tuple(families),
            family_counts=family_counts_filtered,
        )

    def wal_tail_length(self) -> int:
        if not self._wal_path.exists():
            return 0
        return sum(
            1 for line in self._wal_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    def recover_wal(self) -> None:
        records = self._load_wal()
        if not records:
            return
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            for record in records:
                row = conn.execute(
                    "SELECT 1 FROM runtime_entries WHERE content_hash = ?",
                    (record.content_hash,),
                ).fetchone()
                if row is None and record.op == "put":
                    conn.execute(
                        "INSERT OR REPLACE INTO runtime_entries(content_hash, family, body_json, version_id, created_at) VALUES(?, ?, ?, ?, ?)",
                        (
                            record.content_hash,
                            record.family,
                            "{}",
                            f"{self._version.gitHead}:{self._version.workingTreeFingerprint}",
                            record.ts,
                        ),
                    )
            conn.commit()
        self._wal_path.write_text("", encoding="utf-8")