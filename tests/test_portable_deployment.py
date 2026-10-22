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
        self.assertIn('PI_EMBEDDING_MODEL=qwen', production)
        self.assertIn('--license-review distribution/licenses/production-license-review.json', production)


    @unittest.skipUnless(shutil.which('docker') and shutil.which('bash'), 'Compose CLI unavailable')
    def test_model_device_matrix_preserves_cpu_and_selects_matching_gpu_model(self):
        for model in ('qwen', 'gemma', 'qwen-gguf', 'gemma-gguf'):
            for backend in ('cpu', 'vulkan', 'cuda'):
                with self.subTest(model=model, backend=backend):
                    env = {**os.environ, 'PI_EMBEDDING_MODEL':model, 'PI_ACCELERATOR':backend}
                    result = subprocess.run(['bash', str(BUNDLE/'compose.sh'), 'config', '--format', 'json'],
                                            env=env, capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    services = json.loads(result.stdout)['services']
                    app = services['production']['environment']
                    uses_gguf = backend != 'cpu' or model.endswith('-gguf')
                    expected = model.split('-')[0]+'-gguf' if uses_gguf else model
                    self.assertEqual(app['PI_EMBEDDING_MODEL'], expected)
                    self.assertEqual(app['PI_EMBEDDING_DEVICE'], backend)
                    if not uses_gguf:
                        self.assertNotIn('embeddings', services)
                        continue
                    runtime = services['embeddings']['environment']
                    self.assertEqual(runtime['LLAMA_ARG_DEVICE'], {'cpu':'none','cuda':'CUDA0','vulkan':'Vulkan0'}[backend])
                    self.assertEqual(runtime['LLAMA_ARG_N_GPU_LAYERS'], '0' if backend=='cpu' else '99')
                    if model.startswith('gemma'):
                        self.assertIn('mmproj-embeddinggemma-2', runtime['LLAMA_ARG_MMPROJ'])
                        self.assertEqual(runtime['LLAMA_ARG_POOLING'], 'mean')
                    else:
                        self.assertNotIn('LLAMA_ARG_MMPROJ', runtime)

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

    @unittest.skipUnless(shutil.which('bash'), 'bash unavailable')
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
        self.assertIn('bash ./compose.sh up -d --wait', run.stdout)
        self.assertIn('exec -T production python -m pi_platform.cli', run.stdout)
        self.assertNotIn('down -v', run.stdout)
        self.assertNotIn('harness.py', run.stdout)


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
