import pathlib, re, unittest, yaml
ROOT = pathlib.Path(__file__).resolve().parents[1]

class ArchitectureTests(unittest.TestCase):
    def test_compose_is_small_and_has_no_local_hermes_or_firecrawl(self):
        data = yaml.safe_load((ROOT / 'infra/compose.yaml').read_text())
        services = set(data['services'])
        self.assertEqual(services, {
            'litellm','litellm-edge','searxng','searxng-mcp',
            'crawl4ai','crawl4ai-http-bridge','playwright-mcp'
        })
        self.assertNotIn('volumes', data)
        text = (ROOT / 'infra/compose.yaml').read_text().lower()
        for bad in ('firecrawl','rabbitmq','postgres','project-bridge-edge','project-dev','hermes-bridge','hermes-control-mcp'):
            self.assertNotIn(bad, text)

    def test_env_removed_old_bridge_variables(self):
        text = (ROOT / '.env.example').read_text().lower()
        for bad in ('firecrawl_','project_bridge','binding_ttl','hermes_local_bridge_port','hermes_control_mcp_port','hermes_remote_workspace'):
            self.assertNotIn(bad, text)
        for required in ('HERMES_REMOTE_SIDECAR_PORT=', 'HERMES_SIDECAR_TOKEN=', 'HERMES_REMOTE_OPENAI_PORT='):
            self.assertIn(required, (ROOT / '.env.example').read_text())

    def test_all_compose_variables_are_declared(self):
        compose = (ROOT / 'infra/compose.yaml').read_text()
        env_keys = {line.split('=',1)[0] for line in (ROOT / '.env.example').read_text().splitlines() if line and not line.startswith('#') and '=' in line}
        refs = set(re.findall(r'\$\{([A-Z0-9_]+)(?::-[^}]*)?\}', compose))
        self.assertFalse(refs - env_keys, f"Missing env vars: {sorted(refs-env_keys)}")


    def test_litellm_uses_official_upstream_image_without_build(self):
        data = yaml.safe_load((ROOT / 'infra/compose.yaml').read_text())
        service = data['services']['litellm']
        self.assertEqual(service['image'], 'ghcr.io/berriai/litellm:v${LITELLM_VERSION}')
        self.assertNotIn('build', service)
        self.assertFalse((ROOT / 'infra/litellm/Dockerfile').exists())
        mounts = service.get('volumes', [])
        self.assertTrue(any('generate_config.py:/harness/generate_config.py:ro' in x for x in mounts))
        self.assertTrue(any('reasoning_policy.py:/harness/reasoning_policy.py:ro' in x for x in mounts))
        self.assertTrue(any('policy_core.py:/harness/policy_core.py:ro' in x for x in mounts))

    def test_pull_skips_build_only_local_images(self):
        text = (ROOT / 'scripts/stack.py').read_text()
        self.assertIn('pull", "--ignore-buildable', text)

    def test_remote_sidecar_is_bundled_outside_compose(self):
        self.assertTrue((ROOT / 'remote/hermes-worker-mcp/pyproject.toml').is_file())
        self.assertTrue((ROOT / 'remote/hermes-worker-mcp/src/hermes_worker_mcp/server.py').is_file())
    def test_sidecar_copy_uses_neutral_remote_staging(self):
        text = (ROOT / 'scripts/copy_remote_sidecar.py').read_text()
        self.assertIn('/var/tmp/harness-hermes-worker-mcp', text)
        self.assertNotIn('~/.local/share/hermes-worker-mcp', text)
