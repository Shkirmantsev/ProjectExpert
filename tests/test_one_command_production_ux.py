"""End-to-end tests for the One-Command Production UX, Makefile product surface,
Docker Compose production profile, unified settings resolution, and HTTP admin/wizard routes.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from pi_platform.adapters.config.runtime_configuration_resolver import (
    LOCAL_SETTINGS_RELATIVE_PATH,
    RuntimeConfigurationResolver,
)
from pi_platform.adapters.ui import UiHttpServer, build_ui_service
from pi_platform.cli.main import main as cli_main
from pi_platform.core.control.retrieval_settings import (
    load_retrieval_settings,
)
from pi_platform.core.sync.version_snapshot import RuntimeSnapshotService

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE_PATH = ROOT / "Makefile"
COMPOSE_PATH = ROOT / "docker-compose.yml"


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "dev@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Dev User"],
        check=True,
    )
    (repo / "README.md").write_text(
        "# Sample Project\nPaymentService processRefund contract.\n",
        encoding="utf-8",
    )
    src_dir = repo / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (src_dir / "service.py").write_text(
        "def process_refund(order_id: str) -> bool:\n    return True\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "initial commit"],
        check=True,
    )


def _http_request(
    url: str,
    *,
    method: str = "GET",
    payload: dict | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw) if raw else {}


class MakefileAndComposeProductSurfaceTests(unittest.TestCase):
    """Verify the centralized Makefile product targets and Docker Compose production profile."""

    def test_makefile_exposes_all_documented_pi_targets(self) -> None:
        text = MAKEFILE_PATH.read_text(encoding="utf-8")
        for target in (
            "pi-help:",
            "pi-up:",
            "pi-model:",
            "pi-status:",
            "pi-reindex:",
            "pi-doctor:",
            "pi-down:",
        ):
            self.assertIn(target, text, f"Missing Makefile target {target}")

    def test_make_pi_help_prints_centralized_commands(self) -> None:
        proc = subprocess.run(
            ["make", "pi-help"],
            encoding="utf-8",
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        for cmd in (
            "make pi-up",
            "make pi-model",
            "make pi-status",
            "make pi-reindex",
            "make pi-doctor",
            "make pi-down",
        ):
            self.assertIn(cmd, proc.stdout)

    def test_docker_compose_production_profile_and_persistent_model_volume(self) -> None:
        text = COMPOSE_PATH.read_text(encoding="utf-8")
        self.assertIn('"production"', text)
        self.assertIn("${PI_BIND_HOST:-127.0.0.1}:${PI_CONTROL_PORT:-8765}:8765", text)
        self.assertIn("pi-model-cache:/models/huggingface:rw", text)
        self.assertIn("PI_EMBEDDING_MODEL: ${PI_EMBEDDING_MODEL:-gemma-torch}", text)
        self.assertIn("PI_EMBEDDING_DEVICE: ${PI_EMBEDDING_DEVICE:-auto}", text)
        self.assertIn("PI_DENSE_INDEX: ${PI_DENSE_INDEX:-usearch}", text)
        self.assertIn("HF_HOME: ${PI_MODEL_CACHE:-/models/huggingface}", text)


class OneCommandStartAndModelSwitchTests(unittest.TestCase):
    """Verify trivial target bootstrap, model switching without Git churn, and branch reconciliation."""

    def setUp(self) -> None:
        # These UX tests prove orchestration and profile isolation, not model
        # quality. Heavy integration tests exercise actual production weights.
        from unittest.mock import patch
        from dataclasses import replace
        from pi_platform.core.retrieval.embedding_model import HashingEmbeddingModel
        from pi_platform.ports.retrieval.embedding_profile import HASHING_DEFAULT
        environment = patch.dict(os.environ, {
            "PI_STARTUP_PROFILE": "minimal", "PI_DENSE_INDEX": "flat", "PI_DOCLING_ENABLED": "0",
        })
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("PI_EMBEDDING_MODEL", None)
        class ContractEmbedding(HashingEmbeddingModel):
            def __init__(self, alias):
                super().__init__()
                self.alias = alias
            def profile(self):
                return replace(HASHING_DEFAULT, model_revision="ux-contract-" + self.alias)
        factory = patch("pi_platform.adapters.retrieval.embedding_model_factory.EmbeddingModelFactory.build",
                        side_effect=lambda alias, **kwargs: ContractEmbedding(alias))
        factory.start()
        self.addCleanup(factory.stop)
        self.tmp = Path(tempfile.mkdtemp(prefix="one-cmd-ux-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "target-repo"
        self.repo.mkdir()
        _init_git_repo(self.repo)

    def test_start_bootstraps_target_discovers_sources_and_commits_snapshot(self) -> None:
        rc = cli_main([
            "start",
            "--no-serve",
            "--target",
            str(self.repo),
            "--model",
            "gemma-torch",
            "--device",
            "cpu",
        ])
        self.assertEqual(rc, 0)

        # Settings are persisted and unified across both RetrievalSettings and RuntimeConfigurationResolver
        settings = load_retrieval_settings(self.repo)
        self.assertEqual(settings.embedding_model_alias, "gemma-torch")
        self.assertEqual(settings.device, "cpu")
        self.assertEqual(settings.bootstrap_state, "ready")

        resolved = RuntimeConfigurationResolver(
            local_settings_path=self.repo / LOCAL_SETTINGS_RELATIVE_PATH
        ).resolve()
        self.assertEqual(resolved.embedding_model, "gemma-torch")
        self.assertEqual(resolved.embedding_device, "cpu")

        # Source inventory and runtime snapshot are persisted
        cache_root = self.repo / ".project-intelligence-cache"
        self.assertTrue((cache_root / "source-inventory.json").is_file())
        snap = RuntimeSnapshotService(cache_root=cache_root).read_snapshot()
        self.assertIsNotNone(snap)
        assert snap is not None
        self.assertIn("README.md", snap.source.source_ids)
        self.assertIn("src/service.py", snap.source.source_ids)

    def test_restart_environment_selection_is_saved_as_active_model(self) -> None:
        from unittest.mock import patch
        self.assertEqual(cli_main(['start','--no-serve','--target',str(self.repo),'--model','gemma-torch']),0)
        for alias, device in [('gemma','vulkan'), ('gemma-torch','cpu')]:
            with patch.dict(os.environ, {'PI_EMBEDDING_MODEL':alias, 'PI_EMBEDDING_DEVICE':device}):
                self.assertEqual(cli_main(['start','--no-serve','--target',str(self.repo)]),0)
                settings=load_retrieval_settings(self.repo)
                self.assertEqual(settings.embedding_model_alias,alias)
                self.assertEqual(settings.device,device)
                self.assertEqual(settings.bootstrap_state,'ready')
                from pi_platform.core.sync.version_monitor import read_project_version
                snapshot=RuntimeSnapshotService(cache_root=self.repo/'.project-intelligence-cache').read_snapshot()
                self.assertEqual(snapshot.active.working_tree_fingerprint, read_project_version(self.repo).working_tree_fingerprint)

    def test_model_switch_updates_namespace_without_git_churn(self) -> None:
        self.assertEqual(
            cli_main(["start", "--no-serve", "--target", str(self.repo), "--model", "gemma"]),
            0,
        )
        cache_root = self.repo / ".project-intelligence-cache"
        snap_gemma = RuntimeSnapshotService(cache_root=cache_root).read_snapshot()
        assert snap_gemma is not None

        # Switch to the native binding via CLI models use + reindex
        self.assertEqual(
            cli_main(["models", "use", "gemma-torch", "--target", str(self.repo)]),
            0,
        )
        self.assertEqual(
            cli_main(["reindex", "--target", str(self.repo)]),
            0,
        )
        snap_torch = RuntimeSnapshotService(cache_root=cache_root).read_snapshot()
        assert snap_torch is not None
        self.assertNotEqual(
            snap_gemma.active.embedding_profile_identity,
            snap_torch.active.embedding_profile_identity,
        )
        self.assertNotEqual(
            snap_gemma.active.active_index_generation,
            snap_torch.active.active_index_generation,
        )

        # Canonical Git working tree has zero untracked/modified files
        # (other than .project-intelligence-cache which is runtime cache)
        git_status = subprocess.run(
            [
                "git",
                "-C",
                str(self.repo),
                "status",
                "--porcelain",
                "--untracked-files=no",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(git_status.stdout.strip(), "")

    def test_branch_switch_reconciles_added_and_removed_sources(self) -> None:
        self.assertEqual(
            cli_main(["start", "--no-serve", "--target", str(self.repo), "--model", "gemma"]),
            0,
        )
        cache_root = self.repo / ".project-intelligence-cache"

        # Create a feature branch with a new file
        subprocess.run(
            ["git", "-C", str(self.repo), "checkout", "-q", "-b", "feature/new-api"],
            check=True,
        )
        (self.repo / "src" / "new_api.py").write_text(
            "def new_endpoint():\n    return 'ok'\n", encoding="utf-8"
        )
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.repo), "commit", "-q", "-m", "add new_api"],
            check=True,
        )

        self.assertEqual(cli_main(["reindex", "--target", str(self.repo)]), 0)
        snap_feature = RuntimeSnapshotService(cache_root=cache_root).read_snapshot()
        assert snap_feature is not None
        self.assertIn("src/new_api.py", snap_feature.source.source_ids)

        # Switch back to initial branch (master/main) and reindex
        branches = subprocess.run(
            ["git", "-C", str(self.repo), "branch", "--format=%(refname:short)"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.splitlines()
        base_branch = [b for b in branches if b != "feature/new-api"][0]
        subprocess.run(
            ["git", "-C", str(self.repo), "checkout", "-q", base_branch],
            check=True,
        )
        self.assertEqual(cli_main(["reindex", "--target", str(self.repo)]), 0)
        snap_base = RuntimeSnapshotService(cache_root=cache_root).read_snapshot()
        assert snap_base is not None
        self.assertNotIn("src/new_api.py", snap_base.source.source_ids)


class HttpServerAdminAndWizardIntegrationTests(unittest.TestCase):
    """Verify that UiHttpServer serves /api/v1/wizard and /api/v1/admin/* over HTTP."""

    def setUp(self) -> None:
        from unittest.mock import patch
        environment = patch.dict(os.environ, {
            "PI_STARTUP_PROFILE": "minimal", "PI_EMBEDDING_MODEL": "hashing",
            "PI_DENSE_INDEX": "flat", "PI_DOCLING_ENABLED": "0",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.tmp = Path(tempfile.mkdtemp(prefix="ui-http-admin-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "target-repo"
        self.repo.mkdir()
        _init_git_repo(self.repo)
        service, readiness = build_ui_service(
            repo_root=self.repo,
            cache_root=self.repo / ".project-intelligence-cache",
            hydrate_on_start=True,
        )
        self.server = UiHttpServer(
            service,
            host="127.0.0.1",
            port=0,
            readiness=lambda: readiness.is_ready(),
        ).start_background()
        self.addCleanup(self.server.stop)
        self.base = self.server.address

    def test_wizard_get_and_post_over_http(self) -> None:
        status, wizard_schema = _http_request(f"{self.base}/api/v1/wizard")
        self.assertEqual(status, 200)
        self.assertTrue(wizard_schema["visible"])
        self.assertEqual(len(wizard_schema["model_choices"]), 2)

        status, submitted = _http_request(
            f"{self.base}/api/v1/wizard",
            method="POST",
            payload={
                "model": "gemma-torch",
                "device": "cpu",
                "document_processing_enabled": True,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(submitted["embedding_model_alias"], "gemma-torch")
        self.assertEqual(submitted["bootstrap_state"], "not-started")

        # Setup submission schedules bootstrap; it cannot claim runtime readiness.
        status, wizard_after = _http_request(f"{self.base}/api/v1/wizard")
        self.assertEqual(status, 200)
        self.assertTrue(wizard_after["visible"])

    def test_admin_retrieval_get_put_and_coding_agent_rejection_over_http(self) -> None:
        # Administrator PUT succeeds
        status, body = _http_request(
            f"{self.base}/api/v1/admin/retrieval",
            method="PUT",
            payload={"embedding_model_alias": "gemma-torch", "device": "cpu"},
            headers={"X-Actor-Capability": "administrator"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["embedding_model_alias"], "gemma-torch")

        # Coding agent PUT is rejected with 403 and structured error
        status, err = _http_request(
            f"{self.base}/api/v1/admin/retrieval",
            method="PUT",
            payload={"embedding_model_alias": "gemma"},
            headers={"X-Actor-Capability": "coding-agent"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(err["code"], "admin-capability-required")

        # Queue reindex and inspect job status over HTTP
        status, job = _http_request(
            f"{self.base}/api/v1/admin/reindex",
            method="POST",
            payload={},
        )
        self.assertEqual(status, 202)
        job_id = job["job_id"]

        status, job_view = _http_request(
            f"{self.base}/api/v1/admin/jobs/{job_id}",
            method="GET",
        )
        self.assertEqual(status, 200)
        self.assertEqual(job_view["job_id"], job_id)


if __name__ == "__main__":
    unittest.main()
