"""Behavioral checks for the standalone deployment kit and exact release review."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.core.licensing.scoped_review import load_scoped_review, ScopedReviewPolicy
from pi_platform.core.licensing import LicenseGate
from pi_platform.core.licensing.sbom import emit_notice_file
from pi_platform.ports import Dependency

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / 'distribution/deployment'


class DeploymentTests(unittest.TestCase):
    def test_container_defaults_keep_core_model_free_and_trust_only_repo(self):
        content = (ROOT / 'Containerfile').read_text()
        core, production = content.split('FROM core AS production', 1)
        self.assertIn('git config --system --add safe.directory /repo', core)
        self.assertNotIn('safe.directory *', core)
        self.assertIn('PI_EMBEDDING_MODEL=hashing', core)
        self.assertIn('PI_EMBEDDING_MODEL=gemma', production)
        self.assertIn('--license-review distribution/licenses/production-license-review.json', production)


    def test_only_one_production_embedding_model_is_shipped(self):
        """The retired alternative model must be gone from the kit."""

        lock = json.loads((BUNDLE / 'accelerator-lock.json').read_text())
        self.assertEqual(set(lock['models']), {'gemma'})
        record = lock['models']['gemma']
        self.assertEqual(record['quantization'], 'Q8_0')
        self.assertEqual(record['pooling'], 'mean')
        self.assertIn('embeddinggemma-2-Q8_0.gguf', record['model_filename'])
        self.assertIn('mmproj-embeddinggemma-2-Q8_0.gguf', record['projector_filename'])
        for name in ('compose.yaml', 'compose.accelerator.yaml', 'deployment.env'):
            content = (BUNDLE / name).read_text()
            self.assertNotIn('qwen', content.lower(), f'{name} still references the retired model')
        env = (BUNDLE / 'deployment.env').read_text()
        self.assertIn('PI_EMBEDDING_MODEL=gemma', env)
        self.assertIn('PI_ACCELERATOR=auto', env)

    def test_runtime_flags_are_explicit_and_not_environment_variables(self):
        """llama.cpp's LLAMA_ARG_* names differ from its flag names, so the
        deployment must pass an explicit argument vector instead."""

        content = (BUNDLE / 'compose.accelerator.yaml').read_text()
        self.assertNotIn('LLAMA_ARG_BATCH_SIZE', content)
        self.assertNotIn('LLAMA_ARG_UBATCH_SIZE', content)
        self.assertNotIn('LLAMA_ARG_N_GPU_LAYERS', content)
        command = content.split('  embeddings:', 1)[1]
        self.assertIn('--embeddings', command)
        self.assertIn('--mmproj', command)
        self.assertIn('--pooling', command)
        # The projector must be off the GPU exactly once in the argument vector.
        self.assertEqual(command.count('- --no-mmproj-offload'), 1)

    def test_the_launcher_measures_the_candidates_before_deciding(self):
        """The GPU is an optimisation: it is selected only when it is
        measurably faster than the CPU baseline."""

        script = (BUNDLE / 'compose.sh').read_text()
        self.assertIn('inference benchmark', script)
        self.assertIn('inference plan', script)
        self.assertIn('measurements', script)

    def test_the_launcher_never_uses_the_environment_variables_for_the_flags(self):
        script = (BUNDLE / 'compose.sh').read_text()
        for wrong in ('LLAMA_ARG_BATCH_SIZE', 'LLAMA_ARG_UBATCH_SIZE',
                      'LLAMA_ARG_N_GPU_LAYERS'):
            self.assertNotIn(wrong, script)

    @unittest.skipUnless(os.name != 'nt' and shutil.which('docker') and shutil.which('bash'), 'Linux Compose matrix; Windows has native launcher contract tests')
    def test_model_device_matrix_preserves_cpu_and_selects_matching_gpu_model(self):
        for model in ('gemma', 'gemma-torch'):
            for backend in ('cpu', 'vulkan', 'cuda'):
                with self.subTest(model=model, backend=backend):
                    env = {**os.environ, 'PI_EMBEDDING_MODEL':model, 'PI_ACCELERATOR':backend}
                    result = subprocess.run(['bash', str(BUNDLE/'compose.sh'), 'config', '--format', 'json'],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)['services']
                    app = services['production']['environment']
                    self.assertEqual(app['PI_EMBEDDING_MODEL'], model)
                    if model == 'gemma-torch':
                        # The native binding runs no llama.cpp sidecar.
                        self.assertNotIn('embeddings', services)
                        continue
                    self.assertEqual(app['PI_EMBEDDING_DEVICE'], backend)
                    command = services['embeddings']['command']
                    self.assertIn('--mmproj', command)
                    self.assertIn('/models/mmproj-embeddinggemma-2-Q8_0.gguf', command)
                    self.assertIn('mean', command)
                    if backend == 'cpu':
                        self.assertEqual(services['embeddings']['entrypoint'],
                                         ['/app/llama-server', '--device', 'none'])
                    else:
                        self.assertIn('--fit', command)
                        self.assertIn('on', command)
                        self.assertIn('--fit-target', command)

    def test_export_preserves_existing_configuration_and_symlinks(self):
        spec = importlib.util.spec_from_file_location('kit_export', BUNDLE / 'export.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / 'kit'
            module.export(BUNDLE, dest)
            self.assertEqual(set(module.FILES), {p.name for p in dest.iterdir()})
            (dest / 'deployment.env').write_text('PI_CONTROL_PORT=9123\n')
            outside = Path(raw) / 'outside'
            outside.write_text('preserved')
            (dest / 'Makefile').unlink()
            (dest / 'Makefile').symlink_to(outside)
            module.export(BUNDLE, dest)
            self.assertEqual((dest / 'deployment.env').read_text(), 'PI_CONTROL_PORT=9123\n')
            self.assertEqual(outside.read_text(), 'preserved')

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Linux launcher; Windows has native launcher contract tests')
    def test_linux_launcher_reports_failure_and_waits_for_readiness(self):
        with tempfile.TemporaryDirectory() as raw:
            temp = Path(raw)
            shutil.copytree(BUNDLE, temp / 'kit')
            binary = temp / 'docker'
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
                              'case "$*" in *"up -d"*) exit "${START_EXIT:-0}";; esac\n')
            binary.chmod(0o755)
            env = {**os.environ, 'PATH': str(temp)+os.pathsep+os.environ['PATH'],
                   'CALLS': str(temp / 'calls'), 'PI_OPEN_BROWSER': '0'}
            run = subprocess.run(['bash', str(temp / 'kit/start.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('Ready:', run.stdout)
            self.assertIn('--wait --wait-timeout 1800', (temp / 'calls').read_text())
            run = subprocess.run(['bash', str(temp / 'kit/start.sh')], env={**env, 'START_EXIT': '7'}, capture_output=True, text=True)
            self.assertEqual(run.returncode, 7)
            self.assertNotIn('Ready:', run.stdout)

    @unittest.skipUnless(shutil.which('make'), 'make unavailable')
    def test_make_commands_are_container_only_and_keep_volumes(self):
        run = subprocess.run(['make', '-n', '-C', str(BUNDLE), 'platform-start', 'platform-stop',
                              'platform-models', 'eval-retrieval'], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        launcher = 'powershell -NoProfile -File ./compose.ps1' if os.name == 'nt' else 'bash ./compose.sh'
        self.assertIn(launcher + ' up -d --wait', run.stdout)
        self.assertIn('exec -T production python -m pi_platform.cli', run.stdout)
        self.assertNotIn('down -v', run.stdout)
        self.assertNotIn('harness.py', run.stdout)

    @unittest.skipUnless(os.name != 'nt' and shutil.which('docker'), 'Linux Compose config required')
    def test_default_is_gemma_and_explicit_integrated_device_is_preserved(self):
        env = {key: value for key, value in os.environ.items() if not key.startswith('PI_')}
        result = subprocess.run(['bash', str(BUNDLE/'compose.sh'), 'config', '--format', 'json'], env=env, capture_output=True, text=True, check=True)
        services = json.loads(result.stdout)['services']
        self.assertEqual(services['production']['environment']['PI_EMBEDDING_MODEL'], 'gemma')
        command = services['embeddings']['command']
        self.assertIn('/models/embeddinggemma-2-Q8_0.gguf', command)
        self.assertIn('/models/mmproj-embeddinggemma-2-Q8_0.gguf', command)
        env.update(PI_ACCELERATOR='vulkan', PI_GPU_DEVICE='Vulkan1')
        result = subprocess.run(['bash', str(BUNDLE/'compose.sh'), 'config', '--format', 'json'], env=env, capture_output=True, text=True, check=True)
        self.assertIn('Vulkan1', json.loads(result.stdout)['services']['embeddings']['command'])

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Bash launcher required')
    def test_unavailable_gpu_degrades_to_cpu_instead_of_failing(self):
        """An unusable GPU is a downgrade, never a startup failure."""

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            shutil.copytree(BUNDLE, root/'kit')
            docker = root/'docker'
            # The fake docker reports a device that is not the requested one
            # and never returns a usable plan.
            docker.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\n'
                              'case "$*" in *--list-devices*) echo "Available devices:"; echo "  CUDA1: test GPU";; esac\n')
            docker.chmod(0o755)
            env = {**os.environ, 'PATH':str(root)+os.pathsep+os.environ['PATH'], 'CALLS':str(root/'calls'), 'PI_ACCELERATOR':'cuda'}
            result = subprocess.run(['bash',str(root/'kit/compose.sh'),'up','-d'],env=env,capture_output=True,text=True)
            calls = (root/'calls').read_text()
            self.assertIn('--list-devices', calls)
            # The deployment must not abort: it falls back to the CPU profile.
            self.assertNotIn('Selected device', result.stderr)
            self.assertIn('cpu', calls)

    def test_windows_gpu_probes_before_download_and_tracks_device(self):
        script = (BUNDLE/'setup-windows-accelerator.ps1').read_text()
        self.assertLess(script.index("'--list-devices'"), script.index('Get-VerifiedFile $modelSpec.model_url'))
        self.assertIn("'device.txt'", script)
        self.assertIn("'backend.txt'", script)
        # The Windows launcher must apply the shared Python decision.
        self.assertIn('pi_platform.cli', script)
        self.assertIn('inference', script)
        self.assertIn('plan', script)
        # The runtime flags must not come from LLAMA_ARG_* variables.
        self.assertNotIn('LLAMA_ARG_BATCH', script)


class ScopedReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inventory = self.root / 'inventory.json'
        self.lock = self.root / 'lock.txt'
        self.evidence = self.root / 'evidence.json'
        self.review = self.root / 'review.json'
        self.dep = Dependency(name='reviewed', version='1', spdx='MPL-2.0')
        self.inventory.write_text(json.dumps({'dependencies':[{'name':'reviewed','version':'1','spdx':'MPL-2.0'}]}))
        self.lock.write_text('reviewed==1\n')
        self.evidence.write_text('{}')
        self.record = {'status':'approved','accepted_by':'test operator','accepted_at':'2026-10-22',
                       'coordinates':[{'name':'reviewed','version':'1','license_expression':'MPL-2.0',
                                       'decision':'accepted','obligations':'retain notices'}]}
        for field, path in [('inventory_sha256',self.inventory),('lock_sha256',self.lock),('evidence_sha256',self.evidence)]:
            self.record[field] = hashlib.sha256(path.read_bytes()).hexdigest()

    def load(self):
        self.review.write_text(json.dumps(self.record))
        return load_scoped_review(self.review,inventory=self.inventory,lock=self.lock,evidence=self.evidence)

    def test_exact_acceptance_and_notice_without_global_expansion(self):
        policy = ScopedReviewPolicy(self.load())
        self.assertTrue(LicenseGate(policy).run([self.dep])[0])
        self.assertFalse(LicenseGate().run([self.dep])[0])
        self.assertFalse(LicenseGate(policy).run([Dependency(name='reviewed',version='2',spdx='MPL-2.0')])[0])
        path = emit_notice_file([self.dep], output_root=self.root, policy=policy)
        self.assertIn('reviewed:1 - SPDX:MPL-2.0', path.read_text())

    def test_unapproved_or_stale_records_fail(self):
        self.record['status'] = 'proposed-unapproved'
        with self.assertRaises(ValueError): self.load()
        self.record['status'] = 'approved'
        for file in (self.lock,self.inventory,self.evidence):
            old = file.read_bytes()
            file.write_bytes(old+b' ')
            with self.assertRaisesRegex(ValueError,'stale'): self.load()
            file.write_bytes(old)

    def test_pending_unknown_duplicate_and_unattributed_acceptance_fail(self):
        self.record['coordinates'][0]['decision'] = 'pending'
        with self.assertRaises(ValueError): self.load()
        self.record['coordinates'][0]['decision'] = 'accepted'
        self.record['coordinates'].append(self.record['coordinates'][0].copy())
        with self.assertRaises(ValueError): self.load()
        self.record['coordinates'].pop()
        self.record['accepted_by'] = ''
        with self.assertRaises(ValueError): self.load()


if __name__ == '__main__':
    unittest.main()
