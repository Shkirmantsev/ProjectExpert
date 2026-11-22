"""Lossless legacy decoding without rewriting bytes or rebuilding unrelated sources."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from pi_platform.core.canonical.value_types import Source, Metadata
from pi_platform.adapters.ingest.local_pipeline_driver import LocalPipelineDriver
from pi_platform.adapters.fs.local_source_adapter import LocalSourceAdapter
from pi_platform.ports.ingest.source_adapter import SourceAdapterContext, SourceAdapterError


class SourceDecodingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def policy(self, rules):
        from pi_platform.core.ingest.source_decoding_policy import SourceDecodingPolicy
        return SourceDecodingPolicy.from_dict({'schema_version': 1, 'rules': rules})

    def source(self, name, text, encoding):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = text.encode(encoding)
        path.write_bytes(raw)
        return Source('repo:' + name, str(path), 'plain_text', hashlib.sha256(raw).hexdigest(),
                      Metadata(documentId='repo:' + name, version='1', language='und', sourcePath=name, extensions={'portable_identity': 'v2'}))

    def test_sql_german_cyrillic_and_japanese_decode_losslessly(self):
        for codec, text in [('cp1252', 'äöüß€'), ('cp1251', 'Україна Київ'), ('shift_jis', '日本語')]:
            with self.subTest(codec=codec):
                policy = self.policy([{'pattern': '**/*.sql', 'encoding': codec}])
                source = self.source('db/history.sql', text, codec)
                before = Path(source.uri).read_bytes()
                context = SourceAdapterContext(self.root, metadata_overrides={'decoding_policy': policy})
                result = LocalSourceAdapter().parse(source, context)
                chunk = result.sections[0].chunks[0]
                self.assertEqual(chunk.rawText, text)
                self.assertEqual(chunk.metadata.extensions['textDecoding']['replacementCount'], 0)
                self.assertEqual(Path(source.uri).read_bytes(), before)

    def test_windows_code_pages_are_detected_without_rules(self):
        from pi_platform.core.ingest.records import read_text_with_provenance

        for codec, text in [('cp1251', "select 'Повернення платежу, Київ';"),
                            ('cp1252', "select 'Grüße €';")]:
            for filename in ('old.sql', 'old.txt'):
                with self.subTest(codec=codec, filename=filename):
                    source = self.source(filename, text, codec)
                    chunk = LocalSourceAdapter().parse(source).sections[0].chunks[0]
                    self.assertEqual(chunk.rawText, text)
                    self.assertEqual(chunk.metadata.extensions['textDecoding']['encoding'], codec)
                    self.assertEqual(chunk.metadata.extensions['textDecoding']['provenance'], 'automatic-fallback')
                    self.assertEqual(Path(source.uri).read_bytes(), text.encode(codec))
        long_sql = '-- ASCII header\n' * 2048 + "select 'Повернення платежу';"
        source = self.source('large.sql', long_sql, 'cp1251')
        self.assertEqual(read_text_with_provenance(source.uri, automatic=True)[0], long_sql)
        from dataclasses import replace
        from pi_platform.adapters.html.html_adapter import HtmlAdapter
        from pi_platform.adapters.java.java_structured_adapter import JavaStructuredAdapter
        from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter

        for adapter, filename, body in (
            (HtmlAdapter(), 'manual.html', '<p>Повернення платежу</p>'),
            (MarkdownAdapter(), 'manual.md', '# Довідка\nПовернення платежу'),
            (JavaStructuredAdapter(), 'Order.java', 'class Order { String label = "Повернення платежу"; }'),
        ):
            with self.subTest(filename=filename):
                source = replace(self.source(filename, body, 'cp1251'), family=adapter.family.value)
                parsed = adapter.parse(source)
                self.assertTrue(any('Повернення платежу' in chunk.rawText
                                    for section in parsed.sections for chunk in section.chunks))
        path = self.root / 'bad.sql'
        for raw in (b'\xff\xff\xff', b'abc\x00binary', b'\xff\xfe\x01'):
            path.write_bytes(raw)
            with self.assertRaises(SourceAdapterError):
                read_text_with_provenance(path, automatic=True)

    def test_utf8_and_bom_precede_legacy_fallback(self):
        from pi_platform.core.ingest.records import read_text_with_provenance
        policy = self.policy([{'pattern': '*.sql', 'encoding': 'cp1251'}])
        for codec in ('utf-8', 'utf-16', 'utf-32'):
            source = self.source('x.sql', 'Grüße Україна 日本語', codec)
            text, info = read_text_with_provenance(source.uri, automatic=True, source_path='x.sql', encoding_policy=policy)
            self.assertEqual(text, 'Grüße Україна 日本語')
            self.assertEqual(info['replacementCount'], 0)

    def test_conflicts_unsafe_paths_unknown_codecs_and_binary_rejected(self):
        from pi_platform.core.ingest.records import read_text_with_provenance
        with self.assertRaises(ValueError):
            self.policy([{'pattern': '../*.sql', 'encoding': 'cp1252'}])
        with self.assertRaises(ValueError):
            self.policy([{'pattern': '*.sql', 'encoding': 'unicode_escape'}])
        policy = self.policy([{'pattern': '**/*.sql', 'encoding': 'cp1252'},
                              {'pattern': 'db/*', 'encoding': 'cp1251'}])
        with self.assertRaises(ValueError):
            policy.profile('db/x.sql')
        for raw in (b'bad\x81', b'bad\x00', b'\xff\xfe\x01'):
            path = self.root / 'x.sql'; path.write_bytes(raw)
            with self.assertRaises(SourceAdapterError):
                read_text_with_provenance(path, source_path='x.sql',
                    encoding_policy=self.policy([{'pattern': '*.sql', 'encoding': 'cp1252'}]))

    def test_only_matching_pipeline_keys_change_and_portable_identity_is_bound(self):
        a = self.source('a.sql', 'select 1', 'utf-8')
        b = self.source('b.sql', 'select 2', 'utf-8')
        old = LocalPipelineDriver()
        new = LocalPipelineDriver(decoding_policy=self.policy([{'pattern': 'a.sql', 'encoding': 'cp1252'}]))
        self.assertNotEqual(old.pipeline_key(a), new.pipeline_key(a))
        self.assertEqual(old.pipeline_key(b), new.pipeline_key(b))

    def test_admin_preview_before_save_and_no_agent_permission(self):
        from pi_platform.adapters.ui.retrieval_admin_routes import RetrievalAdminRoutes, create_dispatcher
        source = self.source('db/a.sql', 'Grüße', 'cp1252')
        route = '/api/v1/admin/source-encodings'
        policy = {'schema_version': 1, 'rules': [{'pattern': 'db/*.sql', 'encoding': 'cp1252'}]}
        dispatch = create_dispatcher(RetrievalAdminRoutes(target_repo=self.root))
        preview = dispatch('POST', route, policy)
        self.assertIsNotNone(preview)
        self.assertEqual(preview.status, 200)
        self.assertEqual(preview.body['matched'], 1)
        self.assertEqual(preview.body['failed'], 0)
        destination = self.root / '.project-intelligence-cache/config/source-encodings.json'
        self.assertFalse(destination.exists())
        self.assertEqual(dispatch('PUT', route, policy).status, 200)
        self.assertTrue(destination.exists())
        self.assertEqual(Path(source.uri).read_bytes(), 'Grüße'.encode('cp1252'))
        denied = create_dispatcher(RetrievalAdminRoutes(target_repo=self.root, caller_capability_provider=lambda: 'coding-agent'))
        self.assertEqual(denied('PUT', route, policy).status, 403)

    def test_resumable_automatic_decoding_reuses_cache_and_respects_an_override(self):
        import json
        from tests.test_portable_canonical_sync import PortableProductionTests
        fixture = PortableProductionTests('test_cold_clone_skips_parser_and_document_embedding_and_queries')
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        bad = fixture.root / 'legacy.sql'
        original = "select 'Повернення платежу';".encode('cp1251')
        bad.write_bytes(original)
        (fixture.root / 'unicode.sql').write_text('select \'Україна 日本語\';', encoding='utf-8')
        automatic = fixture.build()
        fixture.publish_runtime(automatic)
        self.assertEqual(automatic.extra['source_coverage'], {'eligible': 4, 'indexed': 4, 'skipped': 0})
        self.assertTrue(any('Повернення платежу' in hit.snippet
                            for hit in automatic.extra['chunk_catalog'].values()))
        self.assertEqual(automatic.extra['source_failures'], [])
        policy_path = fixture.cache() / 'config/source-encodings.json'
        policy_path.parent.mkdir(parents=True, exist_ok=True)
        policy_path.write_text(json.dumps({'schema_version': 1, 'rules': [{'pattern': 'legacy.sql', 'encoding': 'cp1251'}]}))
        runtime = fixture.build()
        fixture.publish_runtime(runtime)
        self.assertEqual(runtime.extra['source_parse_misses'], 1)
        self.assertEqual(runtime.extra['source_parse_hits'], 3)
        self.assertEqual(runtime.extra['source_failures'], [])
        warm = fixture.build()
        self.assertEqual(warm.extra['source_parse_misses'], 0)
        self.assertEqual(warm.extra['indexing_report'].embedded_count, 0)
        self.assertEqual(bad.read_bytes(), original)
        policy_path.unlink()
        restored = fixture.build()
        self.assertEqual(restored.extra['source_parse_misses'], 0)
        self.assertEqual(restored.extra['source_parse_hits'], 4)

    def test_reviewed_legacy_java_reaches_real_pinned_worker(self):
        import importlib.util
        if not importlib.util.find_spec('tree_sitter_java'):
            self.skipTest('Pinned production Java bindings required; run in production image')
        from dataclasses import replace
        from pi_platform.adapters.java.java_structured_adapter import JavaStructuredAdapter
        from pi_platform.adapters.java.parser_subprocess import TreeSitterJavaSubprocess
        source = replace(self.source('Grüße.java', 'class Beispiel { String ort = "Grüße äöüß€"; }', 'cp1252'), family='java_source')
        context = SourceAdapterContext(self.root, metadata_overrides={'decoding_policy': self.policy([{'pattern': '*.java', 'encoding': 'cp1252'}])})
        result = JavaStructuredAdapter(TreeSitterJavaSubprocess(required=True)).parse(source, context)
        self.assertTrue(result.entities)
        self.assertEqual(result.document.metadata.extensions['textDecoding']['encoding'], 'cp1252')
        self.assertTrue(any('Grüße' in c.rawText for s in result.sections for c in s.chunks))

    def test_portable_restore_does_not_accept_different_private_decoder(self):
        import json
        from tests.test_portable_canonical_sync import PortableProductionTests, git
        fixture = PortableProductionTests('test_cold_clone_skips_parser_and_document_embedding_and_queries')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        (fixture.root / 'legacy.sql').write_bytes('select \'Grüße\';'.encode('cp1252'))
        git(fixture.root, 'add', 'legacy.sql'); git(fixture.root, 'commit', '-m', 'legacy fixture')
        policy = {'schema_version': 1, 'rules': [{'pattern': 'legacy.sql', 'encoding': 'cp1252'}]}
        path = fixture.cache() / 'config/source-encodings.json'
        path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(policy))
        runtime = fixture.build(); fixture.publish_runtime(runtime)
        fixture.publish(fixture.stage(vectors=True))
        clone = fixture.clone()
        automatic = fixture.build(clone)
        self.assertEqual(automatic.extra['source_parse_misses'], 1)
        self.assertTrue(any(hit.metadata.extensions.get('textDecoding', {}).get('provenance') == 'automatic-fallback'
                            for hit in automatic.extra['chunk_catalog'].values()))
        path = fixture.cache(clone) / 'config/source-encodings.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        policy['rules'][0]['encoding'] = 'cp1251'; path.write_text(json.dumps(policy))
        changed = fixture.build(clone)
        self.assertEqual(changed.extra['source_parse_misses'], 1)
        self.assertEqual(changed.extra['source_parse_hits'], 2)

    def test_inbox_cli_uses_same_policy_and_checks_compatibility_on_repeat(self):
        import argparse
        import json
        from contextlib import redirect_stdout
        from io import StringIO
        from pi_platform.cli.main import _cmd_ingest_sources
        self.source('tmp/local/source/legacy.sql', 'Grüße', 'cp1252')
        cache = self.root / '.project-intelligence-cache'
        policy_file = cache / 'config/source-encodings.json'
        policy_file.parent.mkdir(parents=True)
        policy = {'schema_version': 1, 'rules': [{'pattern': '**/*.sql', 'encoding': 'cp1252'}]}
        policy_file.write_text(json.dumps(policy))
        args = argparse.Namespace(target=self.root, config=None, inbox=None, cache_root=cache)
        with redirect_stdout(StringIO()):
            self.assertEqual(_cmd_ingest_sources(args), 0)
            policy['rules'][0]['encoding'] = 'cp1251'
            policy_file.write_text(json.dumps(policy))
            self.assertEqual(_cmd_ingest_sources(args), 0)
        records = json.loads((cache / 'ingestion.json').read_text(encoding='utf-8'))
        self.assertIn('source-decoding/v1:cp1251', json.dumps(records))
