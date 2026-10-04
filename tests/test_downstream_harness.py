"""Behavior checks for the reusable downstream harness improvements."""
import json
import os
from pathlib import Path
import sys
import tempfile
import tomllib
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import common
import configure_clients
import context_pack
import lesson_candidate
import session_state
import skill_router
import sync_skills
import harness


class DownstreamHarnessTests(unittest.TestCase):
    def test_environment_replacement_preserves_literal_backslashes(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "fixture.env"
            path.write_text("TEST_PATH=old\nUNCHANGED=yes\n")
            value = r"C:\new\工具\1"
            common.update_env({"TEST_PATH": value}, path)
            self.assertEqual(common.parse_env(path), {"TEST_PATH": value, "UNCHANGED": "yes"})

    def test_windows_atomic_state_writes_skip_directory_handles(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for module in (context_pack, lesson_candidate, session_state):
                with self.subTest(module=module.__name__):
                    path = root / (module.__name__ + ".json")
                    path.write_text("old")
                    portable_os = types.SimpleNamespace(**vars(os))
                    portable_os.name = "nt"
                    portable_os.open = mock.Mock(side_effect=AssertionError("directory handle on Windows"))
                    with mock.patch.object(module, "os", portable_os):
                        if module is session_state:
                            module.atomic_write_bytes(path, b'{"complete": true}')
                        else:
                            module.atomic_write(path, {"complete": True})
                    self.assertEqual(json.loads(path.read_text()), {"complete": True})
                    self.assertEqual(sorted(p.name for p in root.glob(".*")), [])

    def test_router_fallback_returns_only_unloaded_sorted_metadata(self):
        plan = skill_router.build_plan("Please untangle these troublesome widgets", "balanced")
        self.assertTrue(plan["needs_clarification"])
        self.assertTrue(plan["catalog_index"])
        active = {item["name"] for item in plan["required_skills"]}
        names = []
        for item in plan["catalog_index"]:
            self.assertEqual(set(item), {"name", "description"})
            self.assertNotIn(item["name"], active)
            self.assertTrue(skill_router.discover()[item["name"]].path.is_relative_to(skill_router.SKILLS_ROOT / "catalog"))
            names.append(item["name"])
        self.assertEqual(names, sorted(names))
        self.assertEqual(skill_router.build_plan("Use ponytail to implement this", "balanced")["catalog_index"], [])
        names = {item["name"] for item in skill_router.build_plan("Use ponytail", "balanced")["required_skills"]}
        self.assertIn("ponytail", names)

    def test_local_sync_preserves_each_clients_integration_and_personal_skills(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            source = root / "source"
            catalog = source / "catalog"
            for name in sync_skills.CORE_SKILL_NAMES:
                (source / name).mkdir(parents=True)
                (source / name / "SKILL.md").write_text(name)
            (catalog / "optional").mkdir(parents=True)
            (catalog / "optional" / "SKILL.md").write_text("optional")
            clients = [root / "claude", root / "opencode"]
            for client in clients:
                for name in ("openspec-propose", "personal", "optional"):
                    (client / name).mkdir(parents=True)
                    (client / name / "SKILL.md").write_text("owned " + name)
            with (mock.patch.object(sync_skills, "SOURCE", source),
                  mock.patch.object(sync_skills, "CATALOG", catalog),
                  mock.patch.object(sync_skills, "CLAUDE", clients[0]),
                  mock.patch.object(sync_skills, "OPENCODE", clients[1])):
                sync_skills.local()
                sync_skills.check()
                for client in clients:
                    self.assertFalse((client / "optional").exists())
                    self.assertEqual((client / "personal" / "SKILL.md").read_text(), "owned personal")
                    self.assertEqual((client / "openspec-propose" / "SKILL.md").read_text(), "owned openspec-propose")
                (clients[1] / "verification" / "SKILL.md").write_text("drift")
                with self.assertRaises(SystemExit):
                    sync_skills.check()

    def test_context7_is_opt_in_and_authenticated_across_clients(self):
        env = {"PROJECT_CONTEXT_MCP_ENABLED": "false"}
        self.assertNotIn("context7", configure_clients.logical_mcp_catalog(env))
        env.update({"CONTEXT7_MCP_ENABLED": "true", "CONTEXT7_MCP_API_KEY": "fixture-key"})
        catalog = configure_clients.logical_mcp_catalog(env)
        expected = {"Authorization": "Bearer fixture-key"}
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with (mock.patch.object(configure_clients, "ROOT", root),
                  mock.patch.object(configure_clients, "GEN", root / ".generated")):
                configure_clients.configure_claude(env, catalog)
                configure_clients.configure_codex(env, catalog)
                for generation in ("v1", "v2"):
                    configure_clients.configure_opencode(dict(env, OPENCODE_CONFIG_GENERATION=generation), catalog)
                    written = json.loads((root / "opencode.json").read_text())["mcp"]
                    self.assertEqual(written.get("servers", written)["context7"]["headers"], expected)
            claude = json.loads((root / ".mcp.json").read_text())["mcpServers"]["context7"]
            codex = tomllib.loads((root / ".codex/config.toml").read_text())["mcp_servers"]["context7"]
            self.assertEqual(claude["headers"], expected)
            self.assertEqual(codex["http_headers"], expected)
            self.assertNotIn("command", codex)
            for render in (configure_clients.render_opencode_v1, configure_clients.render_opencode_v2):
                config = render(env, catalog)
                servers = config["mcp"].get("servers", config["mcp"])
                self.assertEqual(servers["context7"]["headers"], expected)
            if os.name != "nt":
                for name in (".mcp.json", ".codex/config.toml", "opencode.json"):
                    self.assertEqual((root / name).stat().st_mode & 0o777, 0o600)
        env["CONTEXT7_MCP_API_KEY"] = ""
        self.assertNotIn("headers", configure_clients.logical_mcp_catalog(env)["context7"])
        for url in ("http://example.com/mcp", "https://user:password@example.com/mcp", "not-a-url"):
            env["CONTEXT7_MCP_URL"] = url
            with self.subTest(url=url), self.assertRaises(ValueError):
                configure_clients.logical_mcp_catalog(env)

    def test_openspec_gate_rejects_specs_the_cli_would_ignore(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            specs = root / "openspec/specs"
            specs.mkdir(parents=True)
            (specs / "missed.md").write_text("A loose requirement")
            with mock.patch.object(harness, "ROOT", root), self.assertRaises(SystemExit):
                harness.cmd_openspec_check()

    def test_launcher_resolves_platform_executable_before_subprocess(self):
        with (mock.patch.object(harness.shutil, "which", return_value="/tools/openspec.cmd"),
              mock.patch.object(harness.subprocess, "run") as run):
            harness.run(["openspec", "validate"])
        self.assertEqual(run.call_args.args[0], ["/tools/openspec.cmd", "validate"])


if __name__ == "__main__":
    unittest.main()
