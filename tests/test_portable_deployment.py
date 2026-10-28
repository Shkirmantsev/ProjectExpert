"""Behavioral checks for the standalone deployment kit and exact release review."""
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
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


def _kit_copy(root: Path) -> Path:
    kit = Path(root) / 'kit'
    shutil.copytree(BUNDLE, kit)
    return kit


def _fake_docker(directory: Path, exit_code: int = 0) -> Path:
    """A Docker stand-in that records every invocation."""

    if os.name == 'nt':
        binary = directory / 'docker.cmd'
        script = '@echo off\n>>"%CALLS%" echo %*\nexit /b ' + str(exit_code) + '\n'
    else:
        binary = directory / 'docker'
        script = '#!/bin/sh\nprintf "%s\\n" "$*" >> "$CALLS"\nexit ' + str(exit_code) + '\n'
    binary.write_text(script)
    binary.chmod(0o755)
    return binary


class DeploymentHelpTests(unittest.TestCase):
    """`make` and `make help` are read-only command lists."""

    def _snapshot(self, kit: Path) -> dict:
        state = {}
        for path in sorted(kit.rglob('*')):
            rel = path.relative_to(kit).as_posix()
            if path.is_dir():
                state[rel] = 'dir'
            elif path.is_file():
                state[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return state

    @unittest.skipUnless(shutil.which('make'), 'make unavailable')
    def test_bare_make_is_read_only_without_docker_python_or_env_file(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = _kit_copy(raw)
            (kit / 'deployment.env').unlink()
            calls = Path(raw) / 'calls'
            _fake_docker(Path(raw), exit_code=99)
            env = {**os.environ,
                   'PATH': str(Path(raw)) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(calls)}
            before = self._snapshot(kit)
            bare = subprocess.run(['make'], cwd=kit, env=env, capture_output=True, text=True)
            explicit = subprocess.run(['make', 'help'], cwd=kit, env=env, capture_output=True, text=True)
            self.assertEqual(bare.returncode, 0, bare.stderr)
            self.assertEqual(explicit.returncode, 0, explicit.stderr)
            self.assertEqual(bare.stdout, explicit.stdout)
            self.assertFalse(calls.exists(), 'help must not invoke Docker')
            self.assertEqual(before, self._snapshot(kit), 'help must not mutate the kit')

    @unittest.skipUnless(shutil.which('make'), 'make unavailable')
    def test_help_describes_every_public_target(self):
        text = (BUNDLE / 'Makefile').read_text()
        phony = re.search(r'^\.PHONY:[ \t]*(.*)$', text, re.M).group(1).split()
        self.assertIn('help', phony)
        run = subprocess.run(['make', 'help'], cwd=BUNDLE, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        listed = set(re.findall(r'(?m)^\s+make\s+([A-Za-z0-9][A-Za-z0-9_.-]*)\s+\S', run.stdout))
        for target in phony:
            self.assertIn(target, listed, f'{target} is not described in the help output')
        self.assertEqual(listed, set(phony), 'the help output lists a target that is not public')

    def test_the_kit_default_goal_is_help_not_startup(self):
        text = (BUNDLE / 'Makefile').read_text()
        self.assertIn('.DEFAULT_GOAL := help', text)
        self.assertNotIn('.DEFAULT_GOAL := platform-start', text)

    def test_the_exported_kit_ships_the_help_first_makefile(self):
        spec = importlib.util.spec_from_file_location('kit_export', BUNDLE / 'export.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as raw:
            dest = Path(raw) / 'kit'
            module.export(BUNDLE, dest)
            makefile = (dest / 'Makefile').read_text()
            self.assertIn('.DEFAULT_GOAL := help', makefile)
            self.assertRegex(makefile, r'(?m)^help:')
            self.assertTrue((dest / 'url.sh').is_file())
            self.assertTrue((dest / 'url.ps1').is_file())
            self.assertEqual(set(module.FILES), {p.name for p in dest.iterdir()})

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Bash launcher required')
    def test_startup_reports_the_port_configured_in_the_env_file(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = _kit_copy(raw)
            (kit / 'deployment.env').write_text('PI_CONTROL_PORT=9123\n')
            calls = Path(raw) / 'calls'
            _fake_docker(Path(raw))
            env = {**os.environ,
                   'PATH': str(Path(raw)) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(calls), 'PI_OPEN_BROWSER': '0'}
            run = subprocess.run(['bash', str(kit / 'start.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('Ready: http://localhost:9123', run.stdout)

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Bash launcher required')
    def test_the_shell_environment_overrides_the_env_file_port(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = _kit_copy(raw)
            (kit / 'deployment.env').write_text('PI_CONTROL_PORT=9123\n')
            calls = Path(raw) / 'calls'
            _fake_docker(Path(raw))
            env = {**os.environ,
                   'PATH': str(Path(raw)) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(calls), 'PI_OPEN_BROWSER': '0', 'PI_CONTROL_PORT': '9331'}
            run = subprocess.run(['bash', str(kit / 'start.sh')], env=env, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn('Ready: http://localhost:9331', run.stdout)
            self.assertNotIn('9123', run.stdout)

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Bash launcher required')
    def test_a_failed_readiness_never_reports_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = _kit_copy(raw)
            calls = Path(raw) / 'calls'
            _fake_docker(Path(raw), exit_code=7)
            env = {**os.environ,
                   'PATH': str(Path(raw)) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(calls), 'PI_OPEN_BROWSER': '0'}
            run = subprocess.run(['bash', str(kit / 'start.sh')], env=env, capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertNotIn('Ready:', run.stdout)

    @unittest.skipUnless(shutil.which('make'), 'make unavailable')
    def test_a_failed_make_start_never_reports_ready(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = _kit_copy(raw)
            calls = Path(raw) / 'calls'
            # This contract belongs to Make: a failed Compose command must
            # prevent the subsequent URL/Ready command. Launcher behavior has
            # separate coverage; do not start PowerShell or probe GPUs here.
            compose = Path(raw) / 'failing compose.py'
            compose.write_text(
                'import pathlib, sys\n'
                f'pathlib.Path({str(calls)!r}).write_text(" ".join(sys.argv[1:]))\n'
                'sys.exit(7)\n'
            )
            command = f'COMPOSE="{sys.executable}" "{compose}"'
            run = subprocess.run(['make', 'platform-start', command], cwd=kit,
                                 capture_output=True, text=True, timeout=30)
            self.assertNotEqual(run.returncode, 0)
            self.assertNotIn('Ready:', run.stdout)
            self.assertIn('up -d --wait', calls.read_text())


class DeploymentTopologyTests(unittest.TestCase):
    """Helper invocations must use the complete applicable service topology."""

    @unittest.skipUnless(os.name != 'nt' and shutil.which('bash'), 'Bash launcher required')
    def test_every_launcher_compose_call_carries_the_sidecar_topology(self):
        with tempfile.TemporaryDirectory() as raw:
            kit = _kit_copy(raw)
            calls = Path(raw) / 'calls'
            _fake_docker(Path(raw))
            env = {**os.environ,
                   'PATH': str(Path(raw)) + os.pathsep + os.environ['PATH'],
                   'CALLS': str(calls)}
            subprocess.run(['bash', str(kit / 'compose.sh'), 'up', '-d'], env=env,
                           capture_output=True, text=True)
            recorded = calls.read_text().splitlines()
            self.assertTrue(recorded)
            for call in recorded:
                if '-f compose.yaml' in call:
                    self.assertIn('-f compose.accelerator.yaml', call,
                                  f'incomplete Compose topology: {call}')

    def test_no_launcher_deletes_orphans_automatically(self):
        for name in ('compose.sh', 'compose.ps1', 'stop.ps1'):
            content = (BUNDLE / name).read_text()
            self.assertNotIn('--remove-orphans', content,
                             f'{name} must not delete containers automatically')

    def test_the_windows_launcher_uses_the_same_complete_topology(self):
        script = (BUNDLE / 'compose.ps1').read_text()
        # Join the continued lines (backslash and PowerShell backtick) so one
        # Compose call is one record.
        joined = re.sub(r'(`|\\)\r?\n\s*', ' ', script)
        for call in re.findall(r'docker compose[^\n]*', joined):
            if '-f compose.yaml' in call:
                self.assertIn('compose.accelerator.yaml', call, call)
        self.assertIn('-f compose.accelerator.yaml -f compose.cpu.yaml', script)


@unittest.skipUnless(os.name != 'nt' and shutil.which('docker'), 'Docker Compose required')
class DeploymentTopologyAcceptanceTests(unittest.TestCase):
    """Real Compose acceptance for the repeated-start and orphan contract."""

    BASE = """\
name: {project}
services:
  production:
    image: alpine:latest
    command: ["sleep", "600"]
    healthcheck:
      test: ["CMD", "true"]
      interval: 1s
      timeout: 1s
      retries: 5
"""
    ACCELERATOR = """\
services:
  production:
    depends_on:
      model-setup:
        condition: service_completed_successfully
      embeddings:
        condition: service_healthy
  model-setup:
    image: alpine:latest
    command: ["sh", "-c", "echo setup done"]
    restart: "no"
  embeddings:
    image: alpine:latest
    command: ["sleep", "600"]
    healthcheck:
      test: ["CMD", "true"]
      interval: 1s
      timeout: 1s
      retries: 5
"""
    CPU = """\
services:
  production:
    environment:
      PI_EMBEDDING_DEVICE: cpu
"""

    def setUp(self):
        self.project = 'pi-topology-acceptance'
        inspect = subprocess.run(['docker', 'image', 'inspect', 'alpine:latest'],
                                 capture_output=True, text=True)
        if inspect.returncode != 0:
            pull = subprocess.run(['docker', 'pull', 'alpine:latest'], capture_output=True, text=True)
            if pull.returncode != 0:
                self.skipTest('alpine:latest is not available on this host')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'compose.yaml').write_text(self.BASE.format(project=self.project))
        (self.root / 'compose.accelerator.yaml').write_text(self.ACCELERATOR)
        (self.root / 'compose.cpu.yaml').write_text(self.CPU)
        self.addCleanup(self._cleanup)

    def _cleanup(self):
        subprocess.run(['docker', 'compose', '-p', self.project, '-f',
                        str(self.root / 'compose.yaml'), '-f',
                        str(self.root / 'compose.accelerator.yaml'), 'down', '--remove-orphans'],
                       capture_output=True, text=True)
        subprocess.run(['docker', 'rm', '-f', f'{self.project}-unrelated-1'],
                       capture_output=True, text=True)

    def _compose(self, *files, command=None):
        argv = ['docker', 'compose', '-p', self.project]
        for name in files:
            argv += ['-f', str(self.root / name)]
        argv += command or []
        return subprocess.run(argv, capture_output=True, text=True, cwd=self.root)

    def _containers(self):
        listed = subprocess.run(
            ['docker', 'ps', '-a', '--filter', f'label=com.docker.compose.project={self.project}',
             '--format', '{{.Names}}\t{{.Status}}'], capture_output=True, text=True)
        return {line.split('\t')[0]: line.split('\t')[1] for line in listed.stdout.splitlines() if line}

    def test_a_reduced_helper_topology_is_what_reports_the_sidecars_as_orphans(self):
        """This is the reproduced root cause of the repeated-start warning."""

        up = self._compose('compose.yaml', 'compose.accelerator.yaml', 'compose.cpu.yaml',
                           command=['up', '-d', '--wait', '--wait-timeout', '120'])
        self.assertEqual(up.returncode, 0, up.stderr)
        reduced = self._compose('compose.yaml',
                                command=['run', '--rm', '--no-deps', 'production', 'true'])
        self.assertIn('orphan', reduced.stderr.lower(),
                      'the reduced topology must reproduce the orphan warning')
        complete = self._compose('compose.yaml', 'compose.accelerator.yaml', 'compose.cpu.yaml',
                                 command=['run', '--rm', '--no-deps', 'production', 'true'])
        self.assertNotIn('orphan', complete.stderr.lower(),
                         'the complete topology must not report the sidecars as orphans')

    def test_repeated_start_keeps_the_sidecars_and_reports_no_false_orphans(self):
        first = self._compose('compose.yaml', 'compose.accelerator.yaml', 'compose.cpu.yaml',
                              command=['up', '-d', '--wait', '--wait-timeout', '120'])
        self.assertEqual(first.returncode, 0, first.stderr)
        before = self._containers()
        self.assertIn(f'{self.project}-production-1', before)
        self.assertIn(f'{self.project}-embeddings-1', before)
        second = self._compose('compose.yaml', 'compose.accelerator.yaml', 'compose.cpu.yaml',
                               command=['up', '-d', '--wait', '--wait-timeout', '120'])
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertNotIn('orphan', second.stderr.lower())
        after = self._containers()
        self.assertEqual(set(before), set(after), 'the repeated start changed the service set')
        self.assertIn('Exited (0)', after[f'{self.project}-model-setup-1'])

    def test_a_genuine_unrelated_service_is_never_removed(self):
        up = self._compose('compose.yaml', 'compose.accelerator.yaml', 'compose.cpu.yaml',
                           command=['up', '-d', '--wait', '--wait-timeout', '120'])
        self.assertEqual(up.returncode, 0, up.stderr)
        unrelated = subprocess.run(
            ['docker', 'run', '-d', '--name', f'{self.project}-unrelated-1',
             '--label', f'com.docker.compose.project={self.project}',
             '--label', 'com.docker.compose.service=unrelated',
             'alpine:latest', 'sleep', '600'], capture_output=True, text=True)
        self.assertEqual(unrelated.returncode, 0, unrelated.stderr)
        down = self._compose('compose.yaml', 'compose.accelerator.yaml',
                             command=['down'])
        self.assertEqual(down.returncode, 0, down.stderr)
        remaining = self._containers()
        self.assertIn(f'{self.project}-unrelated-1', remaining,
                      'an unrelated container must survive the shutdown')
        self.assertNotIn(f'{self.project}-production-1', remaining)

    def test_the_completed_model_setup_is_not_a_readiness_failure(self):
        up = self._compose('compose.yaml', 'compose.accelerator.yaml', 'compose.cpu.yaml',
                           command=['up', '-d', '--wait', '--wait-timeout', '120'])
        self.assertEqual(up.returncode, 0, up.stderr)
        containers = self._containers()
        self.assertIn('Exited (0)', containers[f'{self.project}-model-setup-1'])
        self.assertIn('healthy', containers[f'{self.project}-production-1'])


if __name__ == '__main__':
    unittest.main()
