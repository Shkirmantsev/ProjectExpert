"""Static Python analysis and real content-addressed ingestion coverage."""
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from pi_platform.adapters.python.intelligence import PythonManifestAdapter, PythonSourceAdapter, PythonWheelAdapter, requirement_record
from pi_platform.adapters.ingest.local_pipeline_driver import LocalPipelineDriver
from pi_platform.core.canonical.content_address import content_address_bytes
from pi_platform.core.canonical.value_types import Source
from pi_platform.core.ingest.runtime_cache import InMemoryRuntimeCache
from pi_platform.core.ingest.local_source_inbox_scanner import LocalSourceInboxScanner
from pi_platform.core.orchestration.repository_indexing import _family
from pi_platform.ports.ingest.source_adapter import SourceAdapterContext, SourceAdapterError


class PythonIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def source(self, name, text):
        p = self.root / name
        p.write_text(text)
        return Source('repo:' + name, str(p), _family(p).value, content_address_bytes(p.read_bytes()))

    def test_pyproject_extras_markers_and_build_dependencies(self):
        source = self.source('pyproject.toml', '''[project]
name = "sample"
dependencies = ["Requests[socks]>=2.31,<3; python_version >= '3.11'"]
[project.optional-dependencies]
test = ["pytest==8.0"]
[build-system]
requires = ["setuptools>=68"]
''')
        result = PythonManifestAdapter().parse(source)
        deps = [e for e in result.entities if e.family == 'Dependency']
        self.assertEqual([e.label for e in deps], ['requests', 'pytest', 'setuptools'])
        attrs = deps[0].metadata.extensions
        self.assertEqual(attrs['extras'], ['socks'])
        self.assertEqual(attrs['marker'], "python_version >= '3.11'")
        self.assertFalse(attrs['resolved'])
        self.assertEqual(attrs['specifier'], '>=2.31,<3')
        self.assertEqual(deps[1].metadata.extensions['scope'], 'extra:test')
        self.assertEqual(deps[2].metadata.extensions['scope'], 'build')
        self.assertEqual(len([r for r in result.relations if r.family == 'DEPENDSON']), 3)

    def test_requirements_hashes_continuations_and_unfollowed_includes(self):
        source = self.source('requirements.txt', 'Foo_Bar==1.2 \\\n --hash=sha256:abcd\n-r ../private.txt\n-e .\n# comment\n')
        result = PythonManifestAdapter().parse(source)
        deps = [e for e in result.entities if e.family == 'Dependency']
        self.assertEqual([e.label for e in deps], ['foo-bar'])
        self.assertIn('not followed', result.rationale)
        self.assertIn('transitive closure', result.rationale)

    def test_direct_reference_preserves_fragment_and_marker(self):
        row = requirement_record("Foo @ https://example.invalid/pkg.whl#sha256=abc ; os_name == 'nt'")
        self.assertEqual(row['url'], 'https://example.invalid/pkg.whl#sha256=abc')
        self.assertEqual(row['marker'], "os_name == 'nt'")

    def test_source_api_without_executing_imports(self):
        source = self.source('library.py', '''raise RuntimeError("MUST NOT EXECUTE")
import dangerous
class Client:
    """Public client API."""
    async def fetch(self, url: str) -> bytes:
        """Fetch payload."""
        pass
    def _private(self): pass
''')
        result = PythonSourceAdapter().parse(source, SourceAdapterContext(self.root))
        labels = [e.label for e in result.entities]
        self.assertIn('library.Client.fetch', labels)
        self.assertNotIn('library.Client._private', labels)
        api = next(e for e in result.entities if e.label == 'library.Client.fetch')
        self.assertEqual(api.metadata.extensions['returns'], 'bytes')
        self.assertTrue(api.metadata.extensions['async'])
        self.assertEqual(api.metadata.extensions['docstring'], 'Fetch payload.')

    def test_wheel_metadata_and_public_api(self):
        path = self.root / 'demo.whl'
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('demo-1.2.dist-info/METADATA', 'Metadata-Version: 2.4\nName: Demo\nVersion: 1.2\nLicense-Expression: MIT\nRequires-Dist: requests (>=2); python_version > "3.10"\n\nDemo library')
            z.writestr('demo/api.py', 'def request(url: str):\n    """Send a request."""\n    pass\n')
        source = Source('wheel', str(path), 'python_wheel', content_address_bytes(path.read_bytes()))
        result = PythonWheelAdapter().parse(source)
        self.assertTrue(any(e.label == 'demo.api.request' for e in result.entities))
        owner = next(e for e in result.entities if e.label == 'demo')
        self.assertEqual(owner.metadata.extensions['version'], '1.2')
        self.assertEqual(owner.metadata.extensions['spdx'], 'MIT')
        self.assertEqual(owner.metadata.extensions['licenseReview'], 'required')
        self.assertIn('demo.api', '\n'.join(c.rawText for s in result.sections for c in s.chunks) + '\n'.join(s.heading for s in result.sections))

    def test_invalid_source_and_archive_fail_explicitly(self):
        source = self.source('broken.py', 'def syntax error')
        with self.assertRaises(SourceAdapterError):
            PythonSourceAdapter().parse(source)
        p = self.root / 'bad.whl'
        with zipfile.ZipFile(p, 'w') as z:
            z.writestr('a.dist-info/METADATA', 'Name: a\nVersion: 1')
            z.writestr('../escape.py', 'print(1)')
        with self.assertRaises(SourceAdapterError):
            PythonWheelAdapter().parse(Source('bad', str(p), 'python_wheel', 'hash'))

    def test_pipeline_records_searchable_chunks_and_reuses_unchanged_input(self):
        source = self.source('requirements.in', 'requests>=2\n')
        self.assertEqual(LocalSourceInboxScanner._family_for(Path(source.uri)), 'python_manifest')
        cache = InMemoryRuntimeCache()
        driver = LocalPipelineDriver(cache=cache)
        first = driver.run(source, self.root)
        self.assertGreater(first.entity_count, 0)
        records = [json.loads(v) for v in cache._store.values()]
        self.assertTrue(any(r.get('family') == 'Dependency' and r.get('label') == 'requests' for r in records))
        self.assertTrue(any('requests>=2' in r.get('rawText', '') for r in records))
        second = driver.run(source, self.root)
        self.assertGreater(second.cache_hit_count, 0)
