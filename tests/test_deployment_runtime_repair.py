"""Deployment capacity, upgrade, frontend health and cache-preserving retry."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'distribution/deployment'


def exporter():
    spec = importlib.util.spec_from_file_location('repair_kit_export', BUNDLE / 'export.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DeploymentRuntimeRepairTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose required')
    def test_operator_frontend_name_survives_template_upgrade(self):
        module = exporter()
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / 'kit'
            module.export(BUNDLE, dest)
            with (dest / 'deployment.env').open('a') as stream:
                stream.write('\nPI_WEBUI_NAME=ProjectExpert - regression\n')
            module.export(BUNDLE, dest, upgrade=True)
            result = subprocess.run(['docker', 'compose', '--env-file', str(dest / 'deployment.env'),
                '-f', str(dest / 'compose.yaml'), '--profile', 'open-webui', 'config', '--format', 'json'],
                env={k: v for k, v in os.environ.items() if k != 'PI_WEBUI_NAME'},
                capture_output=True, text=True, check=True, timeout=30)
            ui = json.loads(result.stdout)['services']['open-webui']
            self.assertEqual(ui['environment']['WEBUI_NAME'], 'ProjectExpert - regression')

    def test_native_and_managed_capacity_admit_wider_chunks(self):
        from pi_platform.core.inference.launch import build_server_argv
        native = build_server_argv(model_path='model', projector_path='projector', alias='gemma')
        commands = {'native': native}
        for name in ('compose.accelerator.yaml', 'compose.vulkan.yaml', 'compose.cuda.yaml'):
            commands[name] = yaml.safe_load((BUNDLE / name).read_text())['services']['embeddings']['command']
        for name, command in commands.items():
            with self.subTest(launch=name):
                for flag in ('--ctx-size', '--batch-size', '--ubatch-size'):
                    capacity = int(command[command.index(flag) + 1])
                    self.assertGreater(capacity, 1049)
                    self.assertGreaterEqual(capacity, 4096)
                self.assertEqual(str(command[command.index('--parallel') + 1]), '1')

    def test_upgrade_keeps_env_and_backs_up_changed_templates(self):
        module = exporter()
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / 'kit'
            module.export(BUNDLE, dest)
            env = b'PI_CONTROL_PORT=8766\nPI_ACCELERATOR=cpu\n'
            (dest / 'deployment.env').write_bytes(env)
            (dest / 'compose.yaml').write_text('operator old compose')
            (dest / 'notes.txt').write_text('operator notes')
            module.export(BUNDLE, dest, upgrade=True)
            self.assertEqual((dest / 'deployment.env').read_bytes(), env)
            self.assertEqual((dest / 'compose.yaml').read_bytes(), (BUNDLE / 'compose.yaml').read_bytes())
            self.assertEqual((dest / 'notes.txt').read_text(), 'operator notes')
            backups = list((dest / '.kit-backups').glob('*/compose.yaml'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'operator old compose')
            module.export(BUNDLE, dest, upgrade=True)
            self.assertEqual(len(list((dest / '.kit-backups').iterdir())), 1)

    def test_upgrade_refuses_managed_symlink_before_writing(self):
        module = exporter()
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / 'kit'
            module.export(BUNDLE, dest)
            (dest / 'compose.yaml').write_text('old compose')
            outside = Path(raw) / 'external'
            outside.write_text('keep external')
            (dest / 'Makefile').unlink()
            try:
                (dest / 'Makefile').symlink_to(outside)
            except OSError as exc:
                self.skipTest(f'Symlinks unavailable: {exc}')
            with self.assertRaises(ValueError):
                module.export(BUNDLE, dest, upgrade=True)
            self.assertEqual((dest / 'compose.yaml').read_text(), 'old compose')
            self.assertEqual(outside.read_text(), 'keep external')

    def test_exported_frontend_uses_internal_adapter_and_python_health(self):
        services = yaml.safe_load((BUNDLE / 'compose.yaml').read_text())['services']
        ui = services['open-webui']
        self.assertEqual(ui['profiles'], ['open-webui'])
        self.assertEqual(ui['environment']['OPENAI_API_BASE_URL'], 'http://production:8765/v1')
        self.assertIn('127.0.0.1', ui['ports'][0])
        probe = ui['healthcheck']['test']
        self.assertEqual(probe[:3], ['CMD', 'python', '-c'])
        status = {'status': True}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps(status).encode())
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        code = probe[3].replace('http://127.0.0.1:8080/health', f'http://127.0.0.1:{server.server_port}/health')
        self.assertEqual(subprocess.run([sys.executable, '-c', code], capture_output=True).returncode, 0)
        status['status'] = False
        self.assertNotEqual(subprocess.run([sys.executable, '-c', code], capture_output=True).returncode, 0)

    def test_successful_retry_clears_failure_without_deleting_cache(self):
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError
        with tempfile.TemporaryDirectory() as raw, patch.dict(os.environ, {
                'PI_STARTUP_PROFILE': 'minimal', 'PI_EMBEDDING_MODEL': 'hashing',
                'PI_DENSE_INDEX': 'flat', 'PI_DOCLING_ENABLED': '0'}):
            target = Path(raw)
            (target / 'billing.md').write_text('Quasar invoices require evidence.')
            service, ready = build_ui_service(repo_root=target, defer_runtime=True)
            service._chat_connection.save({'base_url': 'http://localhost:1234/v1', 'model': 'keep-chat'})
            cache = target / '.project-intelligence-cache'
            with patch('pi_platform.core.retrieval.embedding_model.HashingEmbeddingModel.embed_request', side_effect=EmbeddingModelError('fixture embedding failure')):
                with self.assertRaisesRegex(RuntimeError, 'fixture embedding failure'):
                    _bootstrap_and_index_target(target, service=service, readiness=ready)
            self.assertFalse(ready.is_ready())
            self.assertIn('fixture embedding failure', json.loads((cache / 'readiness.json').read_text())['reason'])
            result = _bootstrap_and_index_target(target, service=service, readiness=ready)
            self.assertTrue(result['ready'])
            self.assertTrue(ready.is_ready())
            self.assertEqual(json.loads((cache / 'readiness.json').read_text())['reason'], '')
            self.assertEqual(service._chat_connection.public_settings()['model'], 'keep-chat')
