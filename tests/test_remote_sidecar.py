import importlib.util, pathlib, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]
path = ROOT / 'remote/hermes-worker-mcp/src/hermes_worker_mcp/native_context.py'
spec = importlib.util.spec_from_file_location('native_context', path)
mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)

class SidecarContractTests(unittest.TestCase):
    def test_root_validation(self):
        root = '/main/projects/repo'
        self.assertEqual(mod.validate_project_root(root), root)
        self.assertEqual(mod.validate_project_root(root, (root,)), root)
        with self.assertRaises(ValueError):
            mod.validate_project_root('/main/projects/outside', (root,))
        for bad in ('repo','/','/a\nb'):
            with self.assertRaises(ValueError):
                mod.validate_project_root(bad)

    def test_context_delegates_file_access_to_native_hermes(self):
        text = mod.instructions('/home/u/repo')
        self.assertIn('YOUR OWN Hermes tools', text)
        self.assertIn('native SSH environment', text)
        self.assertIn('vision', text.lower())
        self.assertNotIn('bridge_token', text.lower())

    def test_sidecar_server_has_only_run_control_tools(self):
        text = (ROOT / 'remote/hermes-worker-mcp/src/hermes_worker_mcp/server.py').read_text()
        for tool in ('hermes_run','hermes_status','hermes_wait','hermes_result','hermes_steer','hermes_approve','hermes_cancel'):
            self.assertIn(f'def {tool}', text)
        for bad in ('BindingStore','project_relay','/v1/bindings','skills/{name','image_part','/workspace'):
            self.assertNotIn(bad, text)

    def test_sidecar_uses_native_runs_contract_safely(self):
        text = (ROOT / 'remote/hermes-worker-mcp/src/hermes_worker_mcp/server.py').read_text()
        self.assertIn('"/v1/runs"', text)
        self.assertIn('{"input": guidance}', text)
        self.assertIn('waiting_for_approval', text)
        self.assertIn('timeout_seconds=remaining', text)
        self.assertIn("quote(value, safe='')", text)
        self.assertNotIn('"model": settings.model', text)
        env = (ROOT / 'remote/hermes-worker-mcp/.env.example').read_text()
        self.assertIn('HERMES_API_BASE_URL=http://127.0.0.1:8642\n', env)
        self.assertIn('HERMES_ALLOWED_PROJECT_ROOTS=', env)
        self.assertNotIn('8642/v1', env)
    def test_systemd_install_uses_real_linux_home_not_HOME_env(self):
        text = (ROOT / 'remote/hermes-worker-mcp/scripts/install_service.py').read_text()
        self.assertIn('pwd.getpwuid(os.getuid()).pw_dir', text)
        self.assertNotIn('Path.home() / ".config/systemd/user"', text)
