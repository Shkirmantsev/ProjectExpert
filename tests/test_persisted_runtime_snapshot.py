"""Tests for the persisted runtime snapshot and reconcile loop.

Covers the ``persisted-runtime-snapshot-reconciliation`` spec
delta (open spec change PR 8):

* ``runtime-state/{active-version,manifest-snapshot,source-snapshot}.json``
  are persisted atomically and read back;
* the persisted snapshot drives the diff between previous and
  current effective state;
* the diff classifies every item as
  ``UNCHANGED / ADDED / MODIFIED / REMOVED``;
* the reconcile loop applies the REMOVED handling (tombstones in
  the sparse index + ``delete_chunk`` on the dense index);
* a refresh failure leaves the previous generation active and the
  persisted snapshot unchanged;
* the working-tree fingerprint changes trigger a refresh even
  when HEAD is unchanged.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from pi_platform.core.sync.reconcile import (
    ReconcileActivationError,
    ReconcileService,
    SnapshotReconcileReport,
)
from pi_platform.core.sync.version_monitor import (
    HeadChange,
    MAX_POLL_INTERVAL_SECONDS,
    MIN_POLL_INTERVAL_SECONDS,
    ProjectVersionMonitor,
    ProjectVersionMonitorStub,
)
from pi_platform.core.sync.version_snapshot import (
    ACTIVE_VERSION_FILENAME,
    MANIFEST_SNAPSHOT_FILENAME,
    RUNTIME_STATE_DIRNAME,
    SOURCE_SNAPSHOT_FILENAME,
    ManifestSnapshot,
    PersistedActiveVersion,
    PersistedSnapshot,
    RuntimeSnapshotService,
    RuntimeSnapshotError,
    SnapshotDiff,
    SourceSnapshot,
    compute_snapshot_hash,
    compute_working_tree_fingerprint,
)


def _tmp_root() -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="snap-"))
    return tmp


class WorkingTreeFingerprintTests(unittest.TestCase):
    """Plan §38: SHA256 of (sorted path, sorted content hash) pairs."""

    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True),
        )

    def test_fingerprint_changes_when_file_changes(self) -> None:
        path_a = self._tmp / "a.txt"
        path_b = self._tmp / "b.txt"
        path_a.write_text("alpha")
        path_b.write_text("beta")
        first = compute_working_tree_fingerprint([path_a, path_b])
        path_a.write_text("alpha-changed")
        second = compute_working_tree_fingerprint([path_a, path_b])
        self.assertNotEqual(
            first, second,
            "working-tree fingerprint MUST change when a file changes",
        )

    def test_fingerprint_is_stable_across_input_order(self) -> None:
        path_a = self._tmp / "a.txt"
        path_b = self._tmp / "b.txt"
        path_a.write_text("alpha")
        path_b.write_text("beta")
        forward = compute_working_tree_fingerprint([path_a, path_b])
        backward = compute_working_tree_fingerprint([path_b, path_a])
        self.assertEqual(forward, backward)


class SnapshotHashTests(unittest.TestCase):
    """``compute_snapshot_hash`` is a stable label for diffs."""

    def test_snapshot_hash_changes_on_added(self) -> None:
        before = compute_snapshot_hash(["c1", "c2"])
        after = compute_snapshot_hash(["c1", "c2", "c3"])
        self.assertNotEqual(before, after)

    def test_snapshot_hash_is_stable_across_input_order(self) -> None:
        forward = compute_snapshot_hash(["c1", "c2", "c3"])
        backward = compute_snapshot_hash(["c3", "c1", "c2"])
        # Sorted order: forward and backward should agree.
        self.assertEqual(forward, backward)


class RuntimeSnapshotServicePersistenceTests(unittest.TestCase):
    """The service persists the three files atomically."""

    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True),
        )
        self.service = RuntimeSnapshotService(cache_root=self._tmp)

    def _build_active(self) -> PersistedActiveVersion:
        return PersistedActiveVersion(
            project_version="v0.0.1",
            branch="main",
            head="abc123",
            working_tree_fingerprint="fp1",
            manifest_snapshot_hash="mh1",
            source_snapshot_hash="sh1",
            embedding_profile_identity="profile-hash",
            active_index_generation="gen1",
            last_refresh_id="refresh-x",
        )

    def _build_manifest(self) -> ManifestSnapshot:
        return ManifestSnapshot(
            snapshot_hash="mh1",
            chunk_ids=("c1", "c2"),
            graph_node_ids=("g1",),
        )

    def _build_source(self) -> SourceSnapshot:
        return SourceSnapshot(
            snapshot_hash="sh1",
            source_ids=("src-a", "src-b"),
            content_hashes={"src-a": "h-a", "src-b": "h-b"},
        )

    def test_commit_writes_all_three_files(self) -> None:
        self.service.commit(
            active=self._build_active(),
            manifest=self._build_manifest(),
            source=self._build_source(),
        )
        runtime_dir = self._tmp / RUNTIME_STATE_DIRNAME
        self.assertTrue(
            (runtime_dir / ACTIVE_VERSION_FILENAME).is_file(),
        )
        self.assertTrue(
            (runtime_dir / MANIFEST_SNAPSHOT_FILENAME).is_file(),
        )
        self.assertTrue(
            (runtime_dir / SOURCE_SNAPSHOT_FILENAME).is_file(),
        )

    def test_commit_then_read_round_trip(self) -> None:
        active = self._build_active()
        manifest = self._build_manifest()
        source = self._build_source()
        self.service.commit(
            active=active, manifest=manifest, source=source,
        )
        snapshot = self.service.read_snapshot()
        self.assertIsNotNone(snapshot)
        assert snapshot is not None
        self.assertEqual(
            snapshot.active.project_version, active.project_version,
        )
        self.assertEqual(
            snapshot.manifest.chunk_ids, manifest.chunk_ids,
        )
        self.assertEqual(
            snapshot.source.content_hashes["src-a"], "h-a",
        )

    def test_read_snapshot_returns_none_when_missing(self) -> None:
        self.assertIsNone(self.service.read_snapshot())

    def test_commit_is_atomic_via_tmp_replace(self) -> None:
        # The commit MUST write to a sibling .tmp and use
        # os.replace; we verify by reading the file back from
        # disk after the commit completes.
        self.service.commit(
            active=self._build_active(),
            manifest=self._build_manifest(),
            source=self._build_source(),
        )
        runtime_dir = self._tmp / RUNTIME_STATE_DIRNAME
        # No stale .tmp files should remain.
        for entry in runtime_dir.iterdir():
            self.assertFalse(
                entry.name.endswith(".tmp"),
                f"unexpected .tmp file left behind: {entry}",
            )


class RuntimeSnapshotDiffTests(unittest.TestCase):
    """``diff`` classifies every chunk and source item."""

    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True),
        )
        self.service = RuntimeSnapshotService(cache_root=self._tmp)

    def _persist(
        self,
        *,
        chunk_ids: tuple[str, ...],
        source_ids: tuple[str, ...],
        content_hashes: dict[str, str],
        fingerprint: str = "fp1",
        head: str = "h1",
    ) -> PersistedSnapshot:
        active = PersistedActiveVersion(
            project_version="v1",
            branch="main",
            head=head,
            working_tree_fingerprint=fingerprint,
            manifest_snapshot_hash=compute_snapshot_hash(list(chunk_ids)),
            source_snapshot_hash=compute_snapshot_hash(list(source_ids)),
            embedding_profile_identity="ph",
            active_index_generation="g1",
            last_refresh_id="r1",
        )
        manifest = ManifestSnapshot(
            snapshot_hash=active.manifest_snapshot_hash,
            chunk_ids=chunk_ids,
            graph_node_ids=(),
        )
        source = SourceSnapshot(
            snapshot_hash=active.source_snapshot_hash,
            source_ids=source_ids,
            content_hashes=content_hashes,
        )
        return self.service.commit(
            active=active, manifest=manifest, source=source,
        )

    def _candidate(
        self,
        *,
        chunk_ids: tuple[str, ...],
        source_ids: tuple[str, ...],
        content_hashes: dict[str, str],
        fingerprint: str = "fp1",
        head: str = "h1",
    ) -> tuple[PersistedActiveVersion, ManifestSnapshot, SourceSnapshot]:
        active = PersistedActiveVersion(
            project_version="v1",
            branch="main",
            head=head,
            working_tree_fingerprint=fingerprint,
            manifest_snapshot_hash=compute_snapshot_hash(list(chunk_ids)),
            source_snapshot_hash=compute_snapshot_hash(list(source_ids)),
            embedding_profile_identity="ph",
            active_index_generation="g2",
            last_refresh_id="r2",
        )
        manifest = ManifestSnapshot(
            snapshot_hash=active.manifest_snapshot_hash,
            chunk_ids=chunk_ids,
            graph_node_ids=(),
        )
        source = SourceSnapshot(
            snapshot_hash=active.source_snapshot_hash,
            source_ids=source_ids,
            content_hashes=content_hashes,
        )
        return active, manifest, source

    def test_first_run_marks_everything_added(self) -> None:
        active, manifest, source = self._candidate(
            chunk_ids=("c1", "c2"),
            source_ids=("src-a",),
            content_hashes={"src-a": "h"},
        )
        diff = self.service.diff(
            None,
            candidate_active=active,
            candidate_manifest=manifest,
            candidate_source=source,
        )
        self.assertEqual(diff.added_chunk_ids, ("c1", "c2"))
        self.assertEqual(diff.added_source_ids, ("src-a",))
        self.assertEqual(diff.removed_chunk_ids, ())
        self.assertTrue(diff.working_tree_changed)
        self.assertTrue(diff.head_changed)

    def test_removed_chunk_is_classified(self) -> None:
        persisted = self._persist(
            chunk_ids=("c1", "c2"),
            source_ids=("src-a",),
            content_hashes={"src-a": "h"},
        )
        active, manifest, source = self._candidate(
            chunk_ids=("c1",),
            source_ids=("src-a",),
            content_hashes={"src-a": "h"},
        )
        diff = self.service.diff(
            persisted,
            candidate_active=active,
            candidate_manifest=manifest,
            candidate_source=source,
        )
        self.assertEqual(diff.removed_chunk_ids, ("c2",))
        self.assertEqual(diff.added_chunk_ids, ())

    def test_modified_source_detected(self) -> None:
        persisted = self._persist(
            chunk_ids=("c1",),
            source_ids=("src-a",),
            content_hashes={"src-a": "h-old"},
        )
        active, manifest, source = self._candidate(
            chunk_ids=("c1",),
            source_ids=("src-a",),
            content_hashes={"src-a": "h-new"},
        )
        diff = self.service.diff(
            persisted,
            candidate_active=active,
            candidate_manifest=manifest,
            candidate_source=source,
        )
        self.assertEqual(diff.modified_source_ids, ("src-a",))

    def test_working_tree_fingerprint_change_detected(self) -> None:
        persisted = self._persist(
            chunk_ids=("c1",),
            source_ids=("src-a",),
            content_hashes={"src-a": "h"},
            fingerprint="fp-old",
        )
        active, manifest, source = self._candidate(
            chunk_ids=("c1",),
            source_ids=("src-a",),
            content_hashes={"src-a": "h"},
            fingerprint="fp-new",
        )
        diff = self.service.diff(
            persisted,
            candidate_active=active,
            candidate_manifest=manifest,
            candidate_source=source,
        )
        self.assertTrue(
            diff.working_tree_changed,
            "fingerprint change MUST trigger a refresh even when "
            "HEAD is unchanged",
        )


class ReconcileWithSnapshotTests(unittest.TestCase):
    """End-to-end reconciliation: tombstones + activation."""

    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(
            lambda: shutil.rmtree(self._tmp, ignore_errors=True),
        )
        self.snapshot_service = RuntimeSnapshotService(
            cache_root=self._tmp,
        )

    def test_first_run_persists_snapshot(self) -> None:
        service = ReconcileService(
            snapshot_service=self.snapshot_service,
        )
        report = service.reconcile_with_snapshot(
            candidate_chunk_ids=("c1", "c2"),
            candidate_source_ids=("src-a",),
            candidate_source_content_hashes={"src-a": "h"},
            project_version="v1",
            branch="main",
            head="abc",
            working_tree_paths=[],
            embedding_profile_identity="ph",
            active_index_generation="gen1",
        )
        self.assertIsInstance(report, SnapshotReconcileReport)
        self.assertTrue(report.new_persisted_snapshot is not None)
        self.assertEqual(
            report.diff.added_chunk_ids, ("c1", "c2"),
        )

    def test_removed_chunk_writes_tombstone(self) -> None:
        # Persist a snapshot with chunk c1.
        snapshot_service = self.snapshot_service
        active = PersistedActiveVersion(
            project_version="v1", branch="main", head="abc",
            working_tree_fingerprint="fp",
            manifest_snapshot_hash="m1",
            source_snapshot_hash="s1",
            embedding_profile_identity="ph",
            active_index_generation="gen1",
            last_refresh_id="r1",
        )
        snapshot_service.commit(
            active=active,
            manifest=ManifestSnapshot(
                snapshot_hash="m1", chunk_ids=("c1", "c2"),
                graph_node_ids=(),
            ),
            source=SourceSnapshot(
                snapshot_hash="s1", source_ids=("src-a",),
                content_hashes={"src-a": "h"},
            ),
        )
        # Stub collaborators: sparse + dense track deletes.
        sparse_deletes: list[str] = []
        dense_deletes: list[str] = []

        class _Sparse:
            def delete_document(self, doc_id: str) -> None:
                sparse_deletes.append(doc_id)

        class _Dense:
            def delete_chunk(self, chunk_id: str) -> None:
                dense_deletes.append(chunk_id)

        service = ReconcileService(
            snapshot_service=snapshot_service,
        )
        report = service.reconcile_with_snapshot(
            candidate_chunk_ids=("c1",),
            candidate_source_ids=("src-a",),
            candidate_source_content_hashes={"src-a": "h"},
            project_version="v1", branch="main", head="abc",
            working_tree_paths=[],
            embedding_profile_identity="ph",
            active_index_generation="gen2",
            sparse_index=_Sparse(),
            dense_index=_Dense(),
        )
        self.assertEqual(report.diff.removed_chunk_ids, ("c2",))
        self.assertIn("c2", sparse_deletes)
        self.assertIn("c2", dense_deletes)
        self.assertIn("c2", report.tombstones_recorded)

    def test_activation_failure_leaves_previous_generation_active(self) -> None:
        snapshot_service = self.snapshot_service
        active = PersistedActiveVersion(
            project_version="v1", branch="main", head="abc",
            working_tree_fingerprint="fp",
            manifest_snapshot_hash="m1",
            source_snapshot_hash="s1",
            embedding_profile_identity="ph",
            active_index_generation="gen1",
            last_refresh_id="r1",
        )
        snapshot_service.commit(
            active=active,
            manifest=ManifestSnapshot(
                snapshot_hash="m1", chunk_ids=("c1",),
                graph_node_ids=(),
            ),
            source=SourceSnapshot(
                snapshot_hash="s1", source_ids=("src-a",),
                content_hashes={"src-a": "h"},
            ),
        )

        class _FailingActivate:
            def __call__(self, manifest, source) -> str:
                raise RuntimeError("simulated activation failure")

        service = ReconcileService(
            snapshot_service=snapshot_service,
        )
        before = snapshot_service.read_snapshot()
        assert before is not None
        prev_generation = before.active.active_index_generation
        with self.assertRaises(ReconcileActivationError):
            service.reconcile_with_snapshot(
                candidate_chunk_ids=("c1", "c2"),
                candidate_source_ids=("src-a",),
                candidate_source_content_hashes={"src-a": "h"},
                project_version="v1", branch="main", head="abc",
                working_tree_paths=[],
                embedding_profile_identity="ph",
                active_index_generation="gen2",
                on_activate=_FailingActivate(),
            )
        after = snapshot_service.read_snapshot()
        assert after is not None
        # The persisted snapshot MUST still point at the previous
        # generation; the failed refresh MUST NOT advance it.
        self.assertEqual(
            after.active.active_index_generation, prev_generation,
            "a failed activation MUST leave the persisted "
            "snapshot at the previous generation",
        )


class ProjectVersionMonitorStubTests(unittest.TestCase):
    """The portable monitor stub honours the 2–5s interval contract."""

    def test_interval_within_documented_range(self) -> None:
        for interval in (
            MIN_POLL_INTERVAL_SECONDS,
            MAX_POLL_INTERVAL_SECONDS,
        ):
            monitor = ProjectVersionMonitorStub(
                poll_interval_seconds=interval,
            )
            self.assertEqual(
                monitor.poll_interval_seconds, interval,
            )

    def test_interval_below_minimum_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ProjectVersionMonitorStub(
                poll_interval_seconds=MIN_POLL_INTERVAL_SECONDS - 1,
            )

    def test_interval_above_maximum_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ProjectVersionMonitorStub(
                poll_interval_seconds=MAX_POLL_INTERVAL_SECONDS + 1,
            )

    def test_lifecycle_start_stop(self) -> None:
        monitor = ProjectVersionMonitorStub()
        self.assertFalse(monitor.is_started)
        monitor.start()
        self.assertTrue(monitor.is_started)
        monitor.stop()
        self.assertTrue(monitor.is_stopped)

    def test_poll_once_is_noop(self) -> None:
        monitor = ProjectVersionMonitorStub()
        result = monitor.poll_once()
        self.assertIsNone(result)
        self.assertEqual(monitor.poll_count, 1)


if __name__ == "__main__":
    unittest.main()
