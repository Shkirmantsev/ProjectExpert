"""Windows path regressions, with native-path spellings reproducible on Linux."""
from pathlib import Path
from types import SimpleNamespace
import os
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.adapters.sync.portable_format import PortableSnapshotError, source_path
from pi_platform.core.canonical import Shard, canonical_dump_json, content_address, manifest_from_shards
from pi_platform.core.sync.hydrate import HydrateService
from pi_platform.runtime import RuntimeCache


class LegacyWindowsManifestTests(unittest.TestCase):
    def test_native_windows_manifest_restores_graph_family_and_warm_hit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            body = {'id': 'entity', 'family': 'Component', 'label': 'Billing'}
            path = root / 'graph/nodes/aa/entity.json'
            path.parent.mkdir(parents=True)
            path.write_bytes(canonical_dump_json(body))
            digest = content_address(body)
            manifest = manifest_from_shards('graph', [Shard(
                id='entity', path=r'graph\nodes\aa\entity.json', contentHash=digest)])
            cache = RuntimeCache(root / 'cache')
            service = HydrateService(cache=cache)
            try:
                cold = service._hydrate_family(root, manifest, cache, root)
            except ValueError as exc:
                self.fail(f'Valid v1 Windows manifest rejected: {exc}')
            self.assertEqual(cold, (0, 1))
            self.assertEqual(cache.get(digest).family, 'graph')
            self.assertEqual(service._hydrate_family(root, manifest, cache, root), (1, 1))

    def test_legacy_native_separator_support_does_not_allow_escape_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            cache = RuntimeCache(root / 'cache')
            for relative in (r'..\outside.json', r'graph\..\..\outside.json',
                             r'C:\outside.json', r'\\server\share\outside.json', r'\outside.json'):
                with self.subTest(path=relative):
                    manifest = manifest_from_shards('objects', [Shard(
                        id='unsafe', path=relative, contentHash='a' * 64)])
                    with self.assertRaises(ValueError):
                        HydrateService(cache=cache)._hydrate_family(root, manifest, cache, root)
            # v2 remains strictly POSIX; compatibility is restricted to v1.
            with self.assertRaises(PortableSnapshotError):
                source_path(r'objects\aa\payload.json')


class AliasedTempRootTests(unittest.TestCase):
    def test_portable_fixture_uses_resolved_root_for_signed_auto_publication(self):
        from tests.test_portable_canonical_sync import PortableProductionTests
        from pi_platform.cli.main import _bootstrap_and_index_target
        from pi_platform.ports import ApprovalRequest
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory).resolve()
            actual, alias = parent / 'actual', parent / 'alias'
            actual.mkdir()
            try:
                alias.symlink_to(actual, target_is_directory=True)
            except OSError:
                self.skipTest('Creating an alias requires symlink privilege')
            fixture = PortableProductionTests()
            fake_temp = SimpleNamespace(name=str(alias), cleanup=lambda: None)
            try:
                with patch('tests.test_portable_canonical_sync.tempfile.TemporaryDirectory', return_value=fake_temp):
                    fixture.setUp()
                capability = fixture.boundary.issue(ApprovalRequest(
                    action='materialise', repo_root=str(fixture.root)))
                with patch.dict(os.environ, {'PI_PORTABLE_EXPORT': 'approved-auto',
                        'PI_OPERATOR_APPROVAL_KEY': 'test-only-local-key',
                        'PI_PORTABLE_APPROVAL_TOKEN': capability}):
                    result = _bootstrap_and_index_target(fixture.root)
                self.assertEqual(result['portable_export']['state'], 'published', result['portable_export'])
            finally:
                fixture.doCleanups()


if __name__ == '__main__':
    unittest.main()
