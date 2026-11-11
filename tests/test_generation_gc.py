"""Reachability retention and crash/replay against the actual durable schema."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from pi_platform.adapters.runtime.generation_gc import collect, disk_budget_metrics, JOURNAL
from pi_platform.adapters.runtime.sqlite_ingestion_cache import _SCHEMA, exclusive_indexer, IndexingStateError


class GenerationGCTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.path = self.root / 'indexing-state.sqlite'
        db = sqlite3.connect(self.path)
        db.executescript(_SCHEMA)
        db.execute('PRAGMA journal_mode=WAL')
        jobs = [('old-published', 'published', 'k', 100), ('previous', 'published', 'k', 200),
                ('active', 'published', 'k', 300), ('old-ready', 'ready', 'k', 400),
                ('new-ready', 'ready', 'k', 500), ('running', 'running', 'k', 9900),
                ('expired', 'interrupted', 'k', 100), ('incompatible', 'running', 'different', 9900)]
        for fence, (identity, state, compatibility, updated) in enumerate(jobs, 1):
            db.execute('INSERT INTO index_jobs VALUES(?,?,?,?,?,?,?)', (identity, compatibility, fence, state, None, updated, updated))
            address = 'shared' if identity in ('previous', 'active') else identity + '-payload'
            self.add_source(db, identity, address)
        self.add_source(db, 'fresh-orphan', 'fresh-orphan-payload', completed=9800, generation=None)
        self.add_source(db, 'expired-orphan', 'expired-orphan-payload', generation=None)
        db.execute("INSERT INTO schema_meta VALUES('active_job','active')")
        db.execute("INSERT INTO schema_meta VALUES('previous_job','previous')")
        db.commit()
        db.close()
        self.artifact = self.root / 'indexes' / 'unknown-old.ready'
        self.artifact.parent.mkdir()
        self.artifact.write_bytes(b'must never delete artifacts without reachability manifest')

    def add_source(self, db, identity, address, *, completed=100, generation='default'):
        payload = address.encode()
        summary = json.dumps({'addresses': [address]}).encode()
        db.execute('INSERT OR IGNORE INTO canonical_payloads VALUES(?,?,?)', (address, payload, hashlib.sha256(payload).hexdigest()))
        db.execute('INSERT INTO source_outputs VALUES(?,?,?,?,?,?,?,?,?)', (identity, 'hash', 'pipeline', 'metadata', summary, hashlib.sha256(summary).hexdigest(), completed, 1, 'complete'))
        db.execute('INSERT INTO source_payload_membership VALUES(?,?,?,?,?)', (identity, 'hash', 'pipeline', 'metadata', address))
        if generation is not None:
            db.execute('INSERT INTO generation_sources VALUES(?,?,?,?,?)', (identity if generation == 'default' else generation, identity, 'hash', 'pipeline', 'metadata'))

    def rows(self, table, column):
        db = sqlite3.connect(self.path)
        try:
            return {row[0] for row in db.execute('SELECT ' + column + ' FROM ' + table)}
        finally:
            db.close()

    def gc(self, **kwargs):
        return collect(self.root, now=10000, ttl_seconds=1000, **kwargs)

    def test_dry_run_plans_without_deleting_any_state(self):
        before = self.rows('index_jobs', 'job_id')
        result = self.gc()
        self.assertFalse(result['applied'])
        self.assertEqual(self.rows('index_jobs', 'job_id'), before)
        self.assertFalse((self.root / JOURNAL).exists())
        self.assertGreater(result['removed']['canonical_payloads'], 0)

    def test_two_published_generations_and_shared_payload_survive_reachability_gc(self):
        result = self.gc(apply=True, max_payload_bytes=1, min_free_bytes=2**63)
        keep = self.rows('generation_sources', 'generation')
        self.assertEqual(keep, {'active', 'previous', 'new-ready', 'running'})
        payloads = self.rows('canonical_payloads', 'address')
        self.assertIn('shared', payloads)
        self.assertIn('fresh-orphan-payload', payloads)
        self.assertNotIn('expired-orphan-payload', payloads)
        self.assertNotIn('expired-payload', payloads)
        self.assertTrue(self.artifact.exists())
        self.assertEqual(result['runtime_files_deleted'], 0)
        self.assertFalse(result['budget']['preflight_ok'])
        self.assertEqual(result['removed']['payload_bytes'], result['before']['payload_bytes'] - result['after']['payload_bytes'])
        self.assertIn('no VACUUM', result['reclaimed_bytes_kind'])

    def test_rollback_active_pointer_retains_old_active_in_addition_to_latest_published(self):
        db = sqlite3.connect(self.path)
        db.execute("UPDATE schema_meta SET value='old-published' WHERE key='active_job'")
        db.commit()
        db.close()
        result = self.gc(apply=True)
        self.assertTrue({'old-published', 'active', 'previous'} <= set(result['plan']['retained_jobs']))
        self.assertIn('old-published-payload', self.rows('canonical_payloads', 'address'))

    def test_prepared_publication_survives_pointer_commit_gap_and_incompatible_ttl(self):
        db = sqlite3.connect(self.path)
        db.execute("INSERT INTO publication_intents VALUES('incompatible',100,'prepared')")
        db.commit()
        db.close()
        result = self.gc(apply=True)
        self.assertIn('incompatible', result['plan']['retained_jobs'])
        self.assertIn('incompatible-payload', self.rows('canonical_payloads', 'address'))

    def test_unknown_generation_reachability_is_conservatively_retained(self):
        db = sqlite3.connect(self.path)
        self.add_source(db, 'unknown-source', 'unknown-payload', generation='unknown-generation')
        db.commit()
        db.close()
        self.gc(apply=True)
        self.assertIn('unknown-generation', self.rows('generation_sources', 'generation'))
        self.assertIn('unknown-payload', self.rows('canonical_payloads', 'address'))

    def test_missing_pointer_or_mismatch_requires_explicit_operator_identity(self):
        with self.assertRaisesRegex(IndexingStateError, 'disagrees'):
            self.gc(active_job='old-published')
        db = sqlite3.connect(self.path)
        db.execute('DELETE FROM schema_meta')
        db.commit()
        db.close()
        with self.assertRaisesRegex(IndexingStateError, 'active_job'):
            self.gc()
        result = self.gc(active_job='active', previous_job='previous')
        self.assertIn('active', result['plan']['retained_jobs'])

    def test_builder_lock_and_restore_journal_block_gc(self):
        with exclusive_indexer(self.root):
            with self.assertRaises(IndexingStateError):
                self.gc(apply=True)
        (self.root / 'restore-in-progress.json').write_text('{}')
        with self.assertRaisesRegex(IndexingStateError, 'restore'):
            self.gc(apply=True)

    def test_exception_mid_delete_rolls_back_and_can_replay(self):
        before = self.rows('canonical_payloads', 'address')
        def fail(stage):
            if stage == 'deleted':
                raise OSError('disk failure before commit')
        with self.assertRaises(OSError):
            self.gc(apply=True, failure_hook=fail)
        self.assertEqual(self.rows('canonical_payloads', 'address'), before)
        self.assertTrue((self.root / JOURNAL).exists())
        with self.assertRaisesRegex(IndexingStateError, 'resume'):
            self.gc(apply=True)
        self.gc(apply=True, resume=True)
        self.assertFalse((self.root / JOURNAL).exists())
        self.assertIn('shared', self.rows('canonical_payloads', 'address'))

    def test_process_death_before_and_after_commit_recovers_without_double_deletion(self):
        for kill_stage in ('deleted', 'committed'):
            with self.subTest(stage=kill_stage):
                before = self.rows('canonical_payloads', 'address')
                script = '''
import os, sys
from pi_platform.adapters.runtime.generation_gc import collect

def fail(stage):
    if stage == sys.argv[2]:
        os._exit(71)
collect(sys.argv[1], now=10000, ttl_seconds=1000, apply=True, failure_hook=fail)
'''
                result = subprocess.run([sys.executable, '-c', script, str(self.root), kill_stage], check=False)
                self.assertEqual(result.returncode, 71)
                self.assertTrue((self.root / JOURNAL).exists())
                if kill_stage == 'deleted':
                    self.assertEqual(self.rows('canonical_payloads', 'address'), before)
                replay = self.gc(apply=True, resume=True)
                self.assertTrue(replay['applied'])
                self.assertFalse((self.root / JOURNAL).exists())
                self.assertIn('shared', self.rows('canonical_payloads', 'address'))
                self.assertTrue(self.artifact.exists())

    def test_budget_validation_has_no_eviction_side_effect(self):
        before = self.rows('canonical_payloads', 'address')
        with self.assertRaises(ValueError):
            disk_budget_metrics(self.root, min_free_percent=101)
        self.assertEqual(self.rows('canonical_payloads', 'address'), before)
