import pathlib, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

class OpenCodeHermesTests(unittest.TestCase):
    def setUp(self):
        self.tool = (ROOT / 'templates/opencode/hermes.js').read_text()
        self.gen = (ROOT / 'scripts/configure_clients.py').read_text()

    def test_uses_native_runs_api_not_model_provider(self):
        self.assertIn('"POST", "/v1/runs"', self.tool)
        self.assertIn('/v1/runs/${encodeURIComponent(runId)}', self.tool)
        self.assertNotIn('/v1/chat/completions', self.tool)
        self.assertNotIn('hermes-remote', self.gen)

    def test_exposes_control_tools(self):
        for name in ('delegate', 'status', 'wait', 'result', 'steer', 'approve', 'cancel'):
            self.assertIn(f'export const {name} = tool(', self.tool)
        self.assertIn('waiting_for_approval', self.tool)
        self.assertIn('Do not send a model override', self.tool)

    def test_reads_generated_runtime_and_secret(self):
        self.assertIn('opencode-hermes-runtime.json', self.tool)
        self.assertIn('hermes-api-key', self.tool)
        self.assertIn('projectRoot', self.tool)

    def test_approval_transport_is_capability_gated_and_metadata_survives(self):
        self.assertIn('"GET", "/v1/capabilities"', self.tool)
        self.assertIn('run_approval_response', self.tool)
        self.assertIn('resolver_scoped_run_approvals', self.tool)
        self.assertIn('unattended auto-approval is not permitted', self.tool)
        self.assertIn('approval_events: run.approval_events', self.tool)
        self.assertIn('pending_approvals: run.pending_approvals', self.tool)

    def test_requests_are_hard_deadline_bounded(self):
        self.assertIn('new AbortController()', self.tool)
        self.assertIn('deadlineMs', self.tool)
        self.assertIn('clearTimeout(timer)', self.tool)

    def test_generator_removes_old_model_subagent(self):
        self.assertIn('generated-hermes*.md', self.gen)
        self.assertIn('tool_dir / "hermes.js"', self.gen)
        self.assertIn('hermes_approve', self.gen)
