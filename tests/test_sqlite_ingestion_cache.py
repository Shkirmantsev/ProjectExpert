"""Atomicity and generation contracts use actual on-disk SQLite connections."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from pi_platform.adapters.runtime.sqlite_ingestion_cache import (
    SqliteIngestionCache, IndexingStateError, exclusive_indexer, indexing_progress,
)


class DurableSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / 'indexing-state.sqlite'
        self.cache = self.open('first')

    def open(self, generation):
        cache = SqliteIngestionCache(self.path, generation=generation)
        self.addCleanup(cache.close)
        return cache

    def commit(self, cache, sid='repo:a', digest='v1', address='a', payload=b'one', key='pipeline'):
        buffer = cache.source_buffer(sid)
        buffer.put(address, payload)
        buffer.put(key, json.dumps({'addresses': [address], 'chunkCount': 1}).encode())
        buffer.complete_source(sid, digest, key, [address], 'meta')

    def test_failed_overlay_is_invisible(self):
        overlay = self.cache.source_buffer('repo:a')
        overlay.put('a', b'not complete')
        self.assertIsNone(self.cache.get('a'))
        self.assertEqual(list(self.cache.iter_records()), [])

    def test_transaction_conflict_rolls_back_new_payload_and_membership(self):
        self.commit(self.cache)
        b = self.cache.source_buffer('repo:b')
        b.put('new', b'new')
        b.put('a', b'conflict')
        b.put('other', json.dumps({'addresses': ['new', 'a']}).encode())
        with self.assertRaises(IndexingStateError):
            b.complete_source('repo:b', 'v1', 'other', ['new', 'a'], 'meta')
        self.assertIsNone(self.cache.source_record('repo:b'))
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM canonical_payloads').fetchone()[0], 1)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def test_new_generation_excludes_deleted_and_changed_sources_preserves_old(self):
        self.commit(self.cache)
        self.commit(self.cache, 'repo:deleted', address='b', payload=b'two', key='p2')
        newer = self.open('next')
        newer.select_sources([('repo:a', 'v2', 'meta')])
        self.assertEqual(list(newer.iter_records()), [])
        self.commit(newer, digest='v2', address='c', payload=b'three', key='new-pipeline')
        self.assertEqual(list(newer.iter_records()), [b'three'])
        self.assertEqual(set(self.cache.iter_records()), {b'one', b'two'})
        self.assertIsNone(newer.source_record('repo:deleted'))

    def test_resume_metadata_and_fence_validation(self):
        self.commit(self.cache)
        resumed = self.open('resume')
        resumed.select_sources([('repo:a', 'v1', 'wrong')])
        self.assertIsNone(resumed.source_record('repo:a'))
        resumed.select_sources([('repo:a', 'v1', 'meta')])
        self.assertEqual(resumed.source_record('repo:a')['key'], 'pipeline')
        self.assertEqual(resumed.get('a'), b'one')
        resumed.select_sources([('repo:a', 'v1', 'meta', 'different-pipeline')])
        self.assertIsNone(resumed.source_record('repo:a'))
        with self.assertRaises(IndexingStateError):
            self.cache.stage('parse', 1)

    def test_foreign_keys_enforce_missing_payload(self):
        self.commit(self.cache)
        with self.cache._db:
            with self.assertRaises(sqlite3.IntegrityError):
                self.cache._db.execute('INSERT INTO source_payload_membership VALUES(?,?,?,?,?)',
                    ('repo:a', 'v1', 'pipeline', 'meta', 'missing'))

    def test_legacy_import_preserves_backup_and_ignores_orphans(self):
        path = self.path.with_name('ingestion.json')
        summary = json.dumps({'addresses': ['a'], 'chunkCount': 1})
        raw = json.dumps({'records': {'a': 'one', 'pipeline': summary, 'orphan': 'old'},
            'sources': {'repo:a': {'hash': 'v1', 'key': 'pipeline', 'addresses': ['a'], 'metadata_key': 'meta'}}})
        path.write_text(raw)
        self.cache.import_legacy(path)
        self.assertEqual(path.read_text(), raw)
        self.assertEqual(path.with_name('ingestion.pre-resumable.json').read_text(), raw)
        self.cache.select_sources([('repo:a', 'v1', 'meta')])
        self.assertEqual(list(self.cache.iter_records()), [b'one'])
        self.assertIsNone(self.cache.get('orphan'))
        self.cache.import_legacy(path)

    def test_streaming_legacy_import_handles_key_order_and_split_unicode(self):
        path = self.path.with_name('ingestion.json')
        payload = 'Überweisung' * 20000
        summary = json.dumps({'addresses': ['a'], 'chunkCount': 1})
        path.write_text(json.dumps({
            'sources': {'repo:a': {'hash': 'v1', 'key': 'pipeline', 'addresses': ['a'], 'metadata_key': 'meta'}},
            'owners': {'orphan': ['deleted']},
            'records': {'pipeline': summary, 'a': payload}, 'failures': []}, ensure_ascii=False))
        self.cache.import_legacy(path)
        self.cache.select_sources([('repo:a', 'v1', 'meta')])
        self.assertEqual(list(self.cache.iter_records()), [payload.encode()])

    def test_os_lock_prevents_second_builder(self):
        with exclusive_indexer(self.path.parent):
            with self.assertRaises(IndexingStateError):
                with exclusive_indexer(self.path.parent):
                    pass
        with exclusive_indexer(self.path.parent):
            pass

    def test_abrupt_exit_preserves_committed_source(self):
        code = '''import json,sys,os
from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache
c=SqliteIngestionCache(sys.argv[1],generation='crashed')
b=c.source_buffer('repo:durable'); b.put('d',b'durable'); b.put('k',json.dumps({'addresses':['d']}).encode()); b.complete_source('repo:durable','v','k',['d'],'m'); os._exit(19)
'''
        result = subprocess.run([sys.executable, '-c', code, str(self.path)], capture_output=True)
        self.assertEqual(result.returncode, 19, result.stderr)
        restarted = self.open('after-crash')
        restarted.select_sources([('repo:durable', 'v', 'm')])
        self.assertEqual(list(restarted.iter_records()), [b'durable'])

    def test_valid_sqlite_but_corrupt_payload_fails_closed(self):
        self.commit(self.cache)
        with self.cache._db:
            self.cache._db.execute("UPDATE canonical_payloads SET payload=? WHERE address='a'", (b'changed',))
        with self.assertRaisesRegex(IndexingStateError, 'checksum mismatch'):
            list(self.cache.iter_records())
        with self.assertRaisesRegex(IndexingStateError, 'checksum mismatch'):
            self.cache.get('a')
        with self.cache._db:
            self.cache._db.execute('UPDATE source_outputs SET summary_json=?', (b'{}',))
        with self.assertRaisesRegex(IndexingStateError, 'checksum mismatch'):
            self.cache.source_record('repo:a')

    def test_stage_progress_survives_restart(self):
        self.cache.stage('parse', 10, 8, 1, 2)
        status = indexing_progress(self.path)
        self.assertEqual(status['stages'][0]['completed_items'], 8)
        self.assertEqual(status['stages'][0]['degraded_items'], 2)
        self.assertEqual(status['state'], 'running')


if __name__ == '__main__':
    unittest.main()
