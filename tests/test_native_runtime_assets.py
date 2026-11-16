"""Offline native CUDA closure verification; fixtures are never executed."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from pi_platform.deployment import native_runtime_assets as native
from pi_platform.deployment.asset_pack import AssetPackError, sha256


class NativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.archives = self.root / 'archives'
        self.archives.mkdir()
        self.lock = {'runtime_version': 'b11515', 'windows': {'cuda': []}}
        for name, files in [('server.zip', {'llama-server.exe': b'fixture-exe', 'ggml-cuda.dll': b'fixture-ggml'}),
                            ('runtime.zip', {'cudart64_12.dll': b'fixture-cudart'})]:
            path = self.archives / name
            with zipfile.ZipFile(path, 'w') as stream:
                for filename, body in files.items(): stream.writestr(filename, body)
            self.lock['windows']['cuda'].append({'name': name, 'sha256': sha256(path)})
        self.patcher = patch.object(native, 'runtime_lock', return_value=self.lock)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.primary = 'a' * 64
        self.candidate = self.root / 'candidate'
        native.inspect_archives(self.archives, self.candidate, self.primary)

    def approve(self, scope='operator-local'):
        review = self.candidate / 'licenses/operator-review.json'
        review.write_text(json.dumps({'approved': True, 'scope': scope, 'review_id': 'synthetic-test-review'}))
        path = self.candidate / 'manifest.json'
        data = json.loads(path.read_text())
        data['release_status'] = 'verified'
        for row in data['files']:
            row.update(license='LicenseRef-TestFixture', license_evidence='licenses/operator-review.json')
            row['sha256'] = sha256(self.candidate / row['path'])
        path.write_text(json.dumps(data))
        return sha256(path)

    def verify(self, digest=None, **kwargs):
        return native.verify_native_runtime_pack(self.candidate, digest or self.approve(), self.primary, **kwargs)

    def test_candidate_cannot_execute_or_install_without_review(self):
        with self.assertRaises(AssetPackError):
            self.verify(sha256(self.candidate / 'manifest.json'))

    def test_roundtrip_installs_isolated_digest_directory_and_rechecks_cache(self):
        digest = self.approve()
        dest = self.root / 'installed'
        final = native.install(self.candidate, dest, digest, self.primary)
        self.assertEqual(final, dest / digest)
        self.assertEqual((final / 'windows/cuda/llama-server.exe').read_bytes(), b'fixture-exe')
        self.assertEqual(native.install(self.candidate, dest, digest, self.primary), final)
        (final / 'windows/cuda/ggml-cuda.dll').write_bytes(b'corrupted')
        with self.assertRaises(AssetPackError): native.install(self.candidate, dest, digest, self.primary)

    def test_tampered_missing_or_extra_binary_rejected(self):
        digest = self.approve()
        path = self.candidate / 'windows/cuda/ggml-cuda.dll'
        for body in (b'changed', None):
            if body is None: path.unlink()
            else: path.write_bytes(body)
            with self.assertRaises(AssetPackError): self.verify(digest)
        path.write_bytes(b'fixture-ggml')
        (path.parent / 'extra.dll').write_bytes(b'x')
        with self.assertRaises(AssetPackError): self.verify(digest)

    def test_main_binding_and_distribution_approval_enforced(self):
        digest = self.approve()
        with self.assertRaises(AssetPackError):
            native.verify_native_runtime_pack(self.candidate, digest, 'b' * 64)
        with self.assertRaises(AssetPackError): self.verify(digest, mode='reviewed-oci')
        self.verify(self.approve(scope='redistribution'), mode='reviewed-oci')

    def test_inventory_cannot_substitute_arbitrary_binary_for_pinned_archive(self):
        self.approve()
        path = self.candidate / 'windows/cuda/llama-server.exe'
        path.write_bytes(b'arbitrary')
        manifest = self.candidate / 'manifest.json'
        data = json.loads(manifest.read_text())
        next(row for row in data['files'] if row['path'].endswith('llama-server.exe'))['sha256'] = sha256(path)
        manifest.write_text(json.dumps(data))
        with self.assertRaisesRegex(AssetPackError, 'closure'):
            self.verify(sha256(manifest))

    def test_path_semantics_and_archive_collisions_rejected(self):
        for name in ('../evil.exe', 'C:/evil.exe', 'a:stream', 'CON.dll', 'a./b.dll',
                     'a\\b.dll', 'A.dll', 'folder/../x.dll', '/root.dll'):
            with self.subTest(name=name):
                archive = self.archives / 'bad.zip'
                with zipfile.ZipFile(archive, 'w') as stream:
                    info = zipfile.ZipInfo('placeholder')
                    info.filename = info.orig_filename = name
                    stream.writestr(info, b'x')
                    if name == 'A.dll': stream.writestr('a.dll', b'y')
                with self.assertRaises(AssetPackError): native.archive_inventory(archive)

    def test_raw_member_names_rejected_before_host_normalization(self):
        for name in ('folder\\runtime.dll', 'runtime.dll\x00hidden'):
            with self.subTest(name=name):
                archive = self.archives / 'raw-name.zip'
                # Supplying a string to writestr invokes ZipInfo's host path
                # normalization. Preserve the hostile bytes in the ZIP itself.
                info = zipfile.ZipInfo('placeholder')
                info.filename = info.orig_filename = name
                with zipfile.ZipFile(archive, 'w') as stream:
                    stream.writestr(info, b'x')
                with zipfile.ZipFile(archive) as stream:
                    self.assertEqual(stream.infolist()[0].orig_filename, name)
                for separator in ('/', '\\'):
                    with self.subTest(host_separator=separator), patch.object(zipfile.os, 'sep', separator):
                        with self.assertRaises(AssetPackError):
                            native.archive_inventory(archive)

    def test_portable_member_names_accepted_under_both_host_separators(self):
        archive = self.archives / 'portable-name.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('folder/runtime.dll', b'x')
        for separator in ('/', '\\'):
            with self.subTest(host_separator=separator), patch.object(zipfile.os, 'sep', separator):
                self.assertEqual(native.archive_inventory(archive), {'folder/runtime.dll': hashlib.sha256(b'x').hexdigest()})

    def test_parent_case_collision_rejected_before_extraction(self):
        archive = self.archives / 'case.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('A/one.dll', b'x')
            stream.writestr('a/two.dll', b'y')
        with self.assertRaises(AssetPackError): native.archive_inventory(archive)

    def test_archive_hash_mismatch_prevents_inspection(self):
        (self.archives / 'server.zip').write_bytes(b'changed')
        with self.assertRaises(AssetPackError):
            native.inspect_archives(self.archives, self.root / 'bad-candidate', self.primary)

    def test_hardlinks_rejected(self):
        import os
        digest = self.approve()
        path = self.candidate / 'windows/cuda/ggml-cuda.dll'
        os.link(path, self.root / 'linked-dll')
        with self.assertRaises(AssetPackError): self.verify(digest)

    def test_false_review_and_runtime_revision_rejected(self):
        digest = self.approve()
        review = self.candidate / 'licenses/operator-review.json'
        review.write_text(json.dumps({'approved': False, 'scope': 'operator-local', 'review_id': 'fixture'}))
        path = self.candidate / 'manifest.json'
        data = json.loads(path.read_text())
        next(row for row in data['files'] if row['path'] == native.REVIEW)['sha256'] = sha256(review)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(AssetPackError, 'approval'):
            self.verify(sha256(path))
        self.approve()
        data = json.loads(path.read_text()); data['llama_cpp_revision'] = 'unknown'
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(AssetPackError, 'Incompatible'):
            self.verify(sha256(path))

    def test_manifest_cannot_replace_the_archive_pins(self):
        self.approve()
        archive = self.candidate / 'windows/archives/server.zip'
        with zipfile.ZipFile(archive, 'w') as stream:
            stream.writestr('llama-server.exe', b'arbitrary')
        path = self.candidate / 'manifest.json'; data = json.loads(path.read_text())
        next(row for row in data['files'] if row['path'].endswith('server.zip'))['sha256'] = sha256(archive)
        path.write_text(json.dumps(data))
        with self.assertRaisesRegex(AssetPackError, 'pin mismatch'):
            self.verify(sha256(path))

    def test_failed_install_leaves_previous_pack_and_no_partial_final(self):
        digest = self.approve(); destination = self.root / 'installed'
        previous = destination / ('b' * 64); previous.mkdir(parents=True)
        (previous / 'keep.txt').write_text('unchanged')
        (self.candidate / 'windows/cuda/ggml-cuda.dll').unlink()
        with self.assertRaises(AssetPackError): native.install(self.candidate, destination, digest, self.primary)
        self.assertEqual((previous / 'keep.txt').read_text(), 'unchanged')
        self.assertFalse((destination / digest).exists())

    def test_zip_bomb_and_link_rejected(self):
        archive = self.archives / 'bad.zip'
        with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as stream:
            stream.writestr('huge.dll', b'0' * 10000)
        with patch.object(native, 'MAX_EXPANDED_BYTES', 100):
            with self.assertRaises(AssetPackError): native.archive_inventory(archive)
        with zipfile.ZipFile(archive, 'w') as stream:
            info = zipfile.ZipInfo('linked.dll'); info.create_system = 3; info.external_attr = 0o120777 << 16
            stream.writestr(info, b'elsewhere')
        with self.assertRaises(AssetPackError): native.archive_inventory(archive)
