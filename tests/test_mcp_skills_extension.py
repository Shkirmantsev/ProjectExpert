"""SEP-2640 regressions: real bundle discovery, integrity and safe resource reads."""
from __future__ import annotations

import base64
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from pi_platform.cli.main import _resolve_skills_root
from pi_platform.mcp.server import McpServer
from pi_platform.mcp.skill_plane import SkillDistributionError, SkillDistributionPlane
from tests.test_mcp_server import _build_context

ROOT = Path(__file__).resolve().parents[1]
URI = 'skill://project-intelligence/SKILL.md'
EXTENSION = 'io.modelcontextprotocol/skills'
META = {
    'io.modelcontextprotocol/protocolVersion': '2026-07-28',
    'io.modelcontextprotocol/clientInfo': {'name': 'skill-test', 'version': '1'},
    'io.modelcontextprotocol/clientCapabilities': {},
}


class SkillsExtensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.skill = self.root / 'project-intelligence'
        self.skill.mkdir()
        self.markdown = (
            '---\nname: project-intelligence\ndescription: Test workflow\n'
            'license: Apache-2.0\nmetadata:\n  version: "1.4.0"\n'
            '  mcp-api: ">=1.3.0 <2.0.0"\n---\n# Workflow\n'
        ).encode()
        (self.skill / 'SKILL.md').write_bytes(self.markdown)
        (self.skill / 'references' / 'nested').mkdir(parents=True)
        (self.skill / 'references' / 'nested' / 'guide.md').write_bytes('Пошук\n'.encode())
        (self.skill / 'assets').mkdir()
        (self.skill / 'assets' / 'sample.bin').write_bytes(b'\x00\xff\x80')
        self.plane = SkillDistributionPlane(skills_root=self.root)
        # A not-ready target must still expose its server's skills.
        self.server = McpServer(context=_build_context(readiness_ready=False))

    def rpc(self, method, **params):
        return self.server.handle_jsonrpc(
            {'jsonrpc': '2.0', 'id': 1, 'method': method,
             'params': {'_meta': META, **params}}, skill_plane=self.plane,
        )

    def test_discovery_and_legacy_initialization_advertise_skill(self):
        modern = self.rpc('server/discover')['result']
        self.assertIn('2026-07-28', modern['supportedVersions'])
        self.assertEqual(modern['capabilities']['extensions'][EXTENSION], {})
        self.assertIn('resources', modern['capabilities'])
        self.assertIn(URI, modern['instructions'])
        legacy = self.rpc('initialize', protocolVersion='2025-11-25')['result']
        self.assertEqual(legacy['protocolVersion'], '2025-11-25')
        self.assertIn(EXTENSION, legacy['capabilities']['extensions'])
        self.assertIn(URI, legacy['instructions'])

    def test_list_get_and_every_resource_have_verifiable_bytes(self):
        listed = self.rpc('skills/list')['result']
        self.assertEqual(listed['resultType'], 'complete')
        self.assertEqual(listed['cacheScope'], 'public')
        self.assertIsInstance(listed['ttlMs'], int)
        self.assertNotIn('nextCursor', listed)
        entry = listed['skills'][0]
        self.assertEqual(len(listed['skills']), 1)
        self.assertEqual(entry['uri'], URI)
        self.assertEqual(entry['frontmatter'], {
            'name': 'project-intelligence', 'description': 'Test workflow',
            'license': 'Apache-2.0',
            'metadata': {'version': '1.4.0', 'mcp-api': '>=1.3.0 <2.0.0'},
        })
        self.assertEqual(self.rpc('skills/get', uri=URI)['result']['skill'], entry)
        self.assertEqual({r['uri'] for r in entry['resources']}, {
            URI, 'skill://project-intelligence/references/nested/guide.md',
            'skill://project-intelligence/assets/sample.bin',
        })
        for item in entry['resources']:
            result = self.rpc('resources/read', uri=item['uri'])['result']
            content = result['contents'][0]
            raw = (content['text'].encode('utf-8') if 'text' in content
                   else base64.b64decode(content['blob']))
            self.assertEqual(item['size'], len(raw))
            self.assertEqual(item['digest'], 'sha256:' + hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['resultType'], 'complete')
        self.assertEqual(self.plane.read_resource(URI), self.markdown)

    def test_resource_listing_supports_non_skills_clients(self):
        resources = self.rpc('resources/list')['result']['resources']
        skill = next(r for r in resources if r['uri'] == URI)
        self.assertEqual(skill['name'], 'project-intelligence')
        self.assertEqual(skill['description'], 'Test workflow')
        self.assertEqual(skill['mimeType'], 'text/markdown')
        legacy_uri = 'project-intelligence://skills/project-intelligence/1.4.0/SKILL.md'
        self.assertEqual(self.plane.read_resource(legacy_uri), self.markdown)

    def test_unknown_skills_files_and_cursors_are_invalid_params(self):
        for method, params in [
            ('skills/get', {'uri': 'skill://missing/SKILL.md'}),
            ('skills/get', {'uri': 'skill://project-intelligence/assets/sample.bin'}),
            ('skills/get', {}), ('skills/get', {'uri': 5}),
            ('skills/list', {'cursor': 'made-up'}),
            ('resources/read', {'uri': 'skill://project-intelligence/../secret'}),
            ('resources/read', {'uri': 'skill://project-intelligence/%2e%2e/secret'}),
            ('resources/read', {'uri': 'skill://project-intelligence/unknown.md'}),
        ]:
            with self.subTest(method=method, params=params):
                response = self.rpc(method, **params)
                self.assertEqual(response.get('error', {}).get('code'), -32602)

    def test_snapshot_preserves_manifest_bytes_after_files_change(self):
        entry = self.rpc('skills/get', uri=URI)['result']['skill']
        (self.skill / 'SKILL.md').write_bytes(b'changed')
        self.assertEqual(self.plane.read_resource(URI), self.markdown)
        self.assertEqual(self.rpc('skills/get', uri=URI)['result']['skill'], entry)

    def test_bundle_frontmatter_without_optional_yaml(self):
        original_import = __import__
        def without_yaml(name, *args, **kwargs):
            if name == 'yaml':
                raise ImportError('optional YAML unavailable')
            return original_import(name, *args, **kwargs)
        with mock.patch('builtins.__import__', side_effect=without_yaml):
            plane = SkillDistributionPlane(skills_root=ROOT / 'distribution/skills')
            reply = self.server.handle_jsonrpc(
                {'id': 1, 'method': 'skills/get', 'params': {'uri': URI}}, skill_plane=plane,
            )
        entry = reply['result']['skill']
        self.assertEqual(entry['frontmatter']['metadata']['version'], '1.4.0')
        self.assertEqual(entry['frontmatter']['metadata']['mcp-api'], '>=1.3.0 <2.0.0')
        self.assertEqual(entry['frontmatter']['license'], 'Apache-2.0')

    def test_stdlib_frontmatter_refuses_ambiguous_yaml_instead_of_changing_types(self):
        original_import = __import__
        def without_yaml(name, *args, **kwargs):
            if name == 'yaml':
                raise ImportError('optional YAML unavailable')
            return original_import(name, *args, **kwargs)
        for extra in ['enabled: on', 'empty:', 'value: .nan']:
            with self.subTest(extra=extra):
                (self.skill / 'SKILL.md').write_bytes(self.markdown.replace(
                    b'license: Apache-2.0', ('license: Apache-2.0\n' + extra).encode(),
                ))
                with mock.patch('builtins.__import__', side_effect=without_yaml):
                    with self.assertRaises(SkillDistributionError):
                        SkillDistributionPlane(skills_root=self.root)

    def test_stdio_discovery_and_direct_get_without_listing(self):
        requests = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'server/discover'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'skills/get', 'params': {'uri': URI}},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'resources/read', 'params': {'uri': URI}},
        ]
        output = io.StringIO()
        self.server.serve_stdio_fallback(
            in_stream=io.StringIO('\n'.join(map(json.dumps, requests)) + '\n'),
            out_stream=output, skill_plane=self.plane,
        )
        responses = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(responses[1]['result']['skill']['uri'], URI)
        self.assertEqual(responses[2]['result']['contents'][0]['text'].encode(), self.markdown)

    @unittest.skipUnless(hasattr(__import__('os'), 'symlink'), 'symlinks unavailable')
    def test_symlinked_file_or_directory_never_enters_catalog(self):
        outside = self.root / 'outside'
        outside.mkdir()
        (outside / 'private.md').write_text('private')
        try:
            (self.skill / 'linked').symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest('symlink creation not permitted')
        with self.assertRaises(SkillDistributionError):
            SkillDistributionPlane(skills_root=self.root)

    def test_modern_requests_validate_metadata_and_report_unsupported_version(self):
        response = self.server.handle_jsonrpc({
            'id': 1, 'method': 'skills/list', 'params': {'_meta': {
                'io.modelcontextprotocol/protocolVersion': '2099-01-01',
            }},
        }, skill_plane=self.plane)
        self.assertEqual(response['error']['code'], -32022)
        self.assertIn('2026-07-28', response['error']['data']['supported'])
        self.assertEqual(response['error']['data']['requested'], '2099-01-01')
        response = self.server.handle_jsonrpc({
            'id': 1, 'method': 'skills/list', 'params': {'_meta': {
                'io.modelcontextprotocol/protocolVersion': '2026-07-28',
            }},
        }, skill_plane=self.plane)
        self.assertEqual(response['error']['code'], -32602)
        tools = self.rpc('tools/list')['result']
        self.assertEqual(tools['resultType'], 'complete')
        self.assertEqual(tools['cacheScope'], 'private')
        self.assertIn('io.modelcontextprotocol/serverInfo', tools['_meta'])

    def test_skill_size_and_count_limits_fail_closed(self):
        huge = self.skill / 'huge.bin'
        with huge.open('wb') as stream:
            stream.truncate(16 * 1024 * 1024)
        with self.assertRaises(SkillDistributionError):
            SkillDistributionPlane(skills_root=self.root)
        huge.unlink()
        for i in range(510):
            (self.skill / f'file-{i}.md').write_text('support')
        with self.assertRaises(SkillDistributionError):
            SkillDistributionPlane(skills_root=self.root)

    def test_missing_plane_does_not_claim_extension(self):
        response = self.server.handle_jsonrpc({'id': 1, 'method': 'initialize'})
        self.assertNotIn(EXTENSION, response['result']['capabilities'].get('extensions', {}))

    def test_target_cannot_shadow_installed_server_skill(self):
        target = self.root / 'target'
        fake = target / 'distribution/skills/project-intelligence'
        fake.mkdir(parents=True)
        (fake / 'SKILL.md').write_text('untrusted project instructions')
        self.assertEqual(_resolve_skills_root(target), ROOT / 'distribution/skills')
