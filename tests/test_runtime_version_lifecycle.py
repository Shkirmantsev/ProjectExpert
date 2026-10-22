"""Portable version detection and serving while a candidate is unavailable."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

from pi_platform.adapters.ui.http_server import UiHttpServer
from pi_platform.core.sync.version_monitor import PollingProjectVersionMonitor, read_project_version


class VersionMonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.com")
        self.git("config", "user.name", "Test")
        (self.repo / "service.py").write_text("return_value = 'A'\n")
        self.git("add", ".")
        self.git("commit", "-qm", "A")
        self.branch = self.git("branch", "--show-current").strip()

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args],
                              check=True, capture_output=True, text=True).stdout

    def test_branch_and_dirty_content_matrix(self):
        events = []
        monitor = PollingProjectVersionMonitor(self.repo, on_change=events.append)
        monitor.poll_once()
        self.assertIsNone(monitor.poll_once())
        # Same HEAD, successive dirty edits have identical porcelain status.
        (self.repo / "service.py").write_text("return_value = 'dirty-one'\n")
        self.assertEqual(monitor.poll_once().kind, "working-tree")
        (self.repo / "service.py").write_text("return_value = 'dirty-two'\n")
        self.assertEqual(monitor.poll_once().kind, "working-tree")
        self.git("restore", "service.py")
        self.assertEqual(monitor.poll_once().kind, "working-tree")
        # Identical knowledge on another branch still changes version identity.
        self.git("checkout", "-qb", "identical")
        self.assertEqual(monitor.poll_once().kind, "head")
        # A committed addition, modification and removal all change corpus identity.
        (self.repo / "added.md").write_text("Added evidence")
        self.git("add", ".")
        self.git("commit", "-qm", "addition")
        self.assertEqual(monitor.poll_once().kind, "both")
        (self.repo / "service.py").write_text("return_value = 'B'\n")
        self.git("commit", "-qam", "modified")
        self.assertEqual(monitor.poll_once().kind, "both")
        self.git("rm", "added.md")
        self.git("commit", "-qm", "removed")
        self.assertEqual(monitor.poll_once().kind, "both")
        self.git("checkout", "-q", self.branch)
        self.assertEqual(monitor.poll_once().kind, "both")
        # Canonical graph changes must refresh even with no source file edits.
        knowledge = self.repo / "project-knowledge" / "graph"
        knowledge.mkdir(parents=True)
        (knowledge / "edges.json").write_text('{"edge":"new"}')
        self.assertEqual(monitor.poll_once().kind, "working-tree")

    def test_actual_graph_jsonl_shards_and_edge_index_trigger_dirty_refresh(self):
        graph = self.repo / "project-knowledge" / "graph"
        node = graph / "nodes" / "ab" / "shard.jsonl"
        edge = graph / "edges" / "cd" / "shard.jsonl"
        index = graph / "edge-index.jsonl"
        for path, body in ((node, '{"id":"node-A"}'), (edge, '{"sourceId":"A","targetId":"B"}'), (index, '{"A":["B"]}')):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body + "\n")
        monitor = PollingProjectVersionMonitor(self.repo, on_change=lambda _: None)
        monitor.poll_once()
        for path in (node, edge, index):
            with self.subTest(path=path.relative_to(graph)):
                path.write_text(path.read_text().replace('A', 'changed-A'))
                event = monitor.poll_once()
                self.assertIsNotNone(event)
                self.assertEqual(event.kind, "working-tree")
                self.assertIsNone(monitor.poll_once())

    def test_failed_refresh_retries_without_another_edit(self):
        calls = []
        def refresh(event):
            calls.append(event)
            if len(calls) == 1:
                raise RuntimeError("temporary model failure")
        monitor = PollingProjectVersionMonitor(self.repo, on_change=refresh)
        with self.assertRaisesRegex(RuntimeError, "model failure"):
            monitor.poll_once()
        self.assertIsNotNone(monitor.poll_once())
        self.assertIsNone(monitor.poll_once())
        self.assertEqual(len(calls), 2)

    def test_edit_during_indexing_is_not_lost(self):
        calls = []
        def refresh(event):
            calls.append(event)
            if len(calls) == 1:
                (self.repo / "service.py").write_text("changed during indexing")
        monitor = PollingProjectVersionMonitor(self.repo, on_change=refresh)
        monitor.poll_once()
        self.assertEqual(monitor.poll_once().kind, "working-tree")
        self.assertEqual(len(calls), 2)

    def test_runtime_writes_do_not_trigger_refresh(self):
        before = read_project_version(self.repo)
        cache = self.repo / ".project-intelligence-cache"
        cache.mkdir()
        (cache / "generation.md").write_text("runtime")
        (cache / "readiness.json").write_text('{"ready": true}')
        self.assertEqual(read_project_version(self.repo), before)

    def test_explicit_refresh_runs_even_when_source_and_settings_are_unchanged(self):
        events = []
        monitor = PollingProjectVersionMonitor(self.repo, on_change=events.append)
        monitor.poll_once()
        self.assertIsNone(monitor.poll_once())
        monitor.request_refresh()
        self.assertIsNotNone(monitor.poll_once())
        self.assertEqual(len(events), 2)
        self.assertIsNone(monitor.poll_once())

    def test_interval_must_be_portable_polling_range(self):
        for interval in (0, 1, 6):
            with self.assertRaises(ValueError):
                PollingProjectVersionMonitor(self.repo, on_change=lambda _: None,
                                             poll_interval_seconds=interval)


class BootstrapHttpTests(unittest.TestCase):
    def test_http_stays_live_and_retrieval_fails_closed_before_and_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A service stand-in deliberately fails if retrieval reaches it.
            service = SimpleNamespace(_repo_root=Path(tmp))
            server = UiHttpServer(service, readiness=lambda: False).start_background()
            self.addCleanup(server.stop)
            def request(path, payload=None):
                req = urllib.request.Request(server.address + path,
                    data=json.dumps(payload).encode() if payload is not None else None,
                    headers={"Content-Type": "application/json"})
                try:
                    with urllib.request.urlopen(req) as response:
                        return response.status, response.read()
                except urllib.error.HTTPError as error:
                    return error.code, error.read()
            self.assertEqual(request("/")[0], 200)
            self.assertEqual(request("/health")[0], 200)
            self.assertEqual(request("/health/ready")[0], 503)
            self.assertEqual(request("/api/v1/wizard")[0], 200)
            for route in ("query", "retrieve", "graph", "wiki"):
                self.assertEqual(request("/api/v1/" + route, {"text": "evidence"})[0], 503)
            code, body = request("/api/v1/wizard", {"model": "qwen", "device": "cpu"})
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(body)["bootstrap_state"], "not-started")
            self.assertEqual(request("/health/ready")[0], 503)

class ServingLifecycleTests(unittest.TestCase):
    def test_start_serves_by_default_and_preserves_explicit_one_shot(self):
        from unittest.mock import patch
        from pi_platform.cli.main import main
        with tempfile.TemporaryDirectory() as tmp:
            with patch("pi_platform.cli.main._cmd_serve", return_value=0) as serve:
                self.assertEqual(main(["start", "--target", tmp]), 0)
                serve.assert_called_once()
            with patch("pi_platform.cli.main._bootstrap_and_index_target", return_value={"ready": True}) as bootstrap:
                with patch("pi_platform.cli.main._cmd_serve") as serve:
                    self.assertEqual(main(["start", "--target", tmp, "--no-serve"]), 0)
                    bootstrap.assert_called_once()
                    serve.assert_not_called()

    def test_failure_persists_false_readiness_and_keeps_last_snapshot(self):
        from unittest.mock import patch
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp)
            cache = target / ".project-intelligence-cache"
            cache.mkdir()
            last_snapshot = cache / "active-runtime.json"
            last_snapshot.write_text('{"last_successful": "A"}')
            readiness = DefaultKnowledgeReadiness()
            with patch("pi_platform.cli.main._bootstrap_and_index_target_locked", side_effect=RuntimeError("download unavailable")):
                with self.assertRaisesRegex(RuntimeError, "download unavailable"):
                    _bootstrap_and_index_target(target, readiness=readiness)
            self.assertFalse(readiness.is_ready())
            self.assertFalse(readiness.snapshot().in_progress)
            persisted = json.loads((cache / "readiness.json").read_text())
            self.assertFalse(persisted["consistent"])
            self.assertEqual(persisted["reason"], "download unavailable")
            self.assertEqual(json.loads(last_snapshot.read_text()), {"last_successful": "A"})
            settings = json.loads((cache / "retrieval-settings.json").read_text())
            self.assertEqual(settings["bootstrap_state"], "error")

    def test_server_listens_before_bootstrap_failure_and_keeps_control_plane_live(self):
        import os
        import sys
        with tempfile.TemporaryDirectory() as tmp:
            # Use a deliberately blocked model worker in a separate serving process.
            # The real HTTP adapter and polling lifecycle remain in use.
            script = '''
import argparse, json, sys, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from pi_platform.cli.main import _cmd_serve
from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
service = SimpleNamespace(_repo_root=Path(sys.argv[1]))
readiness = DefaultKnowledgeReadiness()
def slow_failure(*args, **kwargs):
    time.sleep(0.5)
    raise RuntimeError("model download unavailable")
with patch("pi_platform.adapters.ui.build_ui_service", return_value=(service,readiness)), patch("pi_platform.cli.main._build_embedded_mcp_and_a2a", return_value=(None,None,None,None)), patch("pi_platform.cli.main._bootstrap_and_index_target", side_effect=slow_failure):
    _cmd_serve(argparse.Namespace(target=Path(sys.argv[1]), host="127.0.0.1", port=0))
'''
            process = subprocess.Popen([sys.executable, "-u", "-c", script, tmp],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, env=os.environ.copy())
            try:
                first = json.loads(process.stdout.readline())
                self.assertEqual(first["status"], "listening")
                self.assertFalse(first["ready"])
                address = first["url"]
                with urllib.request.urlopen(address + "/") as response:
                    self.assertEqual(response.status, 200)
                with self.assertRaises(urllib.error.HTTPError) as failure:
                    urllib.request.urlopen(address + "/health/ready")
                self.assertEqual(failure.exception.code, 503)
                failed = json.loads(process.stdout.readline())
                self.assertEqual(failed["status"], "refresh-failed")
                with urllib.request.urlopen(address + "/api/v1/wizard") as response:
                    self.assertEqual(response.status, 200)
                self.assertIsNone(process.poll())
            finally:
                process.terminate()
                process.communicate(timeout=10)

class RepositoryRefreshIntegrationTests(unittest.TestCase):
    def test_actual_minimal_corpus_switch_removes_old_evidence_and_reuses_vectors(self):
        import os
        from unittest.mock import patch
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.ports.ui.rest_api import UiActor, RetrieveRequest
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, {
            "PI_STARTUP_PROFILE": "minimal", "PI_EMBEDDING_MODEL": "hashing",
            "PI_DENSE_INDEX": "flat", "PI_DOCLING_ENABLED": "0",
        }):
            root = Path(tmp)
            def git(*args):
                return subprocess.run(["git", "-C", tmp, *args], check=True,
                                      capture_output=True, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "test@example.com")
            git("config", "user.name", "Test")
            (root / "shared.md").write_text("# Shared\nCommon payment architecture.")
            (root / "branch-only.md").write_text("# Branch A\nOldBranchUnique refund policy.")
            git("add", ".")
            git("commit", "-qm", "A")
            branch_a = git("branch", "--show-current")
            service, readiness = build_ui_service(repo_root=root, defer_runtime=True)
            first = _bootstrap_and_index_target(root, service=service, readiness=readiness)
            self.assertTrue(first["ready"])
            self.assertGreater(first["new_vectors"], 0)
            old_ids = {cid for cid, hit in service._retrieval.runtime.extra["chunk_catalog"].items()
                       if "OldBranchUnique" in hit.snippet}
            self.assertTrue(old_ids)
            git("checkout", "-qb", "branch-b")
            git("rm", "branch-only.md")
            (root / "added.md").write_text("# Branch B\nNewBranchUnique authorization rules.")
            git("add", "added.md")
            git("commit", "-qm", "B")
            second = _bootstrap_and_index_target(root, service=service, readiness=readiness)
            self.assertTrue(readiness.is_ready())
            self.assertGreater(second["reused_vectors"], 0)
            self.assertEqual(second["removed_sources"], 1)
            catalog = service._retrieval.runtime.extra["chunk_catalog"]
            self.assertFalse(old_ids.intersection(catalog))
            self.assertTrue(any("NewBranchUnique" in hit.snippet for hit in catalog.values()))
            result = service.retrieve(UiActor(actor_type="human", actor_id="test", role="viewer"),
                                      RetrieveRequest(text="OldBranchUnique refund policy"))
            self.assertFalse(old_ids.intersection(hit.chunkId for hit in result.results))
            git("checkout", "-q", branch_a)
            third = _bootstrap_and_index_target(root, service=service, readiness=readiness)
            self.assertGreater(third["reused_vectors"], 0)
            self.assertTrue(old_ids.issubset(service._retrieval.runtime.extra["chunk_catalog"]))


class ControlPlaneJobTests(unittest.TestCase):
    def test_jobs_execute_and_record_failure(self):
        import threading
        from pi_platform.adapters.ui.retrieval_admin_routes import RetrievalAdminRoutes
        with tempfile.TemporaryDirectory() as tmp:
            routes = RetrievalAdminRoutes(target_repo=Path(tmp))
            done = threading.Event()
            called = []
            def execute(kind, details):
                called.append((kind, details))
                done.set()
                raise RuntimeError("download refused")
            routes.job_executor = execute
            job_id = routes.enqueue_job("models.pull", alias="gemma")
            self.assertTrue(done.wait(2))
            # The worker is nonblocking to callers; join only this test's job.
            for thread in threading.enumerate():
                if thread.name == f"pi-admin-{job_id}":
                    thread.join(2)
            self.assertEqual(called, [("models.pull", {"alias": "gemma"})])
            self.assertEqual(routes.job_view(job_id)["status"], "failed")
            self.assertEqual(routes.job_view(job_id)["message"], "download refused")

    def test_health_cannot_hydrate_its_way_around_failed_bootstrap(self):
        import os
        from unittest.mock import patch
        from pi_platform.cli.main import main
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "project-knowledge").mkdir()
            with patch.dict(os.environ, {"PI_AUTO_HYDRATE": "1"}), patch("pi_platform.adapters.ui.hydrate_and_reconcile_target") as hydrate:
                self.assertEqual(main(["health", "--ready", "--target", tmp]), 1)
                hydrate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
