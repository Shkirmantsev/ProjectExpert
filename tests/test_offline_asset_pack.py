"""Offline pack integrity, publication and strict CA merge regression tests."""
import hashlib
import json
import os
from pathlib import Path
import ssl
import tempfile
import unittest

from pi_platform.deployment.asset_pack import AssetPackError, load_manifest, seed
from pi_platform.deployment.trust import merge_ca_bundles


class OfflineAssetPackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.destination = self.root / 'models'
        entries = []
        for name, content in [('licenses/LICENSE', b'reviewed license evidence'), ('embedding/model.gguf', b'pinned model')]:
            path = self.source / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(content)
            entries.append(dict(path=name, sha256=hashlib.sha256(content).hexdigest(), source='https://example.org/model', revision='abcdef', license='Apache-2.0', license_evidence='licenses/LICENSE'))
        self.manifest = dict(schema_version=1, release_status='verified', runtime_compatibility='test', files=entries)
        self.pin()

    def pin(self):
        self.path = self.source / 'manifest.json'
        self.path.write_text(json.dumps(self.manifest))
        self.digest = hashlib.sha256(self.path.read_bytes()).hexdigest()

    def test_idempotent_seed_preserves_previous_generation(self):
        first = seed(self.source, self.destination, self.digest)
        self.assertEqual(seed(self.source, self.destination, self.digest), first)
        self.manifest['runtime_compatibility'] = 'test-v2'
        self.pin()
        second = seed(self.source, self.destination, self.digest)
        self.assertNotEqual(first, second)
        self.assertTrue((first / 'embedding/model.gguf').is_file())
        self.assertEqual((self.destination / 'active-asset-pack').read_text().strip(), self.digest)

    @unittest.skipIf(os.name == 'nt', 'POSIX application UID permissions')
    def test_published_pack_is_readable_after_dropping_root_with_private_umask(self):
        self.destination.mkdir()
        previous = os.umask(0o077)
        try:
            final = seed(self.source, self.destination, self.digest)
        finally:
            os.umask(previous)
        self.assertEqual((self.destination / 'asset-packs').stat().st_mode & 0o777, 0o755)
        for path in [final, *final.rglob('*')]:
            self.assertEqual(path.stat().st_mode & 0o777, 0o755 if path.is_dir() else 0o644, str(path))

    def test_damaged_installed_pack_is_not_silently_accepted_or_overwritten(self):
        final = seed(self.source, self.destination, self.digest)
        model = final / 'embedding/model.gguf'
        model.write_bytes(b'corrupt')
        with self.assertRaisesRegex(AssetPackError, 'checksum'):
            seed(self.source, self.destination, self.digest)
        self.assertEqual(model.read_bytes(), b'corrupt')

    def test_installed_manifest_is_reverified_despite_successful_marker(self):
        final = seed(self.source, self.destination, self.digest)
        (final / 'manifest.json').write_text('{}')
        with self.assertRaisesRegex(AssetPackError, 'digest'):
            seed(self.source, self.destination, self.digest)

    def test_uninventoried_file_blocks_seeding(self):
        (self.source / 'unexpected-weight.bin').write_bytes(b'not licensed or hashed')
        with self.assertRaisesRegex(AssetPackError, 'Uninventoried'):
            seed(self.source, self.destination, self.digest)
        self.assertFalse(self.destination.exists())

    def test_wrong_manifest_pin_fails_before_seeding(self):
        with self.assertRaisesRegex(AssetPackError, 'digest'):
            seed(self.source, self.destination, '0' * 64)
        self.assertFalse(self.destination.exists())

    def test_missing_license_evidence_blocks_release(self):
        self.manifest['files'][1]['license_evidence'] = 'missing'
        self.pin()
        with self.assertRaisesRegex(AssetPackError, 'evidence'):
            seed(self.source, self.destination, self.digest)

    def test_blocked_release_cannot_seed(self):
        self.manifest['release_status'] = 'blocked'
        self.pin()
        with self.assertRaisesRegex(AssetPackError, 'blocked'):
            seed(self.source, self.destination, self.digest)

    def test_traversal_and_external_symlink_rejected(self):
        for name in ['../outside', '/absolute', 'a\\b', 'C:/windows']:
            self.manifest['files'][1]['path'] = name
            self.pin()
            with self.assertRaises(AssetPackError):
                seed(self.source, self.destination, self.digest)
        self.manifest['files'][1]['path'] = 'embedding/model.gguf'
        self.pin()
        model = self.source / 'embedding/model.gguf'
        external = self.root / 'outside'
        external.write_bytes(model.read_bytes())
        model.unlink()
        try:
            model.symlink_to(external)
        except OSError:
            if os.name == 'nt':
                return  # Traversal cases above still ran; no symlink privilege.
            raise
        with self.assertRaisesRegex(AssetPackError, 'Linked'):
            seed(self.source, self.destination, self.digest)

    def test_repository_manifest_is_honestly_blocked(self):
        path = Path('distribution/assets/assets-lock.json')
        with self.assertRaisesRegex(AssetPackError, 'blocked'):
            load_manifest(path, hashlib.sha256(path.read_bytes()).hexdigest())


class TrustBundleTests(unittest.TestCase):
    def system_bundle(self, root):
        certificates = ssl.create_default_context().get_ca_certs(binary_form=True)
        if not certificates:
            self.skipTest('No platform trust roots available')
        path = root / 'system.pem'
        path.write_text(''.join(ssl.DER_cert_to_PEM_cert(value) for value in certificates))
        return path

    def test_merge_preserves_public_roots_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = self.system_bundle(root)
            output = root / 'merged.pem'
            result = merge_ca_bundles(system, [system], output)
            context = ssl.create_default_context(cafile=str(output))
            self.assertGreater(result['certificates'], 0)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertTrue(context.check_hostname)
            self.assertEqual(len(context.get_ca_certs()), len(ssl.create_default_context(cafile=str(system)).get_ca_certs()))

    def test_invalid_or_private_input_does_not_replace_working_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'merged.pem'
            output.write_text('previous valid bundle')
            for value in ['no certificates', '-----BEGIN PRIVATE KEY-----']:
                extra = root / 'host.pem'
                extra.write_text(value)
                with self.assertRaises(ValueError):
                    merge_ca_bundles(self.system_bundle(root), [extra], output)
                self.assertEqual(output.read_text(), 'previous valid bundle')
