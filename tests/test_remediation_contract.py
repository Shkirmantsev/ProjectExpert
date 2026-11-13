"""Regression checks for preserved upgrades and actionable CI failures."""
import importlib.util
import hashlib
import json
import os
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from tests.test_workspace_deployment import compose_config

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('remediation_export', ROOT / 'distribution/deployment/export.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class EnvironmentMigrationTests(unittest.TestCase):
    def test_asset_migration_changes_only_matching_pins_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = Path(raw)
            path = kit / 'deployment.env'
            original = 'PI_INDEX_ENGINE=legacy\nPI_CONTROL_PORT=9876\nPI_ASSET_IMAGE=\nPI_ASSET_MANIFEST_SHA256=\n'
            path.write_text(original)
            manifest = kit / 'assets-lock.json'
            shutil.copyfile(ROOT / 'distribution/assets/assets-lock.json', manifest)
            digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
            image = 'ghcr.io/shkirmantsev/project-intelligence-assets@sha256:' + 'a' * 64
            (kit / 'asset-release.json').write_text(json.dumps({
                'release_status': 'verified', 'image': image, 'manifest_sha256': digest}))
            exporter.migrate_environment(kit, assets=True)
            self.assertEqual(path.read_text(), original.replace('PI_ASSET_IMAGE=\n', 'PI_ASSET_IMAGE=' + image + '\n')
                             .replace('PI_ASSET_MANIFEST_SHA256=\n', 'PI_ASSET_MANIFEST_SHA256=' + digest + '\n'))
            before = path.read_bytes()
            manifest.write_text('corrupt')
            with self.assertRaisesRegex(ValueError, 'matching manifest'):
                exporter.migrate_environment(kit, assets=True)
            self.assertEqual(path.read_bytes(), before)

    def test_preview_apply_idempotency_and_exact_backup(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = Path(raw)
            path = kit / 'deployment.env'
            original = b'# operator\r\nPI_INDEX_ENGINE=legacy\r\nPI_INDEX_PARALLEL=0\r\nPI_EMBED_BATCHING=0\r\nPI_CONTROL_PORT=9876\r\nPI_IMAGE=custom\r\n'
            path.write_bytes(original)
            exporter.migrate_environment(kit, indexing=True, dry_run=True)
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse((kit / '.kit-backups').exists())
            exporter.migrate_environment(kit, indexing=True)
            self.assertEqual(path.read_bytes(), original.replace(b'=legacy', b'=resumable').replace(b'=0', b'=1'))
            backups = list((kit / '.kit-backups').glob('*/deployment.env'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original)
            exporter.migrate_environment(kit, indexing=True)
            self.assertEqual(list((kit / '.kit-backups').glob('*/deployment.env')), backups)

    def test_blocked_asset_migration_preserves_entire_environment(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = Path(raw)
            path = kit / 'deployment.env'
            path.write_text('PI_INDEX_ENGINE=legacy\nPI_ASSET_IMAGE=operator\n')
            (kit / 'asset-release.json').write_text(json.dumps({'release_status': 'blocked'}))
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, 'verified published'):
                exporter.migrate_environment(kit, indexing=True, assets=True)
            self.assertEqual(path.read_bytes(), before)

    def test_fresh_kit_and_compose_defaults_agree(self):
        env = dict(line.split('=', 1) for line in (ROOT / 'distribution/deployment/deployment.env').read_text().splitlines()
                   if line and not line.startswith('#') and '=' in line)
        compose = (ROOT / 'distribution/deployment/compose.yaml').read_text()
        for key, value in {'PI_INDEX_ENGINE': 'resumable', 'PI_INDEX_PARALLEL': '1', 'PI_EMBED_BATCHING': '1'}.items():
            self.assertEqual(env[key], value)
            self.assertIn('${' + key + ':-' + value + '}', compose)


class CiDiagnosticsTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'posix' and shutil.which('bash'), 'Bash preflight fixture')
    def test_registry_preflight_skips_cached_images_and_retains_tls_on_failure(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / 'docker').write_text('#!/bin/bash\nif [ "$1" = context ]; then echo test-context; else exit "$CACHED_EXIT"; fi\n')
            (root / 'curl').write_text('#!/bin/bash\nprintf "%s\\n" "$*" > "$CURL_CALL"\nexit 60\n')
            for name in ('docker', 'curl'):
                (root / name).chmod(0o755)
            env = {**os.environ, 'PATH': raw + os.pathsep + os.environ['PATH'],
                   'CACHED_EXIT': '0', 'CURL_CALL': str(root / 'curl-call')}
            args = ['bash', str(ROOT / 'distribution/deployment/registry-preflight.sh'), 'ghcr.io/example/assets@sha256:' + '1' * 64]
            cached = subprocess.run(args, env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(cached.returncode, 0, cached.stderr)
            self.assertFalse((root / 'curl-call').exists())
            env['CACHED_EXIT'] = '1'
            uncached = subprocess.run(args, env=env, capture_output=True, text=True, timeout=5)
            self.assertEqual(uncached.returncode, 0, uncached.stderr)
            self.assertIn('Host registry HTTPS probe failed', uncached.stderr)
            call = (root / 'curl-call').read_text()
            self.assertIn('--max-time 15', call)
            self.assertNotIn('--insecure', call)
            self.assertIn('No trust settings were changed', uncached.stdout)

    def test_timeout_reports_bounded_diagnostics_without_retrying_config(self):
        failure = subprocess.TimeoutExpired(['docker', 'compose'], 120, stderr=b'CLI startup stalled')
        diagnostic = subprocess.CompletedProcess([], 0, 'version/context', '')
        with patch('tests.test_workspace_deployment.subprocess.run', side_effect=[failure, diagnostic, diagnostic, diagnostic]) as run:
            with self.assertRaisesRegex(AssertionError, 'CLI startup stalled.*elapsed='):
                compose_config(['docker', 'compose'], os.environ)
        self.assertEqual(run.call_count, 4)
        self.assertEqual([call.kwargs['timeout'] for call in run.call_args_list], [120, 10, 10, 10])

    def test_runtime_workflow_seeds_same_cache_before_model_start(self):
        workflow = yaml.safe_load((ROOT / '.github/workflows/verify-production-runtime.yml').read_text())
        job = workflow['jobs']['real-production-runtime']
        self.assertEqual(job['env']['PI_ALLOW_REMOTE_ASSET_DOWNLOADS'], '0')
        steps = job['steps']
        seed = next(i for i, step in enumerate(steps) if step.get('name') == 'Seed clean runtime cache twice without networking')
        start = next(i for i, step in enumerate(steps) if step.get('name') == 'Start and verify the pinned GGUF CPU runtime')
        self.assertLess(seed, start)
        self.assertIn('--network none', steps[seed]['run'])
        self.assertNotIn('--user ', steps[seed]['run'])
        self.assertIn('--entrypoint chown', steps[seed]['run'])
        self.assertIn('--cache "$PI_ASSET_CACHE"', steps[start]['run'])
        self.assertNotIn('HF_TOKEN', job['env'])

    def test_production_publication_waits_for_full_cross_platform_verification(self):
        for name, job in [('publish-oci-container.yml', 'production-and-deployment'),
                          ('verify-production-runtime.yml', 'real-production-runtime')]:
            workflow = yaml.safe_load((ROOT / '.github/workflows' / name).read_text())
            self.assertIn('full-regression', workflow['jobs'][job]['needs'])
            self.assertEqual(workflow['jobs']['full-regression']['uses'], './.github/workflows/verify.yml')


if __name__ == '__main__':
    unittest.main()
