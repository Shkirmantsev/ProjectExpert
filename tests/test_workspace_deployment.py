"""Managed storage changes mounts only; launcher paths retain their topology."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'distribution/deployment'


class WorkspaceDeploymentTests(unittest.TestCase):
    def test_overlay_changes_only_production_mounts(self):
        overlay = yaml.safe_load((BUNDLE / 'compose.workspace-volume.yaml').read_text())
        self.assertEqual(set(overlay['services']), {'production'})
        self.assertEqual(set(overlay['services']['production']), {'volumes'})
        mounts = overlay['services']['production']['volumes']
        self.assertEqual(mounts[0]['target'], '/repo')
        self.assertTrue(mounts[0]['read_only'])
        self.assertFalse(mounts[1]['bind']['create_host_path'])
        self.assertEqual(mounts[2]['target'], '/repo/.project-intelligence-cache')

    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose CLI required (no daemon)')
    def test_real_compose_profile_matrix_preserves_topology(self):
        env = {**os.environ, 'PI_WORKSPACE_VOLUME': 'test-source', 'PI_RUNTIME_VOLUME': 'test-runtime',
               'PI_CANONICAL_HOST_DIR': str(ROOT / 'project-knowledge'),
               'PI_ASSET_IMAGE': 'ghcr.io/shkirmantsev/project-intelligence-assets@sha256:' + '1' * 64,
               'PI_ASSET_MANIFEST_SHA256': '2' * 64}
        profiles = [[], ['compose.accelerator.yaml', 'compose.cpu.yaml'],
                    ['compose.accelerator.yaml', 'compose.cuda.yaml'],
                    ['compose.accelerator.yaml', 'compose.vulkan.yaml'], ['compose.windows-gpu.yaml']]
        for profile in profiles:
            with self.subTest(profile=profile):
                args = ['docker', 'compose', '--env-file', str(BUNDLE / 'deployment.env'), '-f', str(BUNDLE / 'compose.yaml')]
                for name in profile:
                    args += ['-f', str(BUNDLE / name)]
                def render(extra):
                    result = subprocess.run(args + extra + ['config', '--format', 'json'], env=env,
                                            capture_output=True, text=True, timeout=30)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    return json.loads(result.stdout)
                ordinary = render([])
                managed = render(['-f', str(BUNDLE / 'compose.workspace-volume.yaml')])
                mounts = {v['target']: v for v in managed['services']['production'].pop('volumes')}
                original = {v['target']: v for v in ordinary['services']['production'].pop('volumes')}
                self.assertEqual(managed['services'], ordinary['services'])
                self.assertEqual(mounts['/models'], original['/models'])
                self.assertEqual(mounts['/repo']['type'], 'volume')
                self.assertTrue(mounts['/repo']['read_only'])
                # Compose serializers can omit false-valued fields. The source
                # overlay assertion above still requires an explicit false.
                self.assertFalse(mounts['/repo/project-knowledge'].get('bind', {}).get('create_host_path', False))
                self.assertFalse(mounts['/repo/project-knowledge'].get('read_only', False))
                self.assertFalse(mounts['/repo/.project-intelligence-cache'].get('read_only', False))

    @unittest.skipUnless(os.name == 'posix' and shutil.which('bash'),
                         'POSIX Bash helper fixture; Windows uses native launcher contract tests')
    def test_bash_managed_read_only_and_lifecycle_calls(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = Path(raw) / 'kit'; shutil.copytree(BUNDLE, kit)
            log = Path(raw) / 'calls'
            docker = Path(raw) / 'docker'
            docker.write_text('#!/bin/bash\nprintf "docker %s\\n" "$*" >> "$CALLS"\n')
            docker.chmod(0o755)
            helper = kit / 'workspace-agent-linux-amd64'
            helper.write_text('''#!/bin/bash
printf 'helper %s\\n' "$*" >> "$CALLS"
if [ "$1" = context ]; then echo local-test; fi
if [ "$1" = prepare ]; then
  printf 'PI_WORKSPACE_VOLUME=test-source\\nPI_RUNTIME_VOLUME=test-runtime\\nPI_CANONICAL_HOST_DIR=/canonical\\n' > workspace.env
fi
''')
            helper.chmod(0o755)
            with (kit / 'deployment.env').open('a') as stream:
                stream.write("\nPI_WORKSPACE_EXCLUDE='secret/**;build/**'\nPI_RUNTIME_BACKUP_INTERVAL_MINUTES=17\n")
            helper.write_text(helper.read_text().replace("printf 'helper", "[ \"$PI_WORKSPACE_EXCLUDE\" = 'secret/**;build/**' ] || exit 8\n[ \"$PI_RUNTIME_BACKUP_INTERVAL_MINUTES\" = 17 ] || exit 9\nprintf 'helper"))
            import hashlib
            (kit / 'workspace-agent-SHA256SUMS').write_text(hashlib.sha256(helper.read_bytes()).hexdigest() + '  ' + helper.name + '\n')
            env = {**os.environ, 'PATH': raw + os.pathsep + os.environ['PATH'], 'CALLS': str(log),
                   'PI_WORKSPACE_MODE': 'volume', 'PI_ACCELERATOR': 'cpu', 'PI_EMBEDDING_MODEL': 'gemma-torch',
                   'PI_TARGET_REPO': raw}
            def run(command):
                log.write_text('')
                result = subprocess.run(['bash', 'compose.sh', *command], cwd=kit, env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
                return log.read_text().splitlines()
            for command in ('config', 'ps', 'logs'):
                calls = run([command])
                self.assertEqual(len(calls), 2)
                self.assertTrue(calls[0].startswith("helper context "))
                self.assertIn("--context local-test compose", calls[1])
                self.assertIn('--env-file deployment.env', calls[1])
                self.assertIn('--env-file workspace.env -f compose.workspace-volume.yaml ' + command, calls[1])
            calls = run(['run', '--rm', 'production', 'health'])
            self.assertTrue(calls[0].startswith('helper prepare '))
            self.assertTrue(calls[1].startswith('helper sync '))
            self.assertEqual(len(calls), 4)
            calls = run(['down'])
            self.assertTrue(calls[0].startswith('helper backup '))
            self.assertTrue(calls[1].startswith('helper stop '))
            self.assertIn('compose.accelerator.yaml', calls[-1])
            helper.write_text('tampered')
            result = subprocess.run(['bash', 'compose.sh', 'run', 'production', 'health'], cwd=kit, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('checksum mismatch', result.stderr)

    def test_release_build_and_export_include_helpers(self):
        source = (ROOT / 'Containerfile').read_text()
        self.assertIn('ARG GO_VERSION=1.27.4', source)
        self.assertIn('GO_SHA256=7226736c', source)
        self.assertIn('COPY --from=workspace-agent-build /out/ /bundle/', source)
        spec = importlib.util.spec_from_file_location('workspace_export', BUNDLE / 'export.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as raw:
            src = Path(raw) / 'source'; shutil.copytree(BUNDLE, src)
            for name in ('assets-lock.json', 'asset-release.json'):
                shutil.copy2(ROOT / 'distribution/assets' / name, src / name)
            for name in module.HELPERS:
                (src / name).write_bytes(b'built helper')
            dest = Path(raw) / 'kit'
            module.export(src, dest)
            (dest / 'deployment.env').write_text('operator-owned')
            (dest / 'workspace.env').write_text('persistent-local-state')
            (src / module.HELPERS[0]).write_bytes(b'updated helper')
            module.export(src, dest, upgrade=True)
            self.assertEqual((dest / module.HELPERS[0]).read_bytes(), b'updated helper')
            self.assertEqual((dest / 'deployment.env').read_text(), 'operator-owned')
            self.assertEqual((dest / 'workspace.env').read_text(), 'persistent-local-state')
            self.assertEqual(next((dest / '.kit-backups').glob('*/' + module.HELPERS[0])).read_bytes(), b'built helper')
