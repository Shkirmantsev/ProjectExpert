"""Regression evidence for portable runtime/Wiki migration review."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from pi_platform.core.wiki.llm_wiki import LlmWiki, LlmWikiError

ROOT = Path(__file__).resolve().parents[1]


class MigrationTests(unittest.TestCase):
    def test_gguf_smoke_imports_current_model_contract(self):
        spec = importlib.util.spec_from_file_location('smoke_gguf', ROOT / 'scripts/smoke_gguf_container.py')
        spec.loader.exec_module(importlib.util.module_from_spec(spec))

    def test_release_workflows_reference_existing_test_modules(self):
        import re
        for path in (ROOT / '.github/workflows').glob('*.yml'):
            for name in re.findall(r'tests\.(test_\w+)', path.read_text()):
                self.assertTrue((ROOT / 'tests' / (name + '.py')).is_file(), name)


class EntryPointDefaultsTests(unittest.TestCase):
    def test_make_defaults_match_their_runtime_topology(self):
        self.assertIn('PI_MODEL ?= $(or $(MODEL),gemma-torch)', (ROOT / 'Makefile').read_text())
        self.assertIn('MODEL ?= gemma', (ROOT / 'distribution/deployment/Makefile').read_text())


class WikiBoundaryTests(unittest.TestCase):
    def test_relative_repository_root(self):
        wiki = LlmWiki(Path('.'))
        with self.assertRaises(LlmWikiError):
            wiki.read_page('nonexistent-review-fixture')

    def test_list_does_not_read_symlink_outside_wiki(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            wiki = LlmWiki(repo)
            wiki.ensure_scaffold()
            external = repo / 'private.md'
            external.write_text('---\ntype: Concept\ntitle: Private\n---\nsecret uniquephrase')
            try:
                (wiki.root / 'leak.md').symlink_to(external)
            except OSError:
                self.skipTest('symlinks unavailable')
            self.assertEqual(wiki.list_pages(), [])
            self.assertEqual(wiki.search_pages('uniquephrase'), [])

    def test_reserved_log_symlink_rejected_before_page_write(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            wiki = LlmWiki(repo)
            wiki.ensure_scaffold()
            outside = repo / 'outside.txt'
            outside.write_text('unchanged')
            (wiki.root / 'log.md').unlink()
            try:
                (wiki.root / 'log.md').symlink_to(outside)
            except OSError:
                self.skipTest('symlinks unavailable')
            with self.assertRaises(LlmWikiError):
                wiki.write_page(relative_path='one', title='One', body='Body')
            self.assertEqual(outside.read_text(), 'unchanged')
            self.assertFalse((wiki.root / 'one.md').exists())

    def test_predictable_temporary_symlink_cannot_overwrite_file(self):
        with tempfile.TemporaryDirectory() as raw:
            repo = Path(raw)
            wiki = LlmWiki(repo)
            wiki.ensure_scaffold()
            outside = repo / 'outside.txt'
            outside.write_text('unchanged')
            try:
                (wiki.root / 'one.md.tmp').symlink_to(outside)
            except OSError:
                self.skipTest('symlinks unavailable')
            wiki.write_page(relative_path='one', title='One', body='Body')
            self.assertEqual(outside.read_text(), 'unchanged')

class AcceptedVersionTests(unittest.TestCase):
    def test_published_version_avoids_bootstrap_refresh_but_keeps_later_edits(self):
        from pi_platform.core.sync.version_monitor import PollingProjectVersionMonitor, ProjectVersionState
        initial = ProjectVersionState('head', 'main', 'before-settings')
        accepted = ProjectVersionState('head', 'main', 'after-settings')
        edited = ProjectVersionState('head', 'main', 'later-user-edit')
        current = [initial]
        def refresh(_):
            current[0] = accepted
            return accepted
        monitor = PollingProjectVersionMonitor(Path('.'), on_change=refresh, state_reader=lambda: current[0])
        monitor.poll_once()
        self.assertIsNone(monitor.poll_once())
        current[0] = edited
        self.assertIsNotNone(monitor.poll_once())

class LauncherStartupTests(unittest.TestCase):
    @unittest.skipUnless(__import__('shutil').which('bash'), 'bash required')
    def test_gpu_device_probe_success_but_startup_failure_falls_back(self):
        import os
        import shutil
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            shutil.copytree(ROOT / 'distribution/deployment', root / 'kit')
            docker = root / 'docker'
            docker.write_text('#!' + sys.executable + '''
import base64, json, os, subprocess, sys
args = sys.argv[1:]
with open(os.environ['CALLS'], 'a') as stream: stream.write('device=' + os.environ.get('PI_GPU_DEVICE', '') + ' ' + ' '.join(args) + '\\n')
if '--list-devices' in args:
    print('Available devices:\\n  CUDA1: Test GPU (4096 MiB, 4000 MiB free)\\n  CUDA2: Requested GPU (2048 MiB, 2000 MiB free)')
elif 'inference' in args and 'plan' in args:
    start = args.index('inference')
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pi_platform.cli', *args[start:]]))
elif 'up' in args and 'embeddings' in args:
    raise SystemExit(1)
''')
            docker.chmod(0o755)
            env = {**os.environ, 'PATH': str(root) + os.pathsep + os.environ['PATH'],
                   'PYTHONPATH': str(ROOT), 'CALLS': str(root / 'calls'), 'PI_ACCELERATOR': 'cuda', 'PI_GPU_DEVICE': 'CUDA2'}
            result = subprocess.run(['bash', str(root / 'kit/compose.sh'), 'up', '-d'], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Selected inference backend: cpu', result.stdout)
            self.assertIn('compose.cpu.yaml up -d', (root / 'calls').read_text())
            self.assertTrue(any(line.startswith('device=CUDA2 ') and 'up -d --wait' in line for line in (root / 'calls').read_text().splitlines()))

class BenchmarkValidationTests(unittest.TestCase):
    def test_http_success_requires_valid_embedding(self):
        import io
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        from pi_platform.cli.inference import _benchmark_client
        for payload in ({'error': 'not an embedding'}, {'data': [{'embedding': [0.1]}]},
                        {'data': [{'embedding': [float('nan')] * 768}]}):
            with self.subTest(payload=str(payload)[:80]):
                embed, _ = _benchmark_client(SimpleNamespace(endpoint='http://localhost:8769'))
                with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
                    with self.assertRaises(ValueError):
                        embed('query')
        embed, _ = _benchmark_client(SimpleNamespace(endpoint='http://localhost:8769'))
        with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps({'data': [{'embedding': [0.1] * 768}]}).encode())):
            embed('query')
