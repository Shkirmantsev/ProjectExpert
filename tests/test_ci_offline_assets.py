"""PR verification must work before registry publication without granting release."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.deployment.asset_pack import AssetPackError
from scripts.prepare_ci_assets import prepare, reviewed_inventory


ROOT = Path(__file__).resolve().parents[1]


class CiOfflineAssetsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        shutil.copytree(ROOT / 'distribution/assets', self.root / 'distribution/assets')
        shutil.copyfile(ROOT / 'requirements-production-linux-x86_64.txt', self.root / 'requirements-production-linux-x86_64.txt')
        self.release = self.root / 'distribution/assets/asset-release.json'
        release = json.loads(self.release.read_text())
        release.update(release_status='blocked', image=None)
        self.release.write_text(json.dumps(release))

    def test_unpublished_release_still_blocks_default_before_external_work(self):
        with patch('scripts.prepare_ci_assets.subprocess.run') as run:
            with self.assertRaisesRegex(AssetPackError, 'blocked'):
                prepare(self.root)
        run.assert_not_called()

    def test_candidate_builds_approved_files_and_returns_actual_local_identity(self):
        image = 'sha256:' + 'a' * 64
        def run(command, **kwargs):
            if 'scripts/materialize_asset_pack.py' in command:
                (self.root / 'tmp/local/asset-pack').mkdir(parents=True)
            return subprocess.CompletedProcess(command, 0)
        before = self.release.read_bytes()
        with patch('scripts.prepare_ci_assets.subprocess.run', side_effect=run) as execute, patch(
            'scripts.prepare_ci_assets.subprocess.check_output', return_value=image + '\n'):
            result = prepare(self.root, candidate=True)
        self.assertEqual(result['PI_ASSET_IMAGE'], image)
        self.assertEqual(result['PI_ASSET_MODE'], 'candidate')
        self.assertEqual(self.release.read_bytes(), before)
        self.assertFalse((self.root / 'tmp/local/asset-pack').exists())
        assembly = execute.call_args_list[0].args[0]
        self.assertIn('--reviewed-manifest-sha256', assembly)
        self.assertIn('--license-evidence', assembly)
        self.assertEqual(assembly[assembly.index('--native-backends') + 1:], ['vulkan'])

    def test_incompatible_inventory_or_changed_notice_fails_before_download(self):
        manifest_path = self.root / 'distribution/assets/assets-lock.json'
        for tamper in ('inventory', 'notice'):
            with self.subTest(tamper=tamper):
                original = manifest_path.read_bytes()
                if tamper == 'inventory':
                    data = json.loads(original)
                    data['production_lock_sha256'] = '0' * 64
                    manifest_path.write_text(json.dumps(data))
                else:
                    (self.root / 'distribution/assets/licenses/NOTICE.txt').write_text('changed')
                with patch('scripts.prepare_ci_assets.subprocess.run') as run:
                    with self.assertRaises(AssetPackError):
                        prepare(self.root, candidate=True)
                run.assert_not_called()
                manifest_path.write_bytes(original)

    def test_ci_computes_inventory_hash_without_manual_release_metadata_edit(self):
        release = json.loads(self.release.read_text())
        release['manifest_sha256'] = '0' * 64  # Stale source release template is not the CI input.
        self.release.write_text(json.dumps(release))
        digest, _ = reviewed_inventory(self.root)
        self.assertEqual(digest, hashlib.sha256((self.root / 'distribution/assets/assets-lock.json').read_bytes()).hexdigest())

    def test_existing_pack_is_neither_overwritten_nor_removed(self):
        pack = self.root / 'tmp/local/asset-pack'
        pack.mkdir(parents=True)
        marker = pack / 'operator-file'
        marker.write_text('preserve')
        with patch('scripts.prepare_ci_assets.subprocess.run') as run:
            with self.assertRaisesRegex(AssetPackError, 'already exists'):
                prepare(self.root, candidate=True)
        run.assert_not_called()
        self.assertEqual(marker.read_text(), 'preserve')

    def test_valid_digest_cannot_approve_an_unreviewed_candidate(self):
        path = self.root / 'distribution/assets/assets-lock.json'
        manifest = json.loads(path.read_text())
        manifest['release_status'] = 'blocked'
        path.write_text(json.dumps(manifest))
        release = json.loads(self.release.read_text())
        release['manifest_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.release.write_text(json.dumps(release))
        with patch('scripts.prepare_ci_assets.subprocess.run') as run:
            with self.assertRaisesRegex(AssetPackError, 'blocked'):
                prepare(self.root, candidate=True)
        run.assert_not_called()

    def test_published_mode_uses_immutable_registry_reference(self):
        release = json.loads(self.release.read_text())
        reference = 'ghcr.io/shkirmantsev/project-intelligence-assets@sha256:' + 'b' * 64
        release.update(release_status='verified', image=reference)
        self.release.write_text(json.dumps(release))
        with patch('scripts.prepare_ci_assets.subprocess.run') as run:
            result = prepare(self.root)
        self.assertEqual(result['PI_ASSET_MODE'], 'published')
        self.assertEqual(result['PI_ASSET_IMAGE'], reference)
        self.assertEqual(run.call_args.args[0], ['docker', 'pull', reference])


if __name__ == '__main__':
    unittest.main()
