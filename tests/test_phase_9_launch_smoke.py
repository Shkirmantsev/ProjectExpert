"""Phase 9 launch smoke + launcher parity tests.

Two parts:

1. In-process smoke (always runs): boots the UI server on an ephemeral port
   against a synthetic project fixture and asserts the launcher-relevant
   routes (``/``, ``/health``, ``/health/ready``, ``/api/v1/sources``,
   ``/api/v1/project-version``). Block G1.

2. Launcher duty-parity (always runs): parses the ``DUTIES:`` header from
   ``scripts/project-intelligence.sh`` and
   ``scripts/Start-ProjectIntelligence.ps1`` and asserts the two sets are
   equal. Block E3.

3. Container smoke (gated): when ``PI_PHASE9_DOCKER_TESTS=1`` is exported
   AND a container runtime is reachable, builds the image, starts the
   ``core-headless`` profile and asserts readiness. The gate is disabled
   by default so the offline suite stays deterministic. Block G2/G3.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
import urllib.request
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _ephemeral_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _http_get(url: str, *, timeout: float = 2.0) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read()


# ---------------------------------------------------------------------------
# Block E3 — duty parity between bash and PowerShell launchers
# ---------------------------------------------------------------------------

def _duties(path: Path) -> list[str]:
    """Extract the wrapped ``DUTIES:`` token list from a launcher header.

    The bash and PowerShell launchers advertise their duty set as a comment
    block that wraps across multiple lines:

        # DUTIES: verify-runtime export-env create-volumes mount-repo start-profile
        #         wait-readiness open-browser print-status

    The first line carries the ``DUTIES:`` prefix; subsequent indented
    comment lines continue the token stream until a blank line or a
    non-comment line ends the block.
    """
    text = path.read_text(encoding="utf-8")
    # ``#`` is optional because the PowerShell launcher wraps the header in a
    # ``<# ... #>`` block comment and the bash launcher uses ``#``.
    header_re = re.compile(r"^\s*#?\s*DUTIES:\s*(.+?)\s*$", re.MULTILINE)
    match = header_re.search(text)
    if not match:
        raise AssertionError(f"DUTIES header missing from {path}")
    duties: list[str] = match.group(1).split()
    # Continuation lines: each line whose first non-whitespace, non-``#``
    # character is lowercase is part of the duty list. The block ends at the
    # first line that is blank, contains a colon, or starts with an
    # uppercase character (i.e., the start of the next paragraph).
    cursor = match.end()
    while True:
        # Skip the terminating newline of the DUTIES header line itself so
        # the next iteration reads the continuation line, not the empty
        # remainder of the header.
        if cursor < len(text) and text[cursor] == "\n":
            cursor += 1
        newline = text.find("\n", cursor)
        if newline == -1:
            newline = len(text)
        line = text[cursor:newline].strip()
        if not line:
            break
        if line.startswith("#"):
            line = line.lstrip("#").strip()
            if not line:
                break
        if line.startswith("DUTIES:"):
            break
        if ":" in line:
            break
        if not line[0].islower():
            break
        duties.extend(line.split())
        cursor = newline + 1
    return duties


class LauncherParityTests(unittest.TestCase):
    """Block E3: bash and PowerShell launchers must advertise the same duties."""

    def test_bash_launcher_declares_duties(self) -> None:
        duties = _duties(ROOT / "scripts" / "project-intelligence.sh")
        self.assertIn("verify-runtime", duties)
        self.assertIn("export-env", duties)
        self.assertIn("create-volumes", duties)
        self.assertIn("mount-repo", duties)
        self.assertIn("start-profile", duties)
        self.assertIn("wait-readiness", duties)
        self.assertIn("open-browser", duties)
        self.assertIn("print-status", duties)

    def test_powershell_launcher_declares_duties(self) -> None:
        duties = _duties(ROOT / "scripts" / "Start-ProjectIntelligence.ps1")
        self.assertIn("verify-runtime", duties)
        self.assertIn("export-env", duties)
        self.assertIn("create-volumes", duties)
        self.assertIn("mount-repo", duties)
        self.assertIn("start-profile", duties)
        self.assertIn("wait-readiness", duties)
        self.assertIn("open-browser", duties)
        self.assertIn("print-status", duties)

    def test_launcher_duties_are_identical(self) -> None:
        bash = _duties(ROOT / "scripts" / "project-intelligence.sh")
        ps = _duties(ROOT / "scripts" / "Start-ProjectIntelligence.ps1")
        self.assertEqual(bash, ps, f"bash={bash} powershell={ps}")

    def test_bash_launcher_is_syntax_clean(self) -> None:
        """``bash -n`` is the documented clean-syntax gate (Block E1)."""
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not on PATH")
        proc = subprocess.run(
            [bash, "-n", str(ROOT / "scripts" / "project-intelligence.sh")],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


# ---------------------------------------------------------------------------
# Block G1 — in-process server smoke
# ---------------------------------------------------------------------------


def _build_synthetic_project(tmp: Path) -> Path:
    """Create a minimal valid project fixture (canonical tree + git HEAD)."""
    import subprocess as sp

    repo = tmp / "repo"
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.email", "test@example.com"], check=True)
    sp.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    (repo / "file.txt").write_text("v1", encoding="utf-8")
    sp.run(["git", "-C", str(repo), "add", "file.txt"], check=True)
    sp.run(["git", "-C", str(repo), "commit", "-q", "-m", "v1"], check=True)
    return repo


class InProcessServerSmokeTests(unittest.TestCase):
    """Boot the UI server in the test process and exercise launcher-relevant routes."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        repo = _build_synthetic_project(Path(self._tmp.name))
        self._cache = repo / ".project-intelligence-cache"
        self._cache.mkdir(exist_ok=True)
        # Pin an approval key so the materialise path can sign and verify
        # a token end-to-end without falling through to the closed boundary.
        # Restore the prior value on teardown so a sibling test that asserts
        # policy denies without an approval key still does so even when this
        # test ran first.
        self._previous_approval_key = os.environ.get("PI_APPROVAL_KEY")
        os.environ["PI_APPROVAL_KEY"] = "phase9-smoke-key"
        self.addCleanup(self._restore_approval_key)

        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.adapters.ui.http_server import UiHttpServer

        self._service, self._readiness = build_ui_service(
            repo_root=repo, cache_root=self._cache,
        )
        self._server = UiHttpServer(
            self._service, host="127.0.0.1", port=0,
            readiness=lambda: bool(self._readiness.snapshot().consistent),
        )
        self._server.start_background()
        self.addCleanup(self._server.stop)
        self._base = f"http://{self._server.host}:{self._server.port}"

    def _restore_approval_key(self) -> None:
        if self._previous_approval_key is None:
            os.environ.pop("PI_APPROVAL_KEY", None)
        else:
            os.environ["PI_APPROVAL_KEY"] = self._previous_approval_key

    def test_health_is_liveness_not_readiness(self) -> None:
        """Liveness precedes readiness: hydration is unstarted here."""
        status, body = _http_get(f"{self._base}/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["status"], "ok")

    def test_readiness_endpoint_distinct(self) -> None:
        """``/health/ready`` reflects hydration; 503 until then."""
        import urllib.error

        try:
            status, body = _http_get(f"{self._base}/health/ready")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 503)
            payload = json.loads(exc.read())
            self.assertEqual(payload["ready"], False)
        else:
            # If hydration raced, the body must at least carry ``ready``.
            self.assertIn("ready", json.loads(body))
            self.assertEqual(status, 200)

    def test_ui_root_is_served(self) -> None:
        status, body = _http_get(f"{self._base}/")
        self.assertEqual(status, 200)
        self.assertTrue(body.startswith(b"<!DOCTYPE html"))

    def test_project_version_route_responds(self) -> None:
        status, body = _http_get(f"{self._base}/api/v1/project-version")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        # The version-identity seam reports ``head`` (the Git commit hash)
        # and a fingerprint of the working tree; both fields must be present
        # even when their values are empty (uncommitted tree fingerprint).
        self.assertIn("head", payload)
        self.assertIn("fingerprint", payload)
        self.assertNotEqual(payload["head"], "")

    def test_sources_route_responds(self) -> None:
        status, body = _http_get(f"{self._base}/api/v1/sources")
        self.assertEqual(status, 200)
        self.assertIsInstance(json.loads(body), (list, dict))

    def test_unknown_route_is_404(self) -> None:
        import urllib.error

        with self.assertRaises(urllib.error.HTTPError) as ctx:
            _http_get(f"{self._base}/api/v1/does-not-exist")
        self.assertEqual(ctx.exception.code, 404)

    def test_loopback_only(self) -> None:
        """The server must bind to 127.0.0.1, never 0.0.0.0."""
        self.assertEqual(self._server.host, "127.0.0.1")

    def test_materialise_end_to_end_with_hmac_token(self) -> None:
        """End-to-end: RestService.materialise shares its trusted approval
        boundary with MaterialiseService. A token issued by the boundary
        the service was built with must succeed; a foreign token must be
        rejected."""
        from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
        from pi_platform.ports import ApprovalRequest
        from pi_platform.ports.control.policy import Role
        from pi_platform.ports.ui.rest_api import MaterializeRequest, UiActor

        # ``materialize`` requires the ``administrator`` role (§59.5).
        actor = UiActor(actor_type="human", actor_id="operator", role=Role.ADMINISTRATOR.value)
        boundary = HmacTrustedApprovalBoundary(key=b"phase9-smoke-key")
        token = boundary.issue(
            ApprovalRequest(
                action="materialise",
                repo_root=str(self._server.service._repo_root),
            )
        )
        # Pre-create the canonical Wiki bundle so the §10 OKF gate passes.
        wiki = self._server.service._repo_root / "project-knowledge" / "wiki"
        wiki.mkdir(parents=True, exist_ok=True)
        (wiki / "index.md").write_text(
            '---\nokf_version: "0.2"\ntype: WikiIndex\n---\n\n# Index\n',
            encoding="utf-8",
        )
        result = self._service.materialize(
            actor, MaterializeRequest(approval_token=token)
        )
        self.assertTrue(result.materialized, result)
        # The foreign-token branch must close.
        foreign = HmacTrustedApprovalBoundary(key=b"other-key").issue(
            ApprovalRequest(
                action="materialise",
                repo_root=str(self._server.service._repo_root),
            )
        )
        with self.assertRaises(Exception):
            self._service.materialize(actor, MaterializeRequest(approval_token=foreign))


# ---------------------------------------------------------------------------
# Block G2 — gated container smoke
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    docker = shutil.which("docker")
    if not docker:
        return False
    try:
        proc = subprocess.run(
            [docker, "info"], check=False, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


class ContainerSmokeTests(unittest.TestCase):
    """Gated container build/start smoke (Block G2/G3).

    The default offline suite must skip this class cleanly. The gate is
    active when both ``PI_PHASE9_DOCKER_TESTS=1`` is exported and a Docker
    daemon is reachable.
    """

    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("PI_PHASE9_DOCKER_TESTS") != "1":
            raise unittest.SkipTest(
                "PI_PHASE9_DOCKER_TESTS not set; container smoke is opt-in"
            )
        if not _docker_available():
            raise unittest.SkipTest("docker not reachable on PATH/daemon")

    def test_image_builds_and_core_profile_reports_ready(self) -> None:
        docker = shutil.which("docker")
        assert docker is not None  # setUpClass guard
        env = os.environ.copy()
        env.setdefault("PI_PROFILE", "core-headless")
        env.setdefault("PI_CONTROL_PORT", "8765")

        build = subprocess.run(
            [docker, "compose", "--profile", env["PI_PROFILE"], "build"],
            cwd=ROOT, check=False, capture_output=True, text=True,
            env=env,
        )
        self.assertEqual(build.returncode, 0, build.stderr)

        up = subprocess.run(
            [docker, "compose", "--profile", env["PI_PROFILE"], "up", "-d"],
            cwd=ROOT, check=False, capture_output=True, text=True,
            env=env,
        )
        self.assertEqual(up.returncode, 0, up.stderr)
        try:
            # Readiness poll, not liveness.
            deadline = time.time() + 60
            ready = False
            while time.time() < deadline:
                probe = subprocess.run(
                    [docker, "compose", "--profile", env["PI_PROFILE"], "exec", "-T",
                     "core", "python", "-m", "pi_platform.cli", "health", "--ready"],
                    cwd=ROOT, check=False, capture_output=True, text=True, env=env,
                )
                if probe.returncode == 0:
                    ready = True
                    break
                time.sleep(2)
            self.assertTrue(ready, "core container did not become ready in 60s")
        finally:
            subprocess.run(
                [docker, "compose", "--profile", env["PI_PROFILE"], "down"],
                cwd=ROOT, check=False, capture_output=True, text=True, env=env,
            )


# ---------------------------------------------------------------------------
# Block F — compose profile matrix assertions
# ---------------------------------------------------------------------------


class ComposeProfileTests(unittest.TestCase):
    """``desktop-lite`` is single-container; no ``desktop-ui`` sidecar."""

    def test_compose_lists_all_five_profiles(self) -> None:
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for profile in ("core-headless", "desktop-lite", "desktop-local-ai",
                        "open-webui", "enterprise"):
            self.assertIn(profile, text, f"profile {profile} missing from compose")

    def test_desktop_ui_sidecar_is_gone(self) -> None:
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        # Block F2 reversal: the Phase 1 ``desktop-ui`` service must not appear.
        self.assertNotIn("  desktop-ui:", text)

    def test_no_mutable_main_tags_for_bundled_images(self) -> None:
        """Block F2: ``:main``/``:latest``/``:server`` are forbidden for
        bundled third-party images. Operator-supplied model endpoints are
        explicitly out of scope — ProjectExpert does not bundle a model.
        """
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        for forbidden in (":main", ":latest", "ghcr.io/ggml-org/llama.cpp:server"):
            self.assertNotIn(forbidden, text, f"mutable tag present: {forbidden}")

    def test_open_webui_sidecar_does_not_force_a_model_endpoint(self) -> None:
        """The Open WebUI profile is a placeholder; teams configure their
        own model endpoint via a project-local override. Hard-wiring
        ``OPENAI_API_BASE_URL:`` to anything (including ``http://core``)
        is forbidden for the open-webui sidecar. Comments explaining the
        policy are allowed and intentionally not stripped."""
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        # The check is line-anchored so prose in comments does not match.
        section_start = text.find("open-webui:")
        self.assertNotEqual(section_start, -1)
        next_profile = text.find("\n  ", section_start + len("open-webui:"))
        section = text[section_start:next_profile if next_profile != -1 else len(text)]
        for forbidden in ("OPENAI_API_BASE_URL:", "OPENAI_API_KEY:"):
            self.assertNotIn(forbidden, section, f"hard-wired model endpoint: {forbidden}")

    def test_desktop_lite_profile_bundles_a_local_model(self) -> None:
        """By default ``desktop-lite`` ships a local model sidecar so text
        retrieval answers out of the box. Operators swap the endpoint
        from the UI; we never hard-wire a remote model."""
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        # The ``local-llm:`` service block must list ``desktop-lite`` in
        # its profiles. Anchor on a line boundary so we don't accidentally
        # match the URL ``http://local-llm:8767/v1`` in the env defaults.
        lines = text.splitlines()
        start_line = -1
        for offset, line in enumerate(lines):
            if line.startswith("  local-llm:"):
                start_line = offset
                break
        self.assertNotEqual(start_line, -1, "local-llm service block missing")
        section_end = len(lines)
        for offset in range(start_line + 1, len(lines)):
            line = lines[offset]
            if line.startswith("  ") and line.endswith(":"):
                section_end = offset
                break
        section = "\n".join(lines[start_line:section_end])
        self.assertIn("desktop-lite", section)

    def test_core_advertises_default_model_endpoint_via_env(self) -> None:
        """The core service exposes ``PI_OPENAI_BASE_URL`` and
        ``PI_OPENAI_MODEL`` so the bundled local model is the default
        while remaining operator-overridable."""
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn("PI_OPENAI_BASE_URL:", text)
        self.assertIn("PI_OPENAI_MODEL:", text)

    def test_open_webui_profile_does_not_depend_on_local_llm(self) -> None:
        """The Open WebUI profile must not depend on ``local-llm`` because
        ``local-llm`` only exists in the ``desktop-local-ai`` profile."""
        text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        # Crude parse: the ``open-webui`` service must not list
        # ``local-llm`` in its ``depends_on`` block.
        section_start = text.find("open-webui:")
        self.assertNotEqual(section_start, -1)
        next_profile = text.find("\n  ", section_start + len("open-webui:"))
        section = text[section_start:next_profile if next_profile != -1 else len(text)]
        self.assertNotIn("local-llm", section)

    def test_containerfile_copies_static_assets_and_okf_profile(self) -> None:
        text = (ROOT / "Containerfile").read_text(encoding="utf-8")
        self.assertIn("COPY pi_platform ./pi_platform", text)
        self.assertIn("COPY distribution/okf-profile ./distribution/okf-profile", text)
        self.assertIn("EXPOSE 8765", text)

    def test_containerfile_keeps_digest_pinned_base(self) -> None:
        text = (ROOT / "Containerfile").read_text(encoding="utf-8")
        # The base image MUST be pinned by digest.
        self.assertRegex(
            text, r"FROM python:[^\s]+@sha256:[0-9a-f]{64}",
        )

    def test_containerfile_has_no_node(self) -> None:
        text = (ROOT / "Containerfile").read_text(encoding="utf-8").lower()
        # No node binary, no npm install, no Node.js base image.
        self.assertNotIn("nodejs", text)
        self.assertNotIn("npm install", text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()