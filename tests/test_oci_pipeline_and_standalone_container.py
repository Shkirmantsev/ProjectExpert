"""Tests for the GHCR OCI container pipeline and standalone container runtime.

Verifies:
1. ``.github/workflows/publish-oci-container.yml`` triggers on merges/pushes
   to ``dev`` and ``development`` (plus PRs and ``workflow_dispatch``),
   publishes to ``ghcr.io``, runs product-only verification gates without
   ``harness.py`` or ``infra/compose.yaml``, and performs a container smoke
   check.
2. ``.dockerignore`` and ``Containerfile`` package all product runtime
   artefacts (``pi_platform``, ``distribution``, ``evals``, generated vendor
   plugin bundles) while excluding the development harness.
3. ``docker-compose.yml`` defaults to ``ghcr.io/shkirmantsev/project-intelligence:core``
   via ``${PI_IMAGE:-...}`` so a user can start ``docker compose`` without
   building locally or having the development harness.
4. Standalone container startup (``build_ui_service(..., hydrate_on_start=True)``,
   ``serve``, ``mcp-serve``, ``package-plugins``, ``eval-retrieval``)
   auto-hydrates and reconciles a mounted target repository, persists
   readiness across processes, and serves the full UI, REST API, MCP
   JSON-RPC (``/mcp`` and stdio), and optional A2A surface.
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from pi_platform.adapters.ui import (
    UiHttpServer,
    build_ui_service,
)
from pi_platform.cli.main import (
    _build_embedded_mcp_and_a2a,
    main as cli_main,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "publish-oci-container.yml"
DOCKERIGNORE_PATH = ROOT / ".dockerignore"
CONTAINERFILE_PATH = ROOT / "Containerfile"
COMPOSE_PATH = ROOT / "docker-compose.yml"


def _init_git_repo(repo: Path) -> None:
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.email", "test@example.com"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "config", "user.name", "Test User"],
        check=True,
    )
    (repo / "README.md").write_text("# Target Repo\nOrderService cancelOrder contract.\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-q", "-m", "initial"],
        check=True,
    )


def _http_json(
    url: str, *, method: str = "GET", payload: dict | None = None
) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=5.0) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        return exc.code, json.loads(raw) if raw else {}


class OciWorkflowContractTests(unittest.TestCase):
    """Verify the GitHub Actions OCI container workflow contract."""

    def test_workflow_exists_and_triggers_on_dev_and_development(self) -> None:
        self.assertTrue(WORKFLOW_PATH.is_file(), f"Missing {WORKFLOW_PATH}")
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("name: publish-oci-container", text)
        self.assertIn("push:", text)
        self.assertIn("- dev", text)
        self.assertIn("- development", text)
        self.assertIn("pull_request:", text)
        self.assertIn("workflow_dispatch:", text)

    def test_workflow_configures_ghcr_and_packages_write_permission(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("REGISTRY: ghcr.io", text)
        self.assertIn("IMAGE_NAME: project-intelligence", text)
        self.assertIn("packages: write", text)
        self.assertIn("docker/login-action@v3", text)
        self.assertIn("docker/metadata-action@v5", text)
        self.assertIn("docker/build-push-action@v6", text)

    def test_workflow_does_not_couple_to_development_harness(self) -> None:
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        # The workflow must not run harness.py or infra/compose.yaml
        self.assertNotIn("python harness.py", text)
        self.assertNotIn("infra/compose.yaml", text)
        self.assertNotIn("tools/mcp/project-context-mcp", text)
        # It must run product CLI gates
        self.assertIn("python -m pi_platform.cli license-gate", text)
        self.assertIn("python -m pi_platform.cli eval", text)
        self.assertIn("python -m pi_platform.cli invariants", text)
        self.assertIn("python -m pi_platform.cli package-plugins", text)


class ContainerIsolationAndComposeTests(unittest.TestCase):
    """Verify Containerfile, .dockerignore, and docker-compose.yml separation from harness."""

    def test_dockerignore_excludes_harness_directories(self) -> None:
        self.assertTrue(DOCKERIGNORE_PATH.is_file(), "Missing .dockerignore")
        lines = {
            line.strip()
            for line in DOCKERIGNORE_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        }
        for forbidden in (
            "harness.py",
            "infra",
            "tools",
            ".ai",
            ".agents",
            ".claude",
            ".opencode",
            ".codex",
            "openspec",
            "scripts",
        ):
            self.assertIn(forbidden, lines, f"{forbidden!r} must be in .dockerignore")

    def test_containerfile_bundles_all_product_assets_and_plugins(self) -> None:
        text = CONTAINERFILE_PATH.read_text(encoding="utf-8")
        self.assertIn("COPY pi_platform ./pi_platform", text)
        self.assertIn("COPY distribution/okf-profile ./distribution/okf-profile", text)
        self.assertIn("COPY distribution/skills ./distribution/skills", text)
        self.assertIn("COPY evals ./evals", text)
        self.assertIn("package-plugins --output-root /opt/project-intelligence/distribution", text)
        for harness_item in ("COPY harness.py", "COPY infra", "COPY .ai", "COPY tools"):
            self.assertNotIn(harness_item, text)

    def test_compose_defaults_to_ghcr_oci_image(self) -> None:
        text = COMPOSE_PATH.read_text(encoding="utf-8")
        self.assertIn(
            "image: ${PI_IMAGE:-ghcr.io/shkirmantsev/project-intelligence:core}",
            text,
        )
        self.assertNotIn("infra/compose.yaml", text)


class StandaloneContainerCapabilitiesTests(unittest.TestCase):
    """Verify out-of-the-box readiness, retrieval, REST projections, MCP, and A2A."""

    def setUp(self) -> None:
        from unittest.mock import patch
        minimal = patch.dict(os.environ, {
            "PI_STARTUP_PROFILE": "minimal", "PI_EMBEDDING_MODEL": "hashing",
            "PI_DENSE_INDEX": "flat", "PI_DOCLING_ENABLED": "0",
        })
        minimal.start()
        self.addCleanup(minimal.stop)
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name) / "target-repo"
        self.repo.mkdir()
        _init_git_repo(self.repo)
        self.cache_root = self.repo / ".project-intelligence-cache"

    def test_auto_hydrate_marks_ready_and_persists_across_processes(self) -> None:
        # Scaffold canonical tree first
        rc = cli_main(["init-project", "--target", str(self.repo)])
        self.assertEqual(rc, 0)

        service, readiness = build_ui_service(
            repo_root=self.repo,
            cache_root=self.cache_root,
            hydrate_on_start=True,
        )
        self.assertTrue(readiness.is_ready())
        self.assertTrue((self.cache_root / "readiness.json").is_file())

        # Cross-process CLI health --ready check must now exit 0
        rc_ready = cli_main([
            "health",
            "--ready",
            "--target",
            str(self.repo),
            "--cache-root",
            str(self.cache_root),
        ])
        self.assertEqual(rc_ready, 0)

    def test_full_http_surface_ui_rest_mcp_and_a2a(self) -> None:
        cli_main(["init-project", "--target", str(self.repo)])
        service, readiness = build_ui_service(
            repo_root=self.repo,
            cache_root=self.cache_root,
            hydrate_on_start=True,
        )
        prev_a2a = os.environ.get("PI_A2A_INBOUND")
        os.environ["PI_A2A_INBOUND"] = "1"
        self.addCleanup(
            lambda: os.environ.pop("PI_A2A_INBOUND", None)
            if prev_a2a is None
            else os.environ.__setitem__("PI_A2A_INBOUND", prev_a2a)
        )
        mcp_server, skill_plane, a2a_adapter, agent_card = (
            _build_embedded_mcp_and_a2a(
                target=self.repo,
                cache_root=self.cache_root,
                service=service,
                readiness=readiness,
            )
        )
        server = UiHttpServer(
            service,
            host="127.0.0.1",
            port=0,
            readiness=lambda: readiness.is_ready(),
            mcp_server=mcp_server,
            skill_plane=skill_plane,
            a2a_adapter=a2a_adapter,
            agent_card=agent_card,
        ).start_background()
        self.addCleanup(server.stop)
        base = server.address

        # 1. Readiness endpoint is 200 OK out of the box
        status, ready_body = _http_json(f"{base}/health/ready")
        self.assertEqual(status, 200)
        self.assertTrue(ready_body["ready"])

        # 2. Indexing status reports sqlite backend and ready=True
        status, idx_body = _http_json(f"{base}/api/v1/indexing-status")
        self.assertEqual(status, 200)
        self.assertTrue(idx_body["ready"])
        self.assertEqual(idx_body["indexes"].get("backend"), "sqlite")

        # 3. Query endpoint retrieves from the target project's OKF Wiki stub
        status, query_body = _http_json(
            f"{base}/api/v1/query",
            method="POST",
            payload={"text": "Project Knowledge Index", "top_k": 5},
        )
        self.assertEqual(status, 200)
        self.assertTrue(len(query_body.get("results", [])) >= 1)

        # Stateless MCP exposes discovery through POST methods; GET streams unsupported.
        status, mcp_info = _http_json(f"{base}/mcp")
        self.assertEqual(status, 405)

        status, rpc_init = _http_json(
            f"{base}/mcp",
            method="POST",
            payload={"jsonrpc": "2.0", "id": 1, "method": "initialize"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            rpc_init["result"]["serverInfo"]["name"], "project-intelligence"
        )

        status, rpc_call = _http_json(
            f"{base}/mcp",
            method="POST",
            payload={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "project.search",
                    "arguments": {"text": "Project Knowledge Index", "top_k": 3},
                },
            },
        )
        self.assertEqual(status, 200)
        self.assertFalse(rpc_call["result"]["isError"])
        self.assertTrue(rpc_call["result"]["structuredContent"]["ok"])

        status, rpc_res = _http_json(
            f"{base}/mcp",
            method="POST",
            payload={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "resources/read",
                "params": {"uri": "project-intelligence://distribution/manifest"},
            },
        )
        self.assertEqual(status, 200)
        manifest_data = json.loads(rpc_res["result"]["contents"][0]["text"])
        self.assertEqual(manifest_data["platformVersion"], "0.8.0")

        # 5. A2A Agent Card and tasks:send
        status, card_body = _http_json(f"{base}/.well-known/agent-card.json")
        self.assertEqual(status, 200)
        self.assertEqual(card_body["name"], "project-intelligence")

        status, a2a_body = _http_json(
            f"{base}/a2a/v1/tasks:send",
            method="POST",
            payload={
                "wireVersion": "1",
                "taskId": "task-1",
                "messages": [
                    {
                        "role": "user",
                        "parts": [{"kind": "text", "text": "hello"}],
                    }
                ],
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(a2a_body["status"], "completed")

    def test_mcp_stdio_fallback_serves_jsonrpc_lines(self) -> None:
        cli_main(["init-project", "--target", str(self.repo)])
        service, readiness = build_ui_service(
            repo_root=self.repo,
            cache_root=self.cache_root,
            hydrate_on_start=True,
        )
        mcp_server, skill_plane, _, _ = _build_embedded_mcp_and_a2a(
            target=self.repo,
            cache_root=self.cache_root,
            service=service,
            readiness=readiness,
        )
        requests = [
            {"jsonrpc": "2.0", "id": 10, "method": "tools/list"},
            {
                "jsonrpc": "2.0",
                "id": 11,
                "method": "tools/call",
                "params": {"name": "project.describe_capabilities", "arguments": {}},
            },
        ]
        in_stream = io.StringIO(
            "\n".join(json.dumps(r) for r in requests) + "\n"
        )
        out_stream = io.StringIO()
        rc = mcp_server.serve_stdio_fallback(
            in_stream=in_stream,
            out_stream=out_stream,
            skill_plane=skill_plane,
        )
        self.assertEqual(rc, 0)
        responses = [
            json.loads(line)
            for line in out_stream.getvalue().splitlines()
            if line.strip()
        ]
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0]["id"], 10)
        self.assertTrue(len(responses[0]["result"]["tools"]) >= 18)
        self.assertEqual(responses[1]["id"], 11)
        self.assertFalse(responses[1]["result"]["isError"])

    def test_hydrate_failure_fails_closed_on_readiness(self) -> None:
        from unittest import mock
        from pi_platform.core.sync import HydrateService

        with mock.patch.object(
            HydrateService,
            "restore_runtime",
            side_effect=RuntimeError("corrupt shard manifest"),
        ):
            _service, readiness = build_ui_service(
                repo_root=self.repo,
                cache_root=self.cache_root,
                hydrate_on_start=True,
            )
        self.assertFalse(readiness.is_ready())
        self.assertIn("corrupt shard manifest", readiness.snapshot().reason)
        rc_ready = cli_main([
            "health",
            "--ready",
            "--target",
            str(self.repo),
            "--cache-root",
            str(self.cache_root),
        ])
        self.assertEqual(rc_ready, 1)

    def test_cli_package_plugins_generates_all_four_vendor_bundles(self) -> None:
        out_dir = Path(self._tmp.name) / "dist-out"
        rc = cli_main(["package-plugins", "--output-root", str(out_dir)])
        self.assertEqual(rc, 0)
        for vendor in ("codex", "claude-code", "opencode", "generic-agent"):
            self.assertTrue(
                (out_dir / vendor / "PROVENANCE.json").is_file(),
                f"missing bundle provenance for {vendor}",
            )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
