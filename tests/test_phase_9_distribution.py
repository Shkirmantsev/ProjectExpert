"""Phase 9 distribution regression tests.

Covers ``openspec/changes/implement-phase-9-distribution/specs/``:
the HTTP adapter boundary, the no-Node static frontend, the feature-flagged
Open WebUI profile and the OKF conformance gate.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pi_platform.adapters.ui import (  # noqa: E402
    OPEN_WEBUI_FLAG,
    OpenAiCompatShim,
    STATIC_ROOT,
    UiHttpServer,
    build_flag_registry,
    build_ui_service,
    is_open_webui_enabled,
)
from pi_platform.core.canonical import (  # noqa: E402
    RuntimeChange,
    Source,
    content_address_bytes,
    validate_wiki_bundle,
)
from pi_platform.core.licensing import (  # noqa: E402
    LicenseGate,
    LicensePolicy,
)
from pi_platform.core.sync import (  # noqa: E402
    MaterialiseService,
    PolicyDecisionStub,
    WriteAheadLog,
)
from pi_platform.core.sync.trusted_approval import (  # noqa: E402
    HmacTrustedApprovalBoundary,
)
from pi_platform.adapters.fs import LocalFilesystemAdapter  # noqa: E402
from pi_platform.ports.control.policy import Capability, Decision  # noqa: E402
from pi_platform.ports.ui.rest_api import QueryRequest  # noqa: E402


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-c", "user.email=t@example",
            "-c", "user.name=Phase9",
            "-c", "commit.gpgsign=false",
            *args,
        ],
        cwd=repo, check=True, capture_output=True,
    )


class TempRepoMixin:
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        # Retain a noncanonical spelling to exercise approval path handling
        # on every OS, even when its temporary-directory path is canonical.
        self.repo = root / ".." / root.name / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q")
        (self.repo / "project-knowledge" / "wiki").mkdir(parents=True)
        _git(self.repo, "commit", "-q", "--allow-empty", "-m", "init")

    def tearDown(self) -> None:
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# HTTP adapter
# ---------------------------------------------------------------------------
class HttpAdapterTests(TempRepoMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.service, self.readiness = build_ui_service(repo_root=self.repo)
        self.server = UiHttpServer(
            self.service, readiness=lambda: self.readiness.is_ready()
        ).start_background()
        self.addCleanup(self.server.stop)

    def _request(self, path: str, data=None, token=None, method=None):
        body = json.dumps(data).encode() if data is not None else None
        request = urllib.request.Request(
            self.server.address + path, data=body, method=method,
        )
        if token:
            request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read().decode()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode()

    def test_binds_loopback_by_default(self) -> None:
        self.assertEqual(self.server.host, "127.0.0.1")
        self.assertTrue(self.server.address.startswith("http://127.0.0.1:"))

    def test_liveness_and_readiness_are_distinct(self) -> None:
        status, body = self._request("/health")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertFalse(payload["ready"])

        status, _ = self._request("/health/ready")
        self.assertEqual(status, 503)

    def test_readiness_reports_ready_after_hydration(self) -> None:
        class Ready:
            def is_ready(self) -> bool:
                return True

        server = UiHttpServer(
            self.service, readiness=lambda: Ready().is_ready()
        ).start_background()
        self.addCleanup(server.stop)
        with urllib.request.urlopen(server.address + "/health/ready", timeout=10) as r:
            self.assertEqual(r.status, 200)

    def test_missing_token_is_rejected_before_operations(self) -> None:
        self.server.token = "s3cret"
        status, body = self._request("/api/v1/project-version")
        self.assertEqual(status, 401)
        self.assertEqual(json.loads(body)["error"], "unauthorized")

    def test_wrong_token_is_rejected(self) -> None:
        self.server.token = "s3cret"
        status, _ = self._request("/api/v1/project-version", token="wrong")
        self.assertEqual(status, 401)

    def test_valid_token_is_accepted(self) -> None:
        self.server.token = "s3cret"
        status, _ = self._request("/api/v1/project-version", token="s3cret")
        self.assertEqual(status, 200)

    def test_read_operations_answer_json(self) -> None:
        for path in ("/api/v1/sources", "/api/v1/indexing-status",
                     "/api/v1/knowledge-status", "/api/v1/project-version"):
            with self.subTest(path=path):
                status, body = self._request(path)
                self.assertEqual(status, 200)
                json.loads(body)

    def test_unknown_route_returns_404(self) -> None:
        status, _ = self._request("/api/v1/does-not-exist")
        self.assertEqual(status, 404)

    def test_materialize_without_token_is_forbidden(self) -> None:
        status, body = self._request("/api/v1/materialize", data={})
        self.assertEqual(status, 403)
        payload = json.loads(body)
        self.assertEqual(payload["operation"], "materialize")

    def test_agent_delegation_is_refused_for_an_unauthorised_role(self) -> None:
        status, body = self._request(
            "/api/v1/agent-delegation", data={"task": "implement REQ-1"}
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(body)["operation"], "agent-delegation")

    def test_agent_delegation_is_egress_gated_when_authorised(self) -> None:
        from pi_platform.ports.ui.rest_api import UiActor

        self.server.actor = UiActor("human", "admin", "administrator")
        status, body = self._request(
            "/api/v1/agent-delegation", data={"task": "implement REQ-1"}
        )
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "denied")
        self.assertTrue(payload["reason"])

    def test_query_is_served_without_a_coding_harness(self) -> None:
        from unittest.mock import patch
        from pi_platform.cli.main import _bootstrap_and_index_target
        status, _ = self._request("/api/v1/query", data={"text": "before bootstrap"})
        self.assertEqual(status, 503)
        with patch.dict(os.environ, {
            "PI_STARTUP_PROFILE": "minimal", "PI_EMBEDDING_MODEL": "hashing",
            "PI_DENSE_INDEX": "flat", "PI_DOCLING_ENABLED": "0",
        }):
            _bootstrap_and_index_target(self.repo, service=self.service, readiness=self.readiness)
        status, body = self._request("/api/v1/query", data={"text": "what is this"})
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertIn("mode", payload)
        self.assertIn("results", payload)

    def test_adapter_uses_standard_library_only(self) -> None:
        source = (ROOT / "pi_platform/adapters/ui/http_server.py").read_text("utf-8")
        for banned in ("fastapi", "flask", "django", "aiohttp", "uvicorn"):
            self.assertNotIn(banned, source)


# ---------------------------------------------------------------------------
# Static frontend
# ---------------------------------------------------------------------------
class StaticFrontendTests(unittest.TestCase):
    def test_required_assets_exist(self) -> None:
        for name in ("index.html", "app.js", "styles.css"):
            self.assertTrue((STATIC_ROOT / name).is_file(), name)

    def test_frontend_calls_only_documented_operations(self) -> None:
        source = (STATIC_ROOT / "app.js").read_text("utf-8")
        expected = {
            "/query", "/retrieve", "/sources", "/graph", "/wiki",
            "/project-version", "/indexing-status", "/knowledge-status",
            "/materialize", "/agent-delegation",
        }
        for operation in expected:
            self.assertIn(operation, source, operation)

    def test_frontend_requires_no_node_runtime(self) -> None:
        source = (STATIC_ROOT / "app.js").read_text("utf-8")
        self.assertNotIn("require(", source)
        self.assertNotIn("process.env", source)
        self.assertNotIn("node_modules", source)

    def test_materialize_view_supplies_approval_token(self) -> None:
        html = (STATIC_ROOT / "index.html").read_text("utf-8")
        self.assertIn("approval-token", html)
        self.assertIn("approval_token", (STATIC_ROOT / "app.js").read_text("utf-8"))

    def test_static_index_is_served_at_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _git(repo, "init", "-q")
            _git(repo, "commit", "-q", "--allow-empty", "-m", "i")
            service, readiness = build_ui_service(repo_root=repo)
            server = UiHttpServer(service, readiness=lambda: readiness.is_ready())
            server.start_background()
            self.addCleanup(server.stop)
            with urllib.request.urlopen(server.address + "/", timeout=10) as r:
                self.assertEqual(r.status, 200)
                self.assertIn("text/html", r.headers.get("Content-Type", ""))
                self.assertIn("Project Intelligence", r.read().decode())

    def test_missing_static_asset_returns_404(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            _git(repo, "init", "-q")
            _git(repo, "commit", "-q", "--allow-empty", "-m", "i")
            service, readiness = build_ui_service(repo_root=repo)
            server = UiHttpServer(service, readiness=lambda: readiness.is_ready())
            server.start_background()
            self.addCleanup(server.stop)
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(server.address + "/missing.js", timeout=10)
            self.assertEqual(ctx.exception.code, 404)


# ---------------------------------------------------------------------------
# Open WebUI profile
# ---------------------------------------------------------------------------
class OpenWebUiProfileTests(unittest.TestCase):
    def test_flag_is_registered_and_enabled_by_default(self) -> None:
        # Local model is the default (§58 "download → start → open browser").
        # The OpenAI-compatible shim is therefore enabled by default so the
        # bundled local-llm sidecar is wired up out of the box.
        registry = build_flag_registry()
        self.assertIn(OPEN_WEBUI_FLAG, {f for f, _, _ in registry.list()})
        self.assertTrue(is_open_webui_enabled(registry))

    def test_shim_is_absent_while_the_flag_is_off(self) -> None:
        shim = OpenAiCompatShim(lambda prompt: None, flag=lambda: False)
        self.assertEqual(shim.handle("/v1/models")[0], 404)
        self.assertEqual(shim.handle("/v1/chat/completions", {"messages": []})[0], 404)

    def test_shim_is_absent_when_base_url_is_empty(self) -> None:
        # ``PI_OPENAI_SHIM=0`` disables the chat path even when the flag is on.
        shim = OpenAiCompatShim(
            lambda prompt: None, flag=lambda: True, base_url="",
        )
        self.assertFalse(shim.enabled)
        self.assertEqual(shim.handle("/v1/models")[0], 404)

    def test_models_endpoint_advertises_configured_base_url(self) -> None:
        shim = OpenAiCompatShim(
            lambda p: None, flag=lambda: True,
            base_url="http://local-llm:8767/v1", model="custom-model",
        )
        status, body = shim.handle("/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual(body["data"][0]["id"], "custom-model")
        self.assertEqual(body["pi_base_url"], "http://local-llm:8767/v1")

    def test_chat_completion_maps_to_the_query_operation(self) -> None:
        class Result:
            answer = "answer from retrieval"
            results = ()

        seen = []

        def query(prompt: str):
            seen.append(prompt)
            return Result()

        shim = OpenAiCompatShim(
            query, flag=lambda: True, base_url="http://localhost:9999/v1",
        )
        status, body = shim.handle(
            "/v1/chat/completions",
            {"messages": [{"role": "user", "content": "where is OrderStatus"}]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["model"], "project-intelligence")
        self.assertEqual(body["choices"][0]["message"]["content"], "answer from retrieval")
        self.assertEqual(seen, ["where is OrderStatus"])

    def test_models_endpoint_is_minimal(self) -> None:
        shim = OpenAiCompatShim(
            lambda p: None, flag=lambda: True, base_url="http://x/v1",
        )
        status, body = shim.handle("/v1/models")
        self.assertEqual(status, 200)
        self.assertEqual(body["object"], "list")
        self.assertEqual(len(body["data"]), 1)

    def test_streaming_is_accepted_for_http_framing(self) -> None:
        shim = OpenAiCompatShim(lambda p: None, flag=lambda: True)
        status, _ = shim.handle(
            "/v1/chat/completions",
            {"stream": True, "messages": [{"role": "user", "content": "x"}]},
        )
        self.assertEqual(status, 200)

    def test_no_admin_or_upload_surface_exists(self) -> None:
        shim = OpenAiCompatShim(lambda p: None, flag=lambda: True)
        for path in ("/v1/files", "/v1/admin", "/v1/embeddings"):
            self.assertEqual(shim.handle(path, {})[0], 404)


# ---------------------------------------------------------------------------
# OKF conformance gate
# ---------------------------------------------------------------------------
VALID_CONCEPT = """---
type: Component
title: Packing Service
description: Handles the packing-machine integration.
resource: "project://component/packing-service"
pi_status: verified
pi_project_version: "0.1.0"
---

# Packing Service

Body text.
"""

VALID_INDEX = """---
type: WikiIndex
okf_version: "0.2"
---

# Project Knowledge
"""

LOG_PAGE = """---
type: Log
title: Log
---

# Log
"""


class OkfProfileTests(unittest.TestCase):
    def _bundle(self, files: dict) -> Path:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name, content in files.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        return root

    def test_valid_bundle_validates(self) -> None:
        root = self._bundle({
            "index.md": VALID_INDEX,
            "log.md": LOG_PAGE,
            "components/packing-service.md": VALID_CONCEPT,
        })
        self.assertEqual(validate_wiki_bundle(root), [])

    def test_reserved_files_need_no_concept_type(self) -> None:
        root = self._bundle({"index.md": VALID_INDEX, "log.md": LOG_PAGE})
        self.assertEqual(validate_wiki_bundle(root), [])

    def test_missing_concept_type_fails(self) -> None:
        root = self._bundle({
            "index.md": VALID_INDEX,
            "components/x.md": "---\ntitle: X\n---\n\n# X\n",
        })
        self.assertTrue(validate_wiki_bundle(root))

    def test_unsupported_declared_version_fails(self) -> None:
        root = self._bundle(
            {"index.md": '---\ntype: WikiIndex\nokf_version: "9.9"\n---\n\n# X\n'}
        )
        self.assertTrue(validate_wiki_bundle(root))

    def test_binary_runtime_artefact_is_rejected(self) -> None:
        root = self._bundle({"index.md": VALID_INDEX})
        (root / "vectors.idx").write_bytes(b"\x00\x01\x02binary")
        self.assertTrue(validate_wiki_bundle(root))

    def test_harness_wiki_is_out_of_scope_for_okf(self) -> None:
        self.assertTrue(str(ROOT / ".ai" / "wiki").startswith(str(ROOT)))
        harness_page = ROOT / ".ai" / "wiki" / "INDEX.md"
        if harness_page.is_file():
            self.assertNotIn("type:", harness_page.read_text("utf-8").split("---")[1])


class MaterialiseOkfGateTests(TempRepoMixin, unittest.TestCase):
    """§10: OKF validation runs before any durable commit."""

    def _service(self) -> MaterialiseService:
        cache_root = self.repo / ".project-intelligence-cache"
        cache_root.mkdir(exist_ok=True)
        return MaterialiseService(
            filesystem=LocalFilesystemAdapter(self.repo, cache_root=cache_root),
            wal=WriteAheadLog(cache_root),
            policy=PolicyDecisionStub(),
            license_gate=LicenseGate(LicensePolicy()),
            boundary=HmacTrustedApprovalBoundary(key=b"phase9-test-key"),
        )

    def _token(self) -> str:
        from pi_platform.ports import ApprovalRequest

        return HmacTrustedApprovalBoundary(key=b"phase9-test-key").issue(
            ApprovalRequest(action="materialise", repo_root=str(self.repo.resolve()))
        )

    def _change(self) -> RuntimeChange:
        return RuntimeChange(
            id="rc-okf",
            kind="chunk",
            payload={"id": "rc-okf", "text": "hello"},
            source=Source(
                id="src-1", uri="file:///tmp/x.md", family="markdown",
                contentHash=content_address_bytes(b"hello"),
            ),
        )

    def _knowledge_snapshot(self) -> set:
        root = self.repo / "project-knowledge"
        return {str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()}

    def test_invalid_bundle_aborts_commit_and_writes_nothing(self) -> None:
        bad = self.repo / "project-knowledge" / "wiki" / "components"
        bad.mkdir(parents=True, exist_ok=True)
        (bad / "broken.md").write_text("---\ntitle: No type\n---\n\n# x\n", "utf-8")
        before = self._knowledge_snapshot()

        report = self._service().materialise_durable_changes(
            self.repo, cache_root=self.repo / ".project-intelligence-cache",
            changes=(self._change(),), approval_token=self._token(),
        )
        self.assertEqual(report.diff_files, ())
        self.assertTrue(report.okf_validation_errors)
        self.assertEqual(self._knowledge_snapshot(), before)

    def test_valid_bundle_materialises(self) -> None:
        wiki = self.repo / "project-knowledge" / "wiki"
        (wiki / "index.md").write_text(VALID_INDEX, "utf-8")
        (wiki / "log.md").write_text(LOG_PAGE, "utf-8")
        components = wiki / "components"
        components.mkdir(parents=True, exist_ok=True)
        (components / "packing-service.md").write_text(VALID_CONCEPT, "utf-8")

        report = self._service().materialise_durable_changes(
            self.repo, cache_root=self.repo / ".project-intelligence-cache",
            changes=(self._change(),), approval_token=self._token(),
        )
        self.assertEqual(report.okf_validation_errors, ())
        self.assertTrue(report.diff_files)

    def test_absent_wiki_tree_is_not_an_error(self) -> None:
        import shutil

        shutil.rmtree(self.repo / "project-knowledge" / "wiki")
        report = self._service().materialise_durable_changes(
            self.repo, cache_root=self.repo / ".project-intelligence-cache",
            changes=(self._change(),), approval_token=self._token(),
        )
        self.assertEqual(report.okf_validation_errors, ())
        self.assertTrue(report.diff_files)


class LicenseInventoryTests(unittest.TestCase):
    def test_open_webui_image_is_inventoried_before_bundling(self) -> None:
        inventory = json.loads(
            (ROOT / "distribution/licenses/dependency-inventory.json").read_text("utf-8")
        )
        names = {entry["name"] for entry in inventory["dependencies"]}
        self.assertIn("open-webui", names)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
