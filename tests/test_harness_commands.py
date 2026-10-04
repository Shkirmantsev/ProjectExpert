"""Portable command aliases, configuration and process ownership regressions."""
from pathlib import Path
import subprocess
import sys
import tempfile
import json
import io
import os
import tomllib
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import harness
import configure_clients
import project_mcp


class HarnessCommandsTests(unittest.TestCase):
    def test_donor_cli_aliases_and_wiki_init(self):
        for alias in ['harness-init', 'harness-init-mcp', 'harness-mcp-install',
                      'harness-client-config', 'harness-check', 'harness-check-delegated',
                      'harness-test', 'harness-wiki-index', 'harness-wiki-validate',
                      'harness-openspec-check', 'harness-manifest-generate',
                      'harness-manifest-check', 'harness-clean', 'mcp-run', 'mcp-stop',
                      'wiki-init', 'init-wiki', 'mcp-status', 'mcp-logs', 'mcp-clean']:
            with self.subTest(alias=alias):
                self.assertIsNotNone(harness.parser().parse_args([alias]))
        with mock.patch.object(harness, 'cmd_wiki_validate') as validate, mock.patch.object(harness, 'cmd_index') as index:
            harness.cmd_wiki_init()
            validate.assert_called_once()
            index.assert_called_once()

    def test_project_context_http_opt_in_and_invalid_settings(self):
        self.assertEqual(configure_clients.logical_mcp_catalog({})['project-context']['type'], 'local')
        env = {'PROJECT_CONTEXT_MCP_TRANSPORT': 'http', 'PROJECT_CONTEXT_MCP_PORT': '18999'}
        mcp = configure_clients.logical_mcp_catalog(env)
        self.assertEqual(mcp['project-context'], {'type': 'remote', 'url': 'http://127.0.0.1:18999/mcp'})
        for value in ['no', '0', '1023', '65536']:
            with self.subTest(port=value), self.assertRaises(ValueError):
                project_mcp.settings({'PROJECT_CONTEXT_MCP_PORT': value})
        with self.assertRaises(ValueError):
            project_mcp.settings({'PROJECT_CONTEXT_MCP_TRANSPORT': 'tcp'})

    def test_http_endpoint_is_rendered_for_all_clients(self):
        env = {'PROJECT_CONTEXT_MCP_TRANSPORT': 'http'}
        catalog = configure_clients.logical_mcp_catalog(env)
        expected = 'http://127.0.0.1:18883/mcp'
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            with mock.patch.object(configure_clients, 'ROOT', root), mock.patch.object(configure_clients, 'GEN', root / '.generated'):
                configure_clients.configure_claude(env, catalog)
                configure_clients.configure_codex(env, catalog)
                for generation in ('v1', 'v2'):
                    configure_clients.configure_opencode(dict(env, OPENCODE_CONFIG_GENERATION=generation), catalog)
                    config = json.loads((root / 'opencode.json').read_text(encoding='utf-8'))['mcp']
                    self.assertEqual(config.get('servers', config)['project-context']['url'], expected)
            claude = json.loads((root / '.mcp.json').read_text(encoding='utf-8'))['mcpServers']['project-context']
            codex = tomllib.loads((root / '.codex/config.toml').read_text(encoding='utf-8'))['mcp_servers']['project_context']
            for config in (claude, codex):
                self.assertEqual(config['url'], expected)
                self.assertNotIn('command', config)

    def test_process_probe_does_not_terminate_a_live_process(self):
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(15)'])
        try:
            self.assertTrue(project_mcp.process_alive(child.pid))
            self.assertIsNone(child.poll())
        finally:
            child.terminate()
            child.wait(timeout=5)
        self.assertFalse(project_mcp.process_alive(child.pid))
        self.assertFalse(project_mcp.process_alive(0))

    def test_clean_refuses_active_worker_and_preserves_unrelated_files(self):
        with tempfile.TemporaryDirectory() as raw:
            lifecycle = project_mcp.Lifecycle(Path(raw))
            lifecycle.write({'phase': 'ready', 'workerPid': 123})
            sentinel = Path(raw) / 'other.log'
            sentinel.write_text('preserve')
            with mock.patch.object(project_mcp, 'process_alive', return_value=True):
                self.assertEqual(lifecycle.clean(), 1)
                self.assertTrue(lifecycle.state_file.exists())
            with mock.patch.object(project_mcp, 'process_alive', return_value=False):
                self.assertEqual(lifecycle.clean(), 0)
            self.assertEqual(sentinel.read_text(), 'preserve')

    def test_stale_state_stop_never_signals_its_pid(self):
        with tempfile.TemporaryDirectory() as raw:
            lifecycle = project_mcp.Lifecycle(Path(raw))
            lifecycle.write({'phase': 'ready', 'workerPid': 123, 'instance': 'stale'})
            with mock.patch.object(project_mcp, 'process_alive', return_value=False), mock.patch.object(project_mcp.os, 'kill') as kill:
                self.assertEqual(lifecycle.stop(), 0)
                kill.assert_not_called()

    def test_supervisor_errors_log_traceback_and_record_failure(self):
        for error in (KeyError('home'), FileNotFoundError('missing interpreter 工具')):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as raw:
                lifecycle = project_mcp.Lifecycle(Path(raw))
                lifecycle.write({'phase': 'starting', 'workerPid': os.getpid(),
                                 'instance': 'fixture', 'python': 'missing-python',
                                 'root': str(ROOT), 'port': 18883})
                with mock.patch.object(project_mcp.signal, 'signal'), mock.patch.object(project_mcp, 'server_command', side_effect=error if isinstance(error, KeyError) else None, return_value=['fixture']), mock.patch.object(project_mcp.subprocess, 'Popen', side_effect=error):
                    self.assertEqual(lifecycle.worker(), 1)
                self.assertEqual(lifecycle.read()['phase'], 'failed')
                diagnostic = lifecycle.log_file.read_text(encoding='utf-8')
                self.assertIn('Traceback (most recent call last)', diagnostic)
                self.assertIn(type(error).__name__, diagnostic)
                self.assertIn(str(error), diagnostic)
                with mock.patch('sys.stdout', new_callable=io.StringIO) as output:
                    lifecycle.logs()
                    self.assertIn(str(error), output.getvalue())

    def test_supervisor_logs_before_cleaning_up_owned_child(self):
        with tempfile.TemporaryDirectory() as raw:
            lifecycle = project_mcp.Lifecycle(Path(raw))
            lifecycle.write({'phase': 'starting', 'workerPid': os.getpid(),
                             'instance': 'fixture', 'python': 'python',
                             'root': str(ROOT), 'port': 18883})
            child = mock.Mock(pid=123)
            child.poll.side_effect = [RuntimeError('supervisor loop failure'), None]
            def assert_diagnostic_saved():
                self.assertIn('RuntimeError: supervisor loop failure',
                              lifecycle.log_file.read_text(encoding='utf-8'))
            child.kill.side_effect = assert_diagnostic_saved
            with mock.patch.object(project_mcp.signal, 'signal'), mock.patch.object(project_mcp, 'server_command', return_value=['fixture']), mock.patch.object(project_mcp.subprocess, 'Popen', return_value=child):
                self.assertEqual(lifecycle.worker(), 1)
            child.kill.assert_called_once()
            child.wait.assert_called_once_with(timeout=5)
            self.assertEqual(lifecycle.read()['phase'], 'failed')

    def test_clean_runtime_refuses_background_mcp_before_removing_files(self):
        with mock.patch.object(project_mcp.Lifecycle, 'active', return_value=True), mock.patch.object(harness.shutil, 'rmtree') as remove:
            with self.assertRaises(SystemExit):
                harness.cmd_clean()
            remove.assert_not_called()


if __name__ == '__main__':
    unittest.main()
