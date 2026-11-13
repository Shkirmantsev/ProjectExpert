"""Public coordinator contracts across interruption, metadata and migration."""
from dataclasses import replace
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.core.control.retrieval_settings import RetrievalSettings
from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
from pi_platform.core.orchestration.repository_indexing import index_repository
from pi_platform.adapters.runtime.sqlite_ingestion_cache import indexing_progress
from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery


class ResumableRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / '.project-intelligence-cache'
        env = patch.dict(os.environ, {'PI_STARTUP_PROFILE': 'minimal', 'PI_EMBEDDING_MODEL': 'hashing',
            'PI_DENSE_INDEX': 'flat', 'PI_DOCLING_ENABLED': '0', 'PI_INDEX_ENGINE': 'resumable',
            'PI_INDEX_PARALLEL': '1', 'PI_EMBED_BATCHING': '1'})
        env.start()
        self.addCleanup(env.stop)
        (self.root / 'billing.md').write_text('# Billing\nRefund customer payments safely\n')
        (self.root / 'shipping.md').write_text('# Shipping\nParcel dispatch tracking\n')

    def build(self, inventory=None):
        return index_repository(target=self.root, cache_root=self.cache,
            inventory=inventory or RepositorySourceDiscovery().discover(self.root),
            previous_inventory=None, settings=RetrievalSettings())

    def test_fresh_fallback_defaults_build_resumable_without_flags(self):
        for key in ('PI_INDEX_ENGINE', 'PI_INDEX_PARALLEL', 'PI_EMBED_BATCHING'):
            os.environ.pop(key, None)
        runtime = self.build()
        self.assertTrue((self.cache / 'indexing-state.sqlite').is_file())
        self.assertFalse((self.cache / 'ingestion.json').exists())
        self.assertTrue(runtime.extra['chunk_ids'])
        self.assertEqual(indexing_progress(self.cache / 'indexing-state.sqlite')['state'], 'ready')
        from pi_platform.adapters.ui.composition import PublishedRetrieval
        published = PublishedRetrieval(None)
        published.runtime = runtime
        self.assertEqual(published.stats()['index_engine'], 'resumable')

    def test_dense_failure_does_not_lose_completed_parsing(self):
        with patch('pi_platform.core.orchestration.repository_indexing._index_dense_generation',
                   side_effect=RuntimeError('model interrupted')):
            with self.assertRaisesRegex(RuntimeError, 'model interrupted'):
                self.build()
        self.assertEqual(indexing_progress(self.cache / 'indexing-state.sqlite')['state'], 'failed')
        with patch('pi_platform.adapters.markdown.markdown_adapter.MarkdownAdapter.parse',
                   side_effect=AssertionError('completed source reparsed')):
            runtime = self.build()
        self.assertTrue(runtime.extra['chunk_ids'])
        self.assertFalse((self.cache / 'ingestion.json').exists())
        self.assertEqual(indexing_progress(self.cache / 'indexing-state.sqlite')['state'], 'ready')

    def test_metadata_change_updates_canonical_projection_without_address_collision(self):
        first = self.build()
        inventory = RepositorySourceDiscovery().discover(self.root)
        changed = replace(inventory, entries=tuple(replace(e, policy='LOCAL_ONLY') for e in inventory.entries))
        second = self.build(changed)
        self.assertEqual(first.extra['chunk_ids'], second.extra['chunk_ids'])
        self.assertTrue(all(hit.metadata.policy == 'LOCAL_ONLY' for hit in second.extra['chunk_catalog'].values()))
        source_stage = next(stage for stage in indexing_progress(self.cache / 'indexing-state.sqlite')['stages'] if stage['stage'] == 'sources')
        self.assertEqual(source_stage['degraded_items'], 0)  # Privacy policy is not parser degradation.
        self.assertTrue(all(hit.metadata.policy != 'LOCAL_ONLY' for hit in first.extra['chunk_catalog'].values()))

    def test_legacy_migration_equivalent_and_preserves_original(self):
        inventory = RepositorySourceDiscovery().discover(self.root)
        with patch.dict(os.environ, {'PI_INDEX_ENGINE': 'legacy'}):
            legacy = self.build(inventory)
        old = (self.cache / 'ingestion.json').read_bytes()
        migrated = self.build(inventory)
        self.assertEqual((self.cache / 'ingestion.json').read_bytes(), old)
        self.assertEqual((self.cache / 'ingestion.pre-resumable.json').read_bytes(), old)
        self.assertEqual(migrated.extra['chunk_ids'], legacy.extra['chunk_ids'])
        self.assertEqual(migrated.extra['source_generation'], legacy.extra['source_generation'])
        self.assertEqual(migrated.extra['source_inventory'], legacy.extra['source_inventory'])
        self.assertEqual(migrated.extra['indexing_report'].embedded_count, 0)
        self.assertEqual(migrated.extra['chunk_catalog'], legacy.extra['chunk_catalog'])

    def test_failed_candidate_does_not_damage_prior_queries(self):
        runtime = self.build()
        expected = runtime.multi_stage_retrieval.retrieve(RetrievalQuery('refund')).hits
        self.assertTrue(expected)
        (self.root / 'billing.md').write_bytes(b'\x00binary')
        with self.assertRaisesRegex(RuntimeError, 'Incomplete ingestion'):
            self.build()
        self.assertEqual(runtime.multi_stage_retrieval.retrieve(RetrievalQuery('refund')).hits, expected)

    def test_changed_and_deleted_sources_are_absent_from_candidate(self):
        old = self.build()
        previous = {cid for cid, hit in old.extra['chunk_catalog'].items() if hit.metadata.sourcePath == 'shipping.md'}
        (self.root / 'shipping.md').unlink()
        (self.root / 'billing.md').write_text('# Billing\nAn entirely different voucher\n')
        new = self.build()
        self.assertFalse(previous & set(new.extra['chunk_ids']))
        self.assertFalse(new.multi_stage_retrieval.retrieve(RetrievalQuery('parcel')).hits)

    def test_unsupported_image_blocks_complete_candidate(self):
        (self.root / 'photo.png').write_bytes(b'pixels')
        with self.assertRaisesRegex(RuntimeError, 'Incomplete ingestion'):
            self.build()

    def test_new_builder_fences_prior_candidate_before_publication(self):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import candidate_publication, IndexingStateError
        old = self.build()
        new = self.build()
        with self.assertRaisesRegex(IndexingStateError, 'Stale'):
            with candidate_publication(self.cache, old):
                self.fail('stale publication entered')
        with candidate_publication(self.cache, new):
            pass
        self.assertEqual(indexing_progress(self.cache / 'indexing-state.sqlite')['state'], 'published')

    def test_artifact_mutation_blocks_publication_and_active_pointer_is_retained(self):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import candidate_publication, IndexingStateError
        from contextlib import closing
        first = self.build()
        with candidate_publication(self.cache, first):
            pass
        second = self.build()
        with closing(sqlite3.connect(self.cache / 'indexing-state.sqlite')) as db:
            relative = db.execute("SELECT relative_path FROM artifact_manifests WHERE generation=? AND artifact_name='exact'",
                                  (second.extra['index_job_id'],)).fetchone()[0]
        path = self.cache / relative
        original = path.read_bytes()
        try:
            path.write_bytes(b'damaged')
            with self.assertRaisesRegex(IndexingStateError, 'artifact checksum'):
                with candidate_publication(self.cache, second):
                    self.fail('damaged candidate published')
        finally:
            path.write_bytes(original)
        with closing(sqlite3.connect(self.cache / 'indexing-state.sqlite')) as db:
            self.assertEqual(db.execute("SELECT value FROM schema_meta WHERE key='active_job'").fetchone()[0], first.extra['index_job_id'])
        with candidate_publication(self.cache, second):
            pass
        with closing(sqlite3.connect(self.cache / 'indexing-state.sqlite')) as db:
            self.assertEqual(db.execute("SELECT value FROM schema_meta WHERE key='previous_job'").fetchone()[0], first.extra['index_job_id'])

    def test_failed_caller_publication_retains_prepared_intent(self):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import candidate_publication
        from contextlib import closing
        runtime = self.build()
        with self.assertRaisesRegex(OSError, 'snapshot commit failure'):
            with candidate_publication(self.cache, runtime):
                raise OSError('snapshot commit failure')
        with closing(sqlite3.connect(self.cache / 'indexing-state.sqlite')) as db:
            self.assertEqual(db.execute('SELECT state FROM publication_intents WHERE job_id=?',
                (runtime.extra['index_job_id'],)).fetchone()[0], 'prepared')
        with candidate_publication(self.cache, runtime):
            pass
        with closing(sqlite3.connect(self.cache / 'indexing-state.sqlite')) as db:
            self.assertEqual(db.execute('SELECT state FROM publication_intents WHERE job_id=?',
                (runtime.extra['index_job_id'],)).fetchone()[0], 'committed')

    def test_status_available_before_first_publication(self):
        self.build()
        from pi_platform.adapters.ui.composition import PublishedRetrieval
        status = PublishedRetrieval(None, indexing_state_path=self.cache / 'indexing-state.sqlite').stats()
        self.assertEqual(status['indexing_progress']['state'], 'ready')
        self.assertIn('sources', {s['stage'] for s in status['indexing_progress']['stages']})


if __name__ == '__main__':
    unittest.main()
