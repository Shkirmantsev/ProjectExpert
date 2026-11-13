"""Automatic merge bootstrap retains registry, review and offline integrity gates."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

from pi_platform.deployment.asset_pack import AssetPackError
from pi_platform.deployment.offline_assets import bind_published_release, release_identity
from scripts.prepare_ci_assets import ASSET_REPOSITORY, ensure_published, published_values

ROOT = Path(__file__).resolve().parents[1]


class AutomaticAssetTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / 'distribution/assets', self.root / 'distribution/assets')
        shutil.copyfile(ROOT / 'requirements-production-linux-x86_64.txt', self.root / 'requirements-production-linux-x86_64.txt')
        self.release = self.root / 'distribution/assets/asset-release.json'
        self.release.write_text(json.dumps({'release_status': 'blocked', 'image': None}))
        self.original = self.release.read_bytes()
        self.directory = self.root / 'tmp/local/ci-assets'
        self.digest = hashlib.sha256((self.root / 'distribution/assets/assets-lock.json').read_bytes()).hexdigest()
        self.image = ASSET_REPOSITORY + '@sha256:' + 'a' * 64
        self.tag = ASSET_REPOSITORY + ':manifest-' + self.digest

    def result(self, command, code=0, stderr=''):
        return subprocess.CompletedProcess(command, code, '', stderr)

    def test_matching_registry_pack_is_reused_without_upstream_or_source_edits(self):
        with patch('scripts.prepare_ci_assets.prepare') as build, patch(
            'scripts.prepare_ci_assets.subprocess.run', side_effect=lambda c, **kw: self.result(c)) as run, patch(
            'scripts.prepare_ci_assets.subprocess.check_output', return_value=json.dumps([self.image])):
            values = ensure_published(self.root, self.directory)
        build.assert_not_called()
        self.assertEqual(values['PI_ASSET_IMAGE'], self.image)
        self.assertEqual(release_identity(Path(values['PI_ASSET_RELEASE_FILE']))['manifest_sha256'], self.digest)
        self.assertEqual(self.release.read_bytes(), self.original)
        self.assertEqual(run.call_args_list[0].args[0], ['docker', 'pull', self.tag])
        verification = next(call.args[0] for call in run.call_args_list if call.args[0][:2] == ['docker', 'run'])
        self.assertIn('none', verification)
        self.assertIn('PYTHONPATH=/opt/current-verifier', verification)

    def test_missing_pack_is_built_once_published_and_pinned_by_registry_digest(self):
        def execute(command, **kw):
            return self.result(command, 1, 'manifest unknown') if command == ['docker', 'pull', self.tag] else self.result(command)
        with patch('scripts.prepare_ci_assets.prepare', return_value={'PI_ASSET_IMAGE': 'sha256:' + 'b' * 64}) as build, patch(
            'scripts.prepare_ci_assets.subprocess.run', side_effect=execute) as run, patch(
            'scripts.prepare_ci_assets.subprocess.check_output', return_value=json.dumps([self.image])):
            values = ensure_published(self.root, self.directory)
        build.assert_called_once_with(self.root, candidate=True)
        self.assertIn(['docker', 'push', self.tag], [call.args[0] for call in run.call_args_list])
        self.assertEqual(values['PI_ASSET_IMAGE'], self.image)
        self.assertEqual(self.release.read_bytes(), self.original)

    def test_mismatched_payload_is_rebuilt_but_failed_replacement_is_never_activated(self):
        for replacement_ok in (True, False):
            with self.subTest(replacement_ok=replacement_ok):
                verification_count = 0
                def execute(command, **kw):
                    nonlocal verification_count
                    if command[:2] == ['docker', 'run']:
                        verification_count += 1
                        return self.result(command, 0 if verification_count > 1 and replacement_ok else 42)
                    return self.result(command)
                directory = self.directory / str(replacement_ok)
                with patch('scripts.prepare_ci_assets.prepare', return_value={'PI_ASSET_IMAGE': 'sha256:' + 'b' * 64}) as build, patch(
                    'scripts.prepare_ci_assets.subprocess.run', side_effect=execute), patch(
                    'scripts.prepare_ci_assets.subprocess.check_output', return_value=json.dumps([self.image])):
                    if replacement_ok:
                        self.assertEqual(ensure_published(self.root, directory)['PI_ASSET_IMAGE'], self.image)
                    else:
                        with self.assertRaisesRegex(AssetPackError, 'payload verification'):
                            ensure_published(self.root, directory)
                        self.assertFalse((directory / 'asset-release.json').exists())
                build.assert_called_once()

    def test_auth_tls_network_and_daemon_failures_do_not_trigger_upstream_downloads(self):
        for error in ('403 forbidden: not found', 'unauthorized', 'x509 certificate error', 'i/o timeout',
                      'Cannot connect to Docker daemon', 'credential helper executable not found', '503 manifest unknown'):
            with self.subTest(error=error), patch('scripts.prepare_ci_assets.prepare') as build, patch(
                'scripts.prepare_ci_assets.subprocess.run', return_value=self.result([], 1, error)):
                with self.assertRaisesRegex(AssetPackError, 'No upstream assembly attempted'):
                    ensure_published(self.root, self.directory)
                build.assert_not_called()

    def test_verifier_infrastructure_failure_does_not_trigger_rebuild(self):
        def execute(command, **kw):
            return self.result(command, 125 if command[:2] == ['docker', 'run'] else 0)
        with patch('scripts.prepare_ci_assets.prepare') as build, patch(
            'scripts.prepare_ci_assets.subprocess.run', side_effect=execute), patch(
            'scripts.prepare_ci_assets.subprocess.check_output', return_value=json.dumps([self.image])):
            with self.assertRaisesRegex(AssetPackError, 'verifier could not run'):
                ensure_published(self.root, self.directory)
        build.assert_not_called()

    def test_unreviewed_manifest_fails_before_registry_access(self):
        manifest = self.root / 'distribution/assets/assets-lock.json'
        data = json.loads(manifest.read_text()); data['release_status'] = 'blocked'
        manifest.write_text(json.dumps(data))
        with patch('scripts.prepare_ci_assets.subprocess.run') as run:
            with self.assertRaisesRegex(AssetPackError, 'blocked'):
                ensure_published(self.root, self.directory)
        run.assert_not_called()

    def test_generated_kit_binding_preserves_matching_app_identity_and_rejects_fake_pins(self):
        metadata = {'release_status': 'blocked', 'image': None, 'application_image': 'app@sha256:' + 'c' * 64, 'kit_revision': 'revision'}
        self.release.write_text(json.dumps(metadata))
        before = self.release.read_bytes()
        for image, digest in ((self.tag, self.digest), ('sha256:' + 'a' * 64, self.digest), (self.image, '0' * 64)):
            with self.assertRaises(AssetPackError):
                bind_published_release(self.release, image, digest)
            self.assertEqual(self.release.read_bytes(), before)
        bind_published_release(self.release, self.image, self.digest)
        bound = release_identity(self.release)
        self.assertEqual(bound['application_image'], metadata['application_image'])
        self.assertEqual(bound['kit_revision'], 'revision')

    def test_caller_cannot_use_a_mutable_image_as_published_output(self):
        with patch('scripts.prepare_ci_assets.subprocess.run') as run:
            with self.assertRaisesRegex(AssetPackError, 'immutable published'):
                published_values(self.root, self.tag, self.digest, self.directory)
        run.assert_not_called()


class AutomaticWorkflowTests(unittest.TestCase):
    def test_merge_jobs_resolve_assets_and_propagate_real_identity_without_manual_hash_input(self):
        workflows = ROOT / '.github/workflows'
        reusable = yaml.safe_load((workflows / 'publish-offline-assets.yml').read_text())
        events = reusable.get('on', reusable.get(True))
        self.assertIn('workflow_call', events)
        self.assertIsNone(events['workflow_dispatch'])
        resolver = reusable['jobs']['resolve-assets']
        self.assertIn("github.event_name != 'pull_request'", resolver['if'])
        self.assertFalse(resolver['concurrency']['cancel-in-progress'])
        steps = '\n'.join(step.get('run', '') for step in resolver['steps'])
        self.assertIn('--ensure-published', steps)
        for name, consumer in [('publish-oci-container.yml', 'production-and-deployment'), ('verify-production-runtime.yml', 'real-production-runtime')]:
            data = yaml.safe_load((workflows / name).read_text())
            asset_job = data['jobs']['published-assets']
            self.assertEqual(asset_job['uses'], './.github/workflows/publish-offline-assets.yml')
            self.assertIn("github.event_name != 'pull_request'", asset_job['if'])
            job = data['jobs'][consumer]
            self.assertIn('published-assets', job['needs'])
            self.assertIn("needs.published-assets.result == 'success'", job['if'])
            commands = '\n'.join(step.get('run', '') for step in job['steps'])
            self.assertIn('--published-image "$PUBLISHED_ASSET_IMAGE"', commands)
            self.assertIn('--asset-release "$PI_ASSET_RELEASE_FILE"', commands)
        publish = (workflows / 'publish-oci-container.yml').read_text()
        self.assertIn('PI_ASSET_IMAGE=${{ env.PI_ASSET_IMAGE }}', publish)
        self.assertIn('PI_ASSET_MANIFEST_SHA256=${{ env.PI_ASSET_MANIFEST_SHA256 }}', publish)


if __name__ == '__main__':
    unittest.main()
