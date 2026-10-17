"""Tests for the SQLite ingestion job store (E4)."""

from __future__ import annotations

import sqlite3
import unittest

from pi_platform.core.canonical.document_graph import (
    IngestionCheckpoint,
    IngestionState,
)
from pi_platform.ports.ingest.ingestion_job_store import (
    IngestionJobStoreError,
)
from pi_platform.adapters.runtime.sqlite_ingestion_job_store import (
    SqliteIngestionJobStore,
    migration_v2_add_ingestion_jobs_table,
)


def _new_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")
    return db


def _job(
    job_id: str = "job-1",
    source_id: str = "src-1",
    revision_id: str = "rev-1",
    strategy_version: str = "docling-pdf-v1",
    state: str = IngestionState.PENDING,
) -> IngestionCheckpoint:
    return IngestionCheckpoint(
        job_id=job_id, source_id=source_id, revision_id=revision_id,
        strategy_version=strategy_version, state=state,
    )


class SqliteIngestionJobStoreSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._db = _new_db()
        self._clock = ["2026-10-15T00:00:00Z"]
        self._store = SqliteIngestionJobStore(
            self._db, clock=lambda: self._clock[0],
        )

    def test_create_and_get(self) -> None:
        self._store.create(_job())
        job = self._store.get("job-1")
        self.assertIsNotNone(job)
        self.assertEqual(job.state, IngestionState.PENDING)
        self.assertEqual(job.source_id, "src-1")

    def test_create_duplicate_raises(self) -> None:
        self._store.create(_job())
        with self.assertRaises(IngestionJobStoreError):
            self._store.create(_job())

    def test_create_non_pending_raises(self) -> None:
        with self.assertRaises(IngestionJobStoreError):
            self._store.create(_job(state=IngestionState.RUNNING))

    def test_mark_running(self) -> None:
        self._store.create(_job())
        self._store.mark_running("job-1")
        self.assertEqual(
            self._store.get("job-1").state, IngestionState.RUNNING,
        )

    def test_mark_batch_done_merges_ranges(self) -> None:
        self._store.create(_job())
        self._store.mark_running("job-1")
        self._store.mark_batch_done("job-1", (1, 32))
        self._store.mark_batch_done("job-1", (33, 64))
        self._store.mark_batch_done("job-1", (10, 20))   # overlap
        job = self._store.get("job-1")
        # After merging, the single covered range is (1, 64)
        self.assertEqual(job.completed_ranges, ((1, 64),))
        self.assertEqual(job.next_page, 65)

    def test_mark_failed_retryable(self) -> None:
        self._store.create(_job())
        self._store.mark_running("job-1")
        self._store.mark_failed("job-1", (385, 416), "boom")
        job = self._store.get("job-1")
        self.assertEqual(job.state, IngestionState.FAILED_RETRYABLE)
        self.assertEqual(job.failed_range, (385, 416))
        self.assertEqual(job.error, "boom")
        self.assertEqual(job.next_page, 1)  # unchanged on failure

    def test_mark_completed_from_running(self) -> None:
        self._store.create(_job())
        self._store.mark_running("job-1")
        self._store.mark_batch_done("job-1", (1, 32))
        self._store.mark_completed("job-1")
        job = self._store.get("job-1")
        self.assertEqual(job.state, IngestionState.COMPLETED)
        self.assertEqual(job.next_page, -1)
        self.assertEqual(job.failed_range, ())

    def test_mark_cancelled(self) -> None:
        self._store.create(_job())
        self._store.mark_running("job-1")
        self._store.mark_cancelled("job-1")
        self.assertEqual(
            self._store.get("job-1").state, IngestionState.CANCELLED,
        )

    def test_list_for_source(self) -> None:
        self._store.create(_job("job-1", source_id="src-1"))
        self._store.create(_job("job-2", source_id="src-1"))
        self._store.create(_job("job-3", source_id="src-2"))
        self.assertEqual(len(self._store.list_for_source("src-1")), 2)
        self.assertEqual(len(self._store.list_for_source("src-2")), 1)
        self.assertEqual(len(self._store.list_for_source("src-3")), 0)

    def test_list_for_revision(self) -> None:
        self._store.create(_job("job-1", revision_id="rev-A"))
        self._store.create(_job("job-2", revision_id="rev-A"))
        self._store.create(_job("job-3", revision_id="rev-B"))
        self.assertEqual(len(self._store.list_for_revision("rev-A")), 2)
        self.assertEqual(len(self._store.list_for_revision("rev-B")), 1)

    def test_find_completed(self) -> None:
        self._store.create(_job("job-1", strategy_version="v1"))
        self._store.mark_running("job-1")
        self._store.mark_batch_done("job-1", (1, 32))
        self._store.mark_completed("job-1")
        self._store.create(_job("job-2", strategy_version="v2"))
        self._store.mark_running("job-2")
        self._store.mark_batch_done("job-2", (1, 32))
        self._store.mark_completed("job-2")
        hit = self._store.find_completed("src-1", "rev-1", "v1")
        self.assertIsNotNone(hit)
        self.assertEqual(hit.job_id, "job-1")
        miss = self._store.find_completed("src-1", "rev-1", "v3")
        self.assertIsNone(miss)

    def test_resume_after_crash(self) -> None:
        """E4 acceptance: a crash at page 417 must not invalidate
        completed batches. The next call resumes at page 417."""
        self._store.create(_job())
        self._store.mark_running("job-1")
        # Simulate pages 1-416 committed in 13 batches.
        for start in range(1, 416 + 1, 32):
            end = min(start + 31, 416)
            self._store.mark_batch_done("job-1", (start, end))
        # Crash at page 417.
        self._store.mark_failed("job-1", (417, 449), "boom")
        job = self._store.get("job-1")
        self.assertEqual(job.state, IngestionState.FAILED_RETRYABLE)
        self.assertEqual(job.failed_range, (417, 449))
        self.assertEqual(job.next_page, 417)
        # Resume.
        self._store.mark_batch_done("job-1", (417, 449))
        self._store.mark_batch_done("job-1", (450, 481))
        self._store.mark_completed("job-1")
        job = self._store.get("job-1")
        self.assertEqual(job.state, IngestionState.COMPLETED)
        self.assertEqual(job.completed_ranges, ((1, 481),))
        self.assertEqual(job.next_page, -1)

    def test_migration_idempotent(self) -> None:
        # Already called in __init__; call again to confirm.
        migration_v2_add_ingestion_jobs_table(self._db)
        migration_v2_add_ingestion_jobs_table(self._db)
        # Store still works.
        self._store.create(_job())
        self.assertIsNotNone(self._store.get("job-1"))

    def test_stats_counts_states(self) -> None:
        self._store.create(_job("job-1"))
        self._store.create(_job("job-2"))
        self._store.mark_running("job-1")
        self._store.mark_batch_done("job-1", (1, 32))
        self._store.mark_completed("job-1")
        self._store.mark_running("job-2")
        self._store.mark_failed("job-2", (10, 20), "boom")
        stats = self._store.stats()
        self.assertEqual(stats["total"], 2)
        self.assertEqual(stats[IngestionState.COMPLETED], 1)
        self.assertEqual(stats[IngestionState.FAILED_RETRYABLE], 1)


class IngestionJobStorePortContractTests(unittest.TestCase):
    def test_port_is_abstract(self) -> None:
        from pi_platform.ports.ingest.ingestion_job_store import (
            IngestionJobStorePort,
        )
        import inspect
        self.assertTrue(inspect.isabstract(IngestionJobStorePort))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
