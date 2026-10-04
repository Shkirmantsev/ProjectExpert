import importlib.util
import pathlib
import unittest
import tempfile
import json
import tomllib
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load_generator():
    import sys
    sys.path.insert(0, str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location('configure_clients_test', ROOT / 'scripts/configure_clients.py')
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class ClientTests(unittest.TestCase):
    def test_clients_pin_context_root_and_escape_command(self):
        gen = load_generator()
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            with patch.object(gen, 'ROOT', root):
                catalog = gen.logical_mcp_catalog({'PROJECT_ROOT': d})
                command = catalog['project-context']['command']
                self.assertEqual(['--root', str(root.resolve())], command[-2:])
                command[0] = '/tmp/a "quoted" path/server'
                gen.configure_claude({}, catalog)
                claude = json.loads((root / '.mcp.json').read_text(encoding="utf-8"))
                self.assertEqual(['--root', str(root.resolve())], claude['mcpServers']['project-context']['args'])
                gen.configure_codex({}, catalog)
                codex = tomllib.loads((root / '.codex/config.toml').read_text(encoding="utf-8"))
                self.assertEqual(command[0], codex['mcp_servers']['project_context']['command'])
                self.assertEqual(['--root', str(root.resolve())], codex['mcp_servers']['project_context']['args'])
                for render in (gen.render_opencode_v1, gen.render_opencode_v2):
                    self.assertIn('--root', json.dumps(render({}, catalog)))

    def test_generator_preserves_client_specific_hermes_transports(self):
        text = (ROOT / 'scripts/configure_clients.py').read_text(encoding="utf-8")
        self.assertIn('HERMES_REMOTE_SIDECAR_PORT', text)
        self.assertIn('tool_dir / "hermes.js"', text)
        self.assertIn('opencode-hermes-runtime.json', text)
        self.assertNotIn('providers["hermes-remote"]', text)
        self.assertNotIn('HERMES_CONTROL_MCP_PORT', text)
        self.assertNotIn('hermes-bind', text)
        self.assertNotIn('PROJECT_BRIDGE_TOKEN', text)
        self.assertIn('scripts/skill_router.py --profile local-small', text)

    def test_opencode_v1_is_default_and_v2_is_separate_native_generation(self):
        gen = load_generator()
        mcp = {'project-context': {'type': 'local', 'command': ['/tmp/project-context-mcp']}}
        v1 = gen.render_opencode_v1({}, mcp)
        self.assertIn('permission', v1)
        self.assertIn('mcp', v1)
        self.assertIn('project-context', v1['mcp'])
        self.assertNotIn('servers', v1['mcp'])
        self.assertTrue(v1['mcp']['project-context']['enabled'])
        self.assertNotIn('providers', v1)

        v2 = gen.render_opencode_v2({}, mcp)
        self.assertIn('permissions', v2)
        self.assertIn('servers', v2['mcp'])
        self.assertFalse(v2['mcp']['servers']['project-context']['disabled'])
        self.assertNotIn('permission', v2)

    def test_litellm_provider_shapes_do_not_mix_generations(self):
        gen = load_generator()
        env = {'LITELLM_ENABLED': 'true', 'LOCAL_MODEL_1_ENABLED': 'false'}
        v1 = gen.render_opencode_v1(env, {})
        self.assertIn('provider', v1)
        self.assertIn('npm', v1['provider']['harness'])
        self.assertIn('options', v1['provider']['harness'])
        self.assertNotIn('providers', v1)
        v2 = gen.render_opencode_v2(env, {})
        self.assertIn('providers', v2)
        self.assertIn('package', v2['providers']['harness'])
        self.assertIn('settings', v2['providers']['harness'])
        self.assertNotIn('provider', v2)

    def test_shared_skills_have_native_contract(self):
        text = '\n'.join(p.read_text(encoding="utf-8") for p in (ROOT / '.agents/skills').rglob('SKILL.md'))
        self.assertIn("OpenCode delegates through project-local `hermes_*` custom tools", text)
        self.assertIn('Claude Code delegates through the dedicated remote Hermes MCP sidecar', text)
        self.assertNotIn('make hermes-bind', text)
        self.assertNotIn('image_paths', text)
        self.assertNotIn('workspace symlink', text.lower())
