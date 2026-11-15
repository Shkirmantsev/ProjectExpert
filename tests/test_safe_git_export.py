"""Safe source isolation through real SQLite, signed writer and Git fixtures."""
from contextlib import closing
import json
import os
import sqlite3
from dataclasses import replace
from unittest.mock import patch

from tests.test_portable_canonical_sync import PortableProductionTests, git
from pi_platform.adapters.sync.portable_snapshot_reader import verified_snapshot


# Deterministic recognizer fixtures below are deliberately invalid test markers,
# never credentials. They must remain readable to test outward admission.
class SafeExportTests(PortableProductionTests):
    def test_payload_fixture_closes_its_real_database_handle(self):
        self.publish_runtime(self.build())
        connect, opened = sqlite3.connect, []
        def tracked(*args, **kwargs):
            connection = connect(*args, **kwargs)
            opened.append(connection)
            self.addCleanup(connection.close)
            return connection
        with patch('sqlite3.connect', tracked):
            self.replace_source_payload('repo:billing.md', lambda body: body['metadata'].setdefault('extensions', {}).update(
                fixture='connection-lifecycle'))
        self.assertTrue(opened)
        for connection in opened:
            with self.assertRaises(sqlite3.ProgrammingError):
                connection.execute('SELECT 1')
    def test_image_projection_change_recomputes_only_image_vector(self):
        from pi_platform.core.orchestration.repository_indexing import build_production_retrieval_runtime
        def runtime(**kwargs):
            kwargs['embedding_alias'] = 'hashing'
            return build_production_retrieval_runtime(**kwargs)
        (self.root / 'diagram.png').write_bytes(b'fixture pixels')
        with patch.dict(os.environ, {'PI_EMBEDDING_MODEL': 'gemma'}), patch(
                'pi_platform.core.orchestration.repository_indexing.build_production_retrieval_runtime', runtime):
            self.build()
            with patch('pi_platform.adapters.sync.portable_media.IMAGE_PROJECTION', 'gemma-image-v2-fixture'):
                changed = self.build()
        self.assertEqual(changed.extra['source_parse_misses'], 0)
        self.assertEqual(changed.extra['indexing_report'].embedded_count, 1)
    def test_legacy_signed_writer_also_filters_secret_derivatives(self):
        from pi_platform.core.canonical.value_types import Source, RuntimeChange
        from pi_platform.ports import ApprovalRequest
        detector_fixture = 'ghp_' + 'P' * 40
        source = Source(id='source', uri='billing.md', family='markdown', contentHash='a' * 64)
        changes = [RuntimeChange(id='unsafe', kind='chunk', source=source,
                       payload={'kind': 'chunk', 'family': 'markdown', 'id': 'unsafe', 'text': detector_fixture}),
                   RuntimeChange(id='safe', kind='chunk', source=source,
                       payload={'kind': 'chunk', 'family': 'markdown', 'id': 'safe', 'text': 'Public fact'})]
        token = self.boundary.issue(ApprovalRequest(action='materialise', repo_root=str(self.root),
                                                    change_ids=('safe', 'unsafe')))
        report = self.materialise.materialise_durable_changes(self.root, cache_root=self.cache(),
            approval_token=token, changes=changes)
        self.assertTrue(any('safe.json' in item.path for item in report.diff_files))
        for path in (self.root / 'project-knowledge').rglob('*'):
            if path.is_file():
                self.assertNotIn(detector_fixture.encode(), path.read_bytes())
    def test_generated_wiki_credentials_never_reach_preview_or_git_files(self):
        from pi_platform.core.wiki.llm_wiki import LlmWiki, LlmWikiError
        wiki = LlmWiki(self.root)
        detector_fixture = 'ghp_' + 'K' * 40
        for preview in (True, False):
            with self.subTest(preview=preview), self.assertRaises(LlmWikiError):
                wiki.write_page(relative_path='unsafe', title='Derived note', body=detector_fixture, dry_run=preview)
        self.assertFalse((wiki.root / 'unsafe.md').exists())
    def test_protected_parser_diagnostics_do_not_leak_credentials_or_paths(self):
        from pi_platform.adapters.ingest.local_pipeline_driver import LocalPipelineDriver
        from pi_platform.core.canonical.value_types import Source, Metadata
        from pi_platform.ports.ingest.source_adapter import SourceAdapterError
        from pi_platform.adapters.sync.portable_format import sha
        path = self.root / 'protected-diagnostic.md'
        path.write_text('private source')
        source = Source(id='repo:protected-diagnostic.md', uri=str(path), family='markdown',
            contentHash=sha(path.read_bytes()), metadata=Metadata(documentId='repo:protected-diagnostic.md',
                sourcePath='protected-diagnostic.md', version='1', language='en', policy='LOCAL_ONLY'))
        for error in (SourceAdapterError('password=private-fixture-value'), RuntimeError('password=private-fixture-value')):
            with self.subTest(error=type(error).__name__), patch(
                    'pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse', side_effect=error), self.assertLogs(
                    'pi_platform.adapters.ingest.local_pipeline_driver', level='WARNING') as captured:
                report = LocalPipelineDriver().run(source, self.root)
            self.assertFalse(report.ok)
            text = '\n'.join(captured.output) + report.error_message
            self.assertNotIn('private-fixture-value', text)
            self.assertNotIn('protected-diagnostic.md', text)
    def test_untracked_text_is_not_assumed_shareable(self):
        (self.root / 'local-notes.md').write_text('# Private business notes\nInternal planning')
        self.publish_runtime(self.build())
        proposal = self.stage()
        self.assertEqual(proposal['sources'], 2)
        self.assertEqual(proposal['excludedReasonCounts'], {'untracked-source': 1})

    def test_vector_export_does_not_open_a_database_per_chunk(self):
        from contextlib import contextmanager
        from pi_platform.adapters.runtime.sqlite_vector_record_store import SqliteVectorRecordStore
        self.publish_runtime(self.build())
        original = SqliteVectorRecordStore._connection
        opened = []
        @contextmanager
        def counted(store):
            opened.append(True)
            with original(store) as connection:
                yield connection
        with patch.object(SqliteVectorRecordStore, '_connection', counted):
            proposal = self.stage(vectors=True)
        self.assertEqual(proposal['sources'], 2)
        self.assertLessEqual(len(opened), 1, 'Vector export opened a connection per chunk')
    def replace_source_payload(self, sid, modify):
        from pi_platform.adapters.sync.portable_format import encode, sha
        with closing(sqlite3.connect(self.cache() / 'indexing-state.sqlite')) as db, db:
            row = db.execute('''SELECT o.source_hash,o.pipeline_key,o.metadata_key,o.summary_json
                FROM source_outputs o JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
                WHERE g.generation=(SELECT value FROM schema_meta WHERE key='active_job') AND o.source_id=?''', (sid,)).fetchone()
            digest, key, metadata, summary = row
            summary = json.loads(summary)
            address = next(a for a in summary['addresses'] if 'rawText' in json.loads(db.execute(
                'SELECT payload FROM canonical_payloads WHERE address=?', (a,)).fetchone()[0]))
            value = json.loads(db.execute('SELECT payload FROM canonical_payloads WHERE address=?', (address,)).fetchone()[0])
            modify(value)
            raw = encode(value)
            new = sha(raw)
            db.execute('INSERT INTO canonical_payloads VALUES(?,?,?)', (new, raw, new))
            db.execute('UPDATE source_payload_membership SET address=? WHERE source_id=? AND source_hash=? AND pipeline_key=? AND metadata_key=? AND address=?',
                (new, sid, digest, key, metadata, address))
            summary['addresses'] = [new if a == address else a for a in summary['addresses']]
            raw = encode(summary)
            db.execute('UPDATE source_outputs SET summary_json=?,checksum=? WHERE source_id=? AND source_hash=? AND pipeline_key=? AND metadata_key=?',
                (raw, sha(raw), sid, digest, key, metadata))

    def test_transitive_derivative_and_vector_stay_local(self):
        detector_fixture = 'ghp_' + 'X' * 40
        (self.root / 'protected.md').write_text('# Protected\n' + detector_fixture)
        self.publish_runtime(self.build())
        self.replace_source_payload('repo:billing.md', lambda body: body['metadata'].setdefault('extensions', {}).update(
            derivedFrom=['repo:protected.md']))
        proposal = self.stage(vectors=True)
        self.assertEqual(proposal['sources'], 1)
        self.assertEqual(proposal['excludedSourceCount'], 2)
        self.publish(proposal)
        with verified_snapshot(self.root / 'project-knowledge', self.cache()) as (db, _):
            sources = [r[0] for r in db.execute("SELECT id FROM records WHERE kind='source'")]
            self.assertEqual(sources, ['repo:shipping.md'])
            self.assertEqual(db.execute("SELECT count(*) FROM records WHERE kind='vector'").fetchone()[0], 1)

    def test_old_now_protected_orphans_require_reviewed_cleanup(self):
        from pi_platform.adapters.sync.portable_format import ROOT, PortableSnapshotError
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        self.publish_runtime(self.build())
        self.publish(self.stage())
        previous = (self.root / 'project-knowledge' / ROOT).read_bytes()
        inventory = RepositorySourceDiscovery().discover(self.root)
        inventory = replace(inventory, entries=tuple(replace(e, policy='LOCAL_ONLY') if e.path == 'billing.md' else e for e in inventory.entries))
        self.publish_runtime(self.build(inventory=inventory))
        with patch.object(RepositorySourceDiscovery, 'discover', return_value=inventory):
            proposal = self.stage()
            self.assertEqual(proposal['sources'], 1)
            with self.assertRaisesRegex(PortableSnapshotError, 'cleanup'):
                self.publish(proposal)
        self.assertEqual(previous, (self.root / 'project-knowledge' / ROOT).read_bytes())

    def test_detector_failure_excludes_only_the_affected_source(self):
        self.publish_runtime(self.build())
        def detector(path):
            if path.name == 'billing.md':
                raise RuntimeError('private detector failure details')
            return False
        with patch('pi_platform.adapters.sync.safe_export_projector.sensitive_file', detector):
            proposal = self.stage()
        self.assertEqual(proposal['sources'], 1)
        self.assertNotIn('private detector failure', json.dumps(proposal))

    def test_unreviewed_media_stays_local_without_blocking_text(self):
        (self.root / 'screenshot.png').write_bytes(b'opaque compressed image')
        from pi_platform.core.orchestration.repository_indexing import build_production_retrieval_runtime
        def runtime(**kwargs):
            kwargs['embedding_alias'] = 'hashing'
            return build_production_retrieval_runtime(**kwargs)
        with patch.dict(os.environ, {'PI_EMBEDDING_MODEL': 'gemma'}), patch(
                'pi_platform.core.orchestration.repository_indexing.build_production_retrieval_runtime', runtime):
            built = self.build()
        self.publish_runtime(built)
        proposal = self.stage(vectors=True)
        self.assertEqual(proposal['sources'], 2)
        self.assertEqual(proposal['excludedReasonCounts'], {'media-review-required': 1})
        stage = self.cache() / 'portable-staging' / proposal['stagingId']
        for path in stage.rglob('*'):
            if path.is_file():
                self.assertNotIn(b'screenshot.png', path.read_bytes())

    def test_changed_security_review_invalidates_an_already_staged_proposal(self):
        from pi_platform.adapters.orchestration.knowledge_sync import KnowledgeSyncCoordinator
        from pi_platform.adapters.sync.portable_format import PortableSnapshotError
        self.publish_runtime(self.build())
        proposal = self.stage()
        KnowledgeSyncCoordinator(self.root, self.cache(), authenticated_operator=True).review_source('billing.md', 'confidential')
        with self.assertRaisesRegex(PortableSnapshotError, 'policy moved'):
            self.publish(proposal)
        self.assertFalse((self.root / 'project-knowledge').exists())

    def test_reindex_rejects_corrupt_git_cache_but_preserves_local_calculation(self):
        from pi_platform.adapters.sync.portable_format import PortableSnapshotError
        self.publish_runtime(self.build())
        self.publish(self.stage(vectors=True))
        shard = next((self.root / 'project-knowledge/objects/portable-v2').glob('*.jsonl'))
        shard.write_bytes(b'broken cache')
        with self.assertRaises(PortableSnapshotError):
            with verified_snapshot(self.root / 'project-knowledge', self.cache()):
                pass
        local = self.build()
        self.assertEqual(local.extra['portable_import']['state'], 'rejected-snapshot')
        self.assertEqual(local.extra['indexing_report'].embedded_count, 0)

    def test_nested_secret_metadata_is_rejected_per_source(self):
        import random
        for seed in range(5):
            with self.subTest(seed=seed):
                # Rebuild fresh immutable output before injecting each nested key.
                self.publish_runtime(self.build())
                rng = random.Random(seed)
                detector_fixture = 'sk-' + ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(40))
                self.replace_source_payload('repo:billing.md', lambda body: body['metadata'].setdefault('extensions', {}).update(
                    nested={'labels': [{'unexpected': detector_fixture}]}))
                proposal = self.stage()
                self.assertEqual(proposal['sources'], 1)
                for path in (self.cache() / 'portable-staging' / proposal['stagingId']).rglob('*'):
                    if path.is_file():
                        self.assertNotIn(detector_fixture.encode(), path.read_bytes())
    def test_image_source_is_durable_and_vector_restores_without_image_embedding(self):
        # Exercise the real multimodal orchestration/persistence with a tiny
        # deterministic model; physical Gemma inference is a separate gate.
        from pi_platform.core.orchestration.repository_indexing import build_production_retrieval_runtime
        def runtime(**kwargs):
            kwargs['embedding_alias'] = 'hashing'
            return build_production_retrieval_runtime(**kwargs)
        (self.root / 'diagram.png').write_bytes(b'fixture-image-pixels')
        git(self.root, 'add', 'diagram.png')
        git(self.root, 'commit', '-m', 'image fixture')
        with patch.dict(os.environ, {'PI_EMBEDDING_MODEL': 'gemma'}), patch(
                'pi_platform.core.orchestration.repository_indexing.build_production_retrieval_runtime', runtime):
            first = self.build()
            self.publish_runtime(first)
            from pi_platform.adapters.orchestration.knowledge_sync import KnowledgeSyncCoordinator
            KnowledgeSyncCoordinator(self.root, self.cache(), authenticated_operator=True).review_source('diagram.png', 'public')
            proposal = self.stage(vectors=True)
            self.assertEqual(proposal['sources'], 3)
            self.publish(proposal)
            clone = self.clone()
            with patch('pi_platform.adapters.retrieval.hashing_embedding_model.HashingEmbeddingAdapter.embed_request',
                       side_effect=AssertionError('image vector was recomputed')):
                restored = self.build(clone)
        self.assertEqual(restored.extra['portable_import']['importedSources'], 3)
        self.assertEqual(restored.extra['indexing_report'].embedded_count, 0)
        self.assertEqual(first.extra['chunk_ids'], restored.extra['chunk_ids'])
    def test_restore_only_full_clone_builds_query_index_without_model_calls(self):
        first = self.build()
        self.publish_runtime(first)
        self.publish(self.stage(vectors=True))
        clone = self.clone()
        from pi_platform.core.orchestration.repository_indexing import index_repository
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        from pi_platform.core.control.retrieval_settings import RetrievalSettings
        from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
        with patch('pi_platform.adapters.ingest.local_pipeline_driver.LocalPipelineDriver.run_many',
                   side_effect=AssertionError('restore scheduled parsers')), patch(
                   'pi_platform.adapters.retrieval.hashing_embedding_model.HashingEmbeddingAdapter.embed_request',
                   side_effect=AssertionError('restore called model')):
            restored = index_repository(target=clone, cache_root=self.cache(clone),
                inventory=RepositorySourceDiscovery().discover(clone), previous_inventory=None,
                settings=RetrievalSettings(), restore_only=True)
        self.assertEqual(restored.extra['indexing_report'].embedded_count, 0)
        self.assertTrue(restored.multi_stage_retrieval.retrieve(RetrievalQuery('refund')).hits)
    def test_secret_source_does_not_abort_unrelated_safe_export(self):
        detector_fixture = 'ghp_' + 'Z' * 36
        (self.root / 'protected.md').write_text('# Private\n' + detector_fixture)
        git(self.root, 'add', 'protected.md')
        git(self.root, 'commit', '-m', 'mixed source fixture')
        runtime = self.build()
        self.publish_runtime(runtime)
        proposal = self.stage(vectors=True)
        self.assertEqual(proposal['sources'], 2)
        self.assertEqual(proposal['excludedSourceCount'], 1)
        self.assertNotIn('protected.md', json.dumps(proposal))
        self.publish(proposal)
        for path in (self.root / 'project-knowledge').rglob('*'):
            if path.is_file():
                self.assertNotIn(detector_fixture.encode(), path.read_bytes())
                self.assertNotIn(b'protected.md', path.read_bytes())
        with verified_snapshot(self.root / 'project-knowledge', self.cache()) as (db, report):
            self.assertEqual(db.execute("SELECT count(*) FROM records WHERE kind='source'").fetchone()[0], 2)
            self.assertTrue(report['scope']['completeForExportableScope'])
        self.assertTrue(runtime.multi_stage_retrieval)

    def test_all_private_produces_no_public_snapshot(self):
        for path in ('billing.md', 'shipping.md'):
            (self.root / path).write_text('-----BEGIN PRIVATE KEY-----\nprivate fixture')
        runtime = self.build()
        self.publish_runtime(runtime)
        proposal = self.stage()
        self.assertEqual(proposal['state'], 'no-exportable-sources')
        self.assertNotIn('stagingId', proposal)
        self.assertFalse((self.root / 'project-knowledge').exists())

    def test_restore_only_missing_vectors_never_embeds_or_parses(self):
        from pi_platform.core.orchestration.repository_indexing import index_repository, RestoreRequiresReindex
        first = self.build()
        self.publish_runtime(first)
        self.publish(self.stage())
        clone = self.clone()
        from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
        from pi_platform.core.control.retrieval_settings import RetrievalSettings
        with patch('pi_platform.adapters.ingest.local_pipeline_driver.LocalPipelineDriver.run_many',
                   side_effect=AssertionError('restore ran parser scheduling')), patch(
                   'pi_platform.adapters.retrieval.hashing_embedding_model.HashingEmbeddingAdapter.embed_request',
                   side_effect=AssertionError('restore embedded')):
            with self.assertRaises(RestoreRequiresReindex):
                index_repository(target=clone, cache_root=self.cache(clone),
                    inventory=RepositorySourceDiscovery().discover(clone), previous_inventory=None,
                    settings=RetrievalSettings(), restore_only=True)


def load_tests(loader, tests, pattern):
    import unittest
    return unittest.TestSuite(SafeExportTests(name) for name in SafeExportTests.__dict__ if name.startswith('test_'))
