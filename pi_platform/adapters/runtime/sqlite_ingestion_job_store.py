"""SQLite-backed ingestion job store (E4).

Stores resumable ingestion jobs in a single ``ingestion_jobs``
table inside the existing ``runtime.db``. The schema is
additive; the existing ``runtime_entries`` table is not
touched.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from pi_platform.core.canonical.document_graph import (
    IngestionCheckpoint,
    IngestionState,
)
from pi_platform.ports.ingest.ingestion_job_store import (
    IngestionJobStoreError,
    IngestionJobStorePort,
)


__all__ = [
    "SqliteIngestionJobStore",
    "migration_v2_add_ingestion_jobs_table",
]


SCHEMA = """
CREATE TABLE IF NOT EXISTS ingestion_jobs (
    job_id           TEXT PRIMARY KEY,
    source_id        TEXT NOT NULL,
    revision_id      TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    state            TEXT NOT NULL,
    next_page        INTEGER NOT NULL DEFAULT 1,
    completed_ranges TEXT NOT NULL DEFAULT '[]',
    failed_range     TEXT NOT NULL DEFAULT '[]',
    error            TEXT NOT NULL DEFAULT '',
    started_at       TEXT NOT NULL DEFAULT '',
    updated_at       TEXT NOT NULL DEFAULT ''
)
""".strip()

# Index that makes the (source_id, revision_id, strategy_version)
# short-circuit lookup fast.
INDEX = (
    "CREATE INDEX IF NOT EXISTS ingestion_jobs_lookup "
    "ON ingestion_jobs (source_id, revision_id, strategy_version, state)"
)


def migration_v2_add_ingestion_jobs_table(
    db: sqlite3.Connection,
) -> None:
    """Additive migration: create the ingestion_jobs table and
    its lookup index. Idempotent."""
    db.execute(SCHEMA)
    db.execute(INDEX)
    db.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_checkpoint(row: sqlite3.Row) -> IngestionCheckpoint:
    return IngestionCheckpoint(
        job_id=row["job_id"],
        source_id=row["source_id"],
        revision_id=row["revision_id"],
        strategy_version=row["strategy_version"],
        state=row["state"],
        next_page=int(row["next_page"]),
        completed_ranges=tuple(
            tuple(int(a) for a in pair)
            for pair in json.loads(row["completed_ranges"] or "[]")
        ),
        failed_range=tuple(
            int(a) for a in json.loads(row["failed_range"] or "[]")
        ),
        error=row["error"] or "",
        started_at=row["started_at"] or "",
        updated_at=row["updated_at"] or "",
    )


def _merge_ranges(
    ranges: List[Tuple[int, int]], new: Tuple[int, int],
) -> List[Tuple[int, int]]:
    """Merge an in-order range into a sorted, non-overlapping
    list. Used to keep ``completed_ranges`` compact."""
    if not new or new[0] > new[1]:
        return ranges
    merged = list(ranges)
    merged.append((int(new[0]), int(new[1])))
    merged.sort()
    out: List[Tuple[int, int]] = []
    for r in merged:
        if out and r[0] <= out[-1][1] + 1:
            out[-1] = (out[-1][0], max(out[-1][1], r[1]))
        else:
            out.append(r)
    return out


def _next_page_from_ranges(
    ranges: Sequence[Tuple[int, int]],
) -> int:
    """Return the first page NOT yet covered by the merged
    completed ranges, or 1 if nothing is completed."""
    if not ranges:
        return 1
    return max(end for _, end in ranges) + 1


class SqliteIngestionJobStore(IngestionJobStorePort):
    """SQLite adapter for the resumable ingestion job store."""

    def __init__(
        self,
        db: sqlite3.Connection,
        *,
        clock: Callable[[], str] = _utc_now,
    ) -> None:
        if db is None:
            raise IngestionJobStoreError("db connection is required")
        self._db = db
        self._clock = clock
        # Ensure the schema is present (idempotent).
        migration_v2_add_ingestion_jobs_table(db)

    # -- public API --------------------------------------------------

    def create(self, job: IngestionCheckpoint) -> None:
        if job.state != IngestionState.PENDING:
            raise IngestionJobStoreError(
                f"create() requires state=PENDING, got {job.state!r}"
            )
        try:
            self._db.execute(
                """
                INSERT INTO ingestion_jobs (
                    job_id, source_id, revision_id, strategy_version,
                    state, next_page, completed_ranges, failed_range,
                    error, started_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id, job.source_id, job.revision_id,
                    job.strategy_version, job.state, job.next_page,
                    json.dumps(list(job.completed_ranges)),
                    json.dumps(list(job.failed_range)),
                    job.error, job.started_at, job.updated_at,
                ),
            )
            self._db.commit()
        except sqlite3.IntegrityError as exc:
            raise IngestionJobStoreError(
                f"ingestion job {job.job_id!r} already exists"
            ) from exc

    def mark_running(self, job_id: str) -> None:
        with self._db:
            self._db.execute(
                """
                UPDATE ingestion_jobs
                   SET state = ?, updated_at = ?,
                       started_at = COALESCE(NULLIF(started_at, ''), ?)
                 WHERE job_id = ?
                """,
                (IngestionState.RUNNING, self._clock(), self._clock(),
                 job_id),
            )

    def mark_batch_done(
        self, job_id: str, completed_range: Tuple[int, int],
    ) -> None:
        row = self._fetch_row(job_id)
        if row is None:
            raise IngestionJobStoreError(
                f"ingestion job {job_id!r} not found"
            )
        ranges = list(_row_to_checkpoint(row).completed_ranges)
        merged = _merge_ranges(ranges, completed_range)
        next_page = _next_page_from_ranges(merged)
        with self._db:
            self._db.execute(
                """
                UPDATE ingestion_jobs
                   SET completed_ranges = ?, next_page = ?,
                       state = ?, updated_at = ?,
                       failed_range = '[]', error = ''
                 WHERE job_id = ?
                """,
                (json.dumps([list(r) for r in merged]), next_page,
                 IngestionState.RUNNING, self._clock(), job_id),
            )

    def mark_failed(
        self, job_id: str, failed_range: Tuple[int, int], error: str,
    ) -> None:
        with self._db:
            self._db.execute(
                """
                UPDATE ingestion_jobs
                   SET state = ?, failed_range = ?, error = ?,
                       updated_at = ?
                 WHERE job_id = ?
                """,
                (IngestionState.FAILED_RETRYABLE,
                 json.dumps(list(failed_range)), error,
                 self._clock(), job_id),
            )

    def mark_completed(self, job_id: str) -> None:
        with self._db:
            self._db.execute(
                """
                UPDATE ingestion_jobs
                   SET state = ?, updated_at = ?, next_page = -1,
                       failed_range = '[]', error = ''
                 WHERE job_id = ?
                """,
                (IngestionState.COMPLETED, self._clock(), job_id),
            )

    def mark_cancelled(self, job_id: str) -> None:
        with self._db:
            self._db.execute(
                """
                UPDATE ingestion_jobs
                   SET state = ?, updated_at = ?
                 WHERE job_id = ?
                """,
                (IngestionState.CANCELLED, self._clock(), job_id),
            )

    def get(self, job_id: str) -> Optional[IngestionCheckpoint]:
        row = self._fetch_row(job_id)
        return _row_to_checkpoint(row) if row is not None else None

    def list_for_source(
        self, source_id: str,
    ) -> Sequence[IngestionCheckpoint]:
        cur = self._db.execute(
            "SELECT * FROM ingestion_jobs WHERE source_id = ? "
            "ORDER BY started_at, job_id",
            (source_id,),
        )
        return tuple(_row_to_checkpoint(r) for r in cur.fetchall())

    def list_for_revision(
        self, revision_id: str,
    ) -> Sequence[IngestionCheckpoint]:
        cur = self._db.execute(
            "SELECT * FROM ingestion_jobs WHERE revision_id = ? "
            "ORDER BY started_at, job_id",
            (revision_id,),
        )
        return tuple(_row_to_checkpoint(r) for r in cur.fetchall())

    def find_completed(
        self, source_id: str, revision_id: str, strategy_version: str,
    ) -> Optional[IngestionCheckpoint]:
        cur = self._db.execute(
            "SELECT * FROM ingestion_jobs "
            " WHERE source_id = ? AND revision_id = ? "
            "   AND strategy_version = ? AND state = ? "
            " ORDER BY updated_at DESC LIMIT 1",
            (source_id, revision_id, strategy_version,
             IngestionState.COMPLETED),
        )
        row = cur.fetchone()
        return _row_to_checkpoint(row) if row is not None else None

    def stats(self) -> Mapping[str, int]:
        cur = self._db.execute(
            "SELECT state, COUNT(*) AS n FROM ingestion_jobs GROUP BY state"
        )
        out: Dict[str, int] = {"total": 0}
        for r in cur.fetchall():
            out[r["state"]] = int(r["n"])
            out["total"] += int(r["n"])
        return out

    # -- internal helpers --------------------------------------------

    def _fetch_row(self, job_id: str) -> Optional[sqlite3.Row]:
        cur = self._db.execute(
            "SELECT * FROM ingestion_jobs WHERE job_id = ?", (job_id,),
        )
        return cur.fetchone()
