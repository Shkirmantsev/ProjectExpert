"""End-to-end PDF batch-resume test (E4 acceptance).

A crash at page 417 must not invalidate completed batches. The
next call resumes at page 417 with full state recovery.
"""

from __future__ import annotations

import sqlite3
import unittest

from pi_platform.core.canonical.document_graph import IngestionState
from pi_platform.adapters.runtime.sqlite_ingestion_job_store import (
    SqliteIngestionJobStore,
)


def _new_db() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    return db


class PdfBatchResumeEndToEndTests(unittest.TestCase):
    """Synthesise a 600-page ingestion that crashes at page 417."""

    def test_600_page_resume_after_crash(self) -> None:
        db = _new_db()
        store = SqliteIngestionJobStore(db, clock=lambda: "t")
        # Create the job.
        from pi_platform.core.canonical.document_graph import (
            IngestionCheckpoint,
        )
        job = IngestionCheckpoint(
            job_id="pdf-job-1", source_id="pdf-1", revision_id="rev-1",
            strategy_version="docling-pdf-v1",
            state=IngestionState.PENDING,
        )
        store.create(job)
        store.mark_running("pdf-job-1")
        # Simulate 13 batches of pages 1..416 (32-page windows).
        for start in range(1, 416 + 1, 32):
            end = min(start + 31, 416)
            store.mark_batch_done("pdf-job-1", (start, end))
        # Crash at page 417.
        store.mark_failed("pdf-job-1", (417, 449), "oom")
        # Read the persisted state.
        snap = store.get("pdf-job-1")
        self.assertEqual(snap.state, IngestionState.FAILED_RETRYABLE)
        self.assertEqual(snap.failed_range, (417, 449))
        self.assertEqual(snap.completed_ranges, ((1, 416),))
        self.assertEqual(snap.next_page, 417)
        # Resume: 33..480, 481..600.
        store.mark_batch_done("pdf-job-1", (417, 449))
        store.mark_batch_done("pdf-job-1", (450, 481))
        store.mark_batch_done("pdf-job-1", (482, 513))
        store.mark_batch_done("pdf-job-1", (514, 545))
        store.mark_batch_done("pdf-job-1", (546, 577))
        store.mark_batch_done("pdf-job-1", (578, 600))
        store.mark_completed("pdf-job-1")
        snap = store.get("pdf-job-1")
        self.assertEqual(snap.state, IngestionState.COMPLETED)
        self.assertEqual(snap.completed_ranges, ((1, 600),))
        self.assertEqual(snap.next_page, -1)
        # find_completed short-circuits a future prescan.
        found = store.find_completed("pdf-1", "rev-1", "docling-pdf-v1")
        self.assertIsNotNone(found)
        self.assertEqual(found.job_id, "pdf-job-1")

    def test_600_page_partial_crash_at_385(self) -> None:
        """Plan §21.2 example: crash at page 385 mid-window."""
        db = _new_db()
        store = SqliteIngestionJobStore(db, clock=lambda: "t")
        from pi_platform.core.canonical.document_graph import (
            IngestionCheckpoint,
        )
        job = IngestionCheckpoint(
            job_id="pdf-job-2", source_id="pdf-2", revision_id="rev-2",
            strategy_version="docling-pdf-v1",
            state=IngestionState.PENDING,
        )
        store.create(job)
        store.mark_running("pdf-job-2")
        # 12 batches of 32 pages each, total 384.
        for start in range(1, 384 + 1, 32):
            end = min(start + 31, 384)
            store.mark_batch_done("pdf-job-2", (start, end))
        # Crash mid-window on page 385-416.
        store.mark_failed("pdf-job-2", (385, 416), "docling oom")
        snap = store.get("pdf-job-2")
        self.assertEqual(snap.completed_ranges, ((1, 384),))
        self.assertEqual(snap.failed_range, (385, 416))
        self.assertEqual(snap.next_page, 385)
        # Recovery: full window of 385-416.
        store.mark_batch_done("pdf-job-2", (385, 416))
        self.assertEqual(
            store.get("pdf-job-2").completed_ranges, ((1, 416),),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
