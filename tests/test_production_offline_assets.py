"""Offline startup failures must precede downloads and canonical writes."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import yaml
from pi_platform.cli import gguf_setup
from pi_platform.deployment.asset_pack import AssetPackError, seed
from pi_platform.deployment.offline_assets import configure, release_identity, verify_pack, COMPATIBILITY


class ProductionOfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_missing_embedding_assets_never_download_or_create_key(self):
        with patch.object(gguf_setup.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            with self.assertRaisesRegex(ValueError, 'offline embedding asset'):
                gguf_setup.prepare(self.root / 'missing')
        self.assertFalse((self.root / 'missing').exists())

    def test_verified_local_weights_and_key_are_reused_without_network(self):
        files = [('model.gguf', 'https://invalid', hashlib.sha256(b'model').hexdigest()),
                 ('projector.gguf', 'https://invalid', hashlib.sha256(b'projector').hexdigest())]
        (self.root / 'model.gguf').write_bytes(b'model')
        (self.root / 'projector.gguf').write_bytes(b'projector')
        with patch.object(gguf_setup, 'GEMMA_FILES', files), patch.object(gguf_setup.urllib.request, 'urlopen', side_effect=AssertionError('network')):
            gguf_setup.prepare(self.root)
            key = (self.root / 'llama-api-key').read_bytes()
            gguf_setup.prepare(self.root)
        self.assertEqual(key, (self.root / 'llama-api-key').read_bytes())

    def test_docling_missing_pack_does_not_import_hub_or_download(self):
        from pi_platform.adapters.pdf.real_docling import _pinned_pdf_assets, RealDoclingConverterError
        with patch.dict('sys.modules', {'huggingface_hub': None}):
            with self.assertRaisesRegex(RealDoclingConverterError, 'local Docling assets'):
                _pinned_pdf_assets(do_ocr=True)

    def test_stale_environment_diagnoses_upgrade_without_trusting_marker(self):
        (self.root / 'active-asset-pack').write_text('1' * 64)
        with self.assertRaisesRegex(AssetPackError, 'upgrade.*--upgrade'):
            configure(self.root)

    def test_missing_pack_fails_before_index_lock_or_cache_mutation(self):
        from pi_platform.core.orchestration.repository_indexing import index_repository
        with patch.dict(os.environ, {'PI_REQUIRE_OFFLINE_ASSETS': '1'}), patch(
            'pi_platform.adapters.runtime.sqlite_ingestion_cache.exclusive_indexer', side_effect=AssertionError('cache mutated')):
            with self.assertRaisesRegex(AssetPackError, 'Missing offline asset'):
                index_repository(target=self.root, cache_root=self.root / 'cache', inventory=None,
                                 previous_inventory=None, settings=None)
        self.assertFalse((self.root / 'cache').exists())

    def test_blocked_release_and_mutable_image_cannot_promote(self):
        path = self.root / 'release.json'
        path.write_text(json.dumps({'release_status': 'blocked'}))
        with self.assertRaisesRegex(AssetPackError, 'blocked'):
            release_identity(path)
        path.write_text(json.dumps({'release_status': 'verified', 'image': 'assets:latest', 'manifest_sha256': '1' * 64}))
        with self.assertRaisesRegex(AssetPackError, 'OCI digest'):
            release_identity(path)

    def make_pack(self):
        from pi_platform.adapters.pdf.real_docling import DOCLING_OCR_FILES
        from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_FILENAME, GEMMA_PROJECTOR_FILENAME
        source = self.root / 'source'
        names = ['licenses/NOTICE', 'embedding/' + GEMMA_FILENAME, 'embedding/' + GEMMA_PROJECTOR_FILENAME,
                 *['transformers/gemma/' + name for name in ('config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors')],
                 *['docling/artifacts/docling-project--docling-layout-heron/' + name for name in ('config.json', 'preprocessor_config.json', 'model.safetensors')],
                 'docling/artifacts/docling-project--docling-models/config.json',
                 'docling/artifacts/docling-project--docling-models/model_artifacts/tableformer/accurate/tm_config.json',
                 'docling/artifacts/docling-project--docling-models/model_artifacts/tableformer/accurate/model.safetensors',
                 *['docling/ocr/' + name for name in DOCLING_OCR_FILES],
                 'windows/cuda/llama-server.exe', 'windows/vulkan/llama-server.exe']
        entries = []
        for name in names:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'unit fixture')
            entries.append(dict(path=name, sha256=hashlib.sha256(b'unit fixture').hexdigest(),
                                source='https://example.invalid', revision='test-only', license='test-only', license_evidence='licenses/NOTICE'))
        manifest = dict(schema_version=1, release_status='verified', runtime_compatibility=COMPATIBILITY, native_backends=['vulkan'],
                        production_lock_sha256=hashlib.sha256(Path('requirements-production-linux-x86_64.txt').read_bytes()).hexdigest(), files=entries)
        (source / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
        digest = hashlib.sha256((source / 'manifest.json').read_bytes()).hexdigest()
        final = seed(source, self.root / 'models', digest)
        for key in ('GEMMA_SHA256', 'GEMMA_PROJECTOR_SHA256'):
            patcher = patch('pi_platform.deployment.offline_assets.' + key, hashlib.sha256(b'unit fixture').hexdigest())
            patcher.start()
            self.addCleanup(patcher.stop)
        return final, digest

    def test_installed_pack_routes_consumers_by_independent_digest(self):
        final, digest = self.make_pack()
        with patch.dict(os.environ, {'PI_ASSET_MANIFEST_SHA256': digest}):
            self.assertEqual(configure(self.root / 'models'), final)
            self.assertEqual(os.environ['PI_DOCLING_TOKENIZER'], str(final / 'transformers/gemma'))
            self.assertEqual(os.environ['HF_HUB_OFFLINE'], '1')

    def test_installed_wheel_uses_explicit_application_home_for_exact_lock(self):
        final, digest = self.make_pack()
        with patch('pi_platform.deployment.offline_assets.__file__', str(self.root / 'site-packages/pi_platform/deployment/offline_assets.py')), patch.dict(
            os.environ, {'PI_PLATFORM_HOME': str(Path.cwd())}):
            verify_pack(final, digest)
        wrong_home = self.root / 'wrong-home'
        wrong_home.mkdir()
        (wrong_home / 'requirements-production-linux-x86_64.txt').write_text('wrong lock')
        with patch.dict(os.environ, {'PI_PLATFORM_HOME': str(wrong_home)}):
            with self.assertRaisesRegex(AssetPackError, 'exact production dependency lock'):
                verify_pack(final, digest)

    def test_corrupt_ocr_and_missing_tokenizer_fail_before_loading(self):
        from pi_platform.adapters.pdf.real_docling import DOCLING_OCR_FILES
        final, digest = self.make_pack()
        ocr = final / 'docling/ocr' / DOCLING_OCR_FILES[0]
        ocr.write_bytes(b'corrupt')
        with self.assertRaisesRegex(AssetPackError, 'checksum'):
            verify_pack(final, digest)
        ocr.write_bytes(b'unit fixture')
        (final / 'transformers/gemma/tokenizer.json').unlink()
        with self.assertRaisesRegex(AssetPackError, 'Missing asset'):
            verify_pack(final, digest)

    def test_candidate_inspection_does_not_grant_seed_or_activation(self):
        from pi_platform.deployment.offline_assets import verify_candidate
        root, _ = self.make_pack()
        path = root / 'manifest.json'
        data = json.loads(path.read_text())
        data['release_status'] = 'blocked'
        path.write_text(json.dumps(data))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(verify_candidate(root, digest)['release_status'], 'blocked')
        with self.assertRaisesRegex(AssetPackError, 'blocked'):
            seed(root, self.root / 'unapproved', digest)
        with self.assertRaisesRegex(AssetPackError, 'blocked'):
            verify_pack(root, digest)
        self.assertFalse((self.root / 'unapproved').exists())

    def test_every_default_mode_requires_seed_and_offline_environment(self):
        bundle = Path('distribution/deployment')
        services = yaml.safe_load((bundle / 'compose.yaml').read_text())['services']
        self.assertEqual(services['asset-seed']['network_mode'], 'none')
        self.assertEqual(services['production']['depends_on']['asset-seed']['condition'], 'service_completed_successfully')
        env = services['production']['environment']
        for key, value in {'PI_ALLOW_REMOTE_ASSET_DOWNLOADS':'0', 'HF_HUB_OFFLINE':'1', 'TRANSFORMERS_OFFLINE':'1'}.items():
            self.assertEqual(env[key], value)
        setup = yaml.safe_load((bundle / 'compose.accelerator.yaml').read_text())['services']['model-setup']
        self.assertEqual(setup['network_mode'], 'none')
        self.assertIn('asset-seed', setup['depends_on'])
        native = (bundle / 'setup-windows-accelerator.ps1').read_text()
        self.assertNotIn('Invoke-WebRequest', native)
        self.assertIn('docker cp', native)
        self.assertIn('--network none', native)

class MaterializationTests(unittest.TestCase):
    def test_cache_reuse_requires_matching_sha256_and_never_uses_a_bad_copy(self):
        from scripts import materialize_asset_pack as builder
        import io
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            cache = root / 'cache'
            cache.mkdir()
            good = b'verified bytes'
            digest = hashlib.sha256(good).hexdigest()
            (cache / digest).write_bytes(good)
            destination = root / 'output' / 'weight.bin'
            with patch.object(builder.urllib.request, 'urlopen', side_effect=AssertionError('network')):
                builder.fetch('https://example.invalid', destination, digest, cache_roots=[cache])
            self.assertEqual(destination.read_bytes(), good)
            destination.unlink()
            (cache / digest).write_bytes(b'corrupt')
            with patch.object(builder.urllib.request, 'urlopen', return_value=io.BytesIO(good)) as download:
                builder.fetch('https://example.invalid', destination, digest, cache_roots=[cache])
            download.assert_called_once()
            self.assertEqual(destination.read_bytes(), good)

    def test_materialization_never_self_approves_licenses_or_release(self):
        import io
        from scripts import materialize_asset_pack as builder
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw) / 'candidate'
            def fetch(url, destination, expected=None, **kwargs):
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.suffix == '.zip':
                    import zipfile
                    with zipfile.ZipFile(destination, 'w') as bundle:
                        bundle.writestr('llama-server.exe', b'fixture executable')
                else:
                    destination.write_bytes(b'fixture')
            def metadata(url, **kwargs):
                revision = url.split('?', 1)[0].rsplit('/', 1)[-1]
                return io.BytesIO(json.dumps({'sha': revision, 'siblings':[{'rfilename':'config.json'}]}).encode())
            with patch.object(builder, 'fetch', side_effect=fetch), patch.object(builder.urllib.request, 'urlopen', side_effect=metadata):
                manifest = builder.assemble(root)
            self.assertEqual(manifest['release_status'], 'blocked')
            self.assertTrue(manifest['files'])
            self.assertTrue(all(row['license'] is None and row['license_evidence'] is None for row in manifest['files']))
            from pi_platform.deployment.asset_pack import load_manifest, sha256
            with self.assertRaisesRegex(AssetPackError, 'blocked'):
                load_manifest(root / 'manifest.json', sha256(root / 'manifest.json'))
            self.assertTrue((root / 'windows/vulkan/llama-server.exe').is_file())
            self.assertFalse((root / 'windows/cuda').exists())
            with self.assertRaisesRegex(AssetPackError, 'empty controlled'):
                builder.assemble(root)


if __name__ == '__main__':
    unittest.main()
