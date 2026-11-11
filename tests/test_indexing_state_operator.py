"""Real WAL backup and interrupted multi-database restore regressions."""
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer, IndexingStateError

SPEC = importlib.util.spec_from_file_location('indexing_state_operator', Path('scripts/indexing_state.py'))
operator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(operator)


class IndexingStateOperatorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        self.connections = []
        for name in operator.DATABASES:
            path = self.cache / name
            path.parent.mkdir(exist_ok=True)
            db = sqlite3.connect(path)
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('PRAGMA wal_autocheckpoint=0')
            db.execute('CREATE TABLE evidence(value TEXT)')
            db.execute("INSERT INTO evidence VALUES('before')")
            db.commit()
            self.connections.append(db)
        self.backup = self.root / 'backup'
        self.addCleanup(self.close_connections)

    def close_connections(self):
        for db in self.connections:
            db.close()
        self.connections = []

    def values(self, root):
        values = []
        for name in operator.DATABASES:
            db = sqlite3.connect(root / name)
            try:
                values.append(db.execute('SELECT value FROM evidence').fetchone()[0])
            finally:
                db.close()
        return values

    def mutate(self):
        for db in self.connections:
            db.execute("UPDATE evidence SET value='after'")
            db.commit()

    def test_sqlite_backup_reads_uncheckpointed_wal_and_has_private_permissions(self):
        self.assertTrue(Path(str(self.cache / operator.DATABASES[0]) + '-wal').exists())
        operator.backup(self.cache, self.backup)
        self.assertEqual(self.values(self.backup), ['before'] * 3)
        self.assertEqual(len(operator.verify_backup(self.backup)['files']), 3)
        self.assertFalse(list(self.backup.rglob('*-wal')))
        if os.name != 'nt':
            self.assertEqual(self.backup.stat().st_mode & 0o777, 0o700)
            self.assertEqual((self.backup / 'manifest.json').stat().st_mode & 0o777, 0o600)
            for name in operator.DATABASES:
                self.assertEqual((self.backup / name).stat().st_mode & 0o777, 0o600)

    def test_restore_preserves_pre_restore_snapshot_and_canonical_sources(self):
        operator.backup(self.cache, self.backup)
        self.mutate()
        self.close_connections()
        canonical = self.root / 'project-knowledge'
        canonical.mkdir()
        (canonical / 'source.md').write_text('canonical source')
        report = operator.restore(self.cache, self.backup)
        self.assertEqual(self.values(self.cache), ['before'] * 3)
        self.assertEqual(self.values(Path(report['pre_restore_backup'])), ['after'] * 3)
        self.assertEqual((canonical / 'source.md').read_text(), 'canonical source')
        self.assertFalse((self.cache / operator.JOURNAL).exists())

    def test_restore_into_new_cache_keeps_an_empty_pre_restore_manifest(self):
        operator.backup(self.cache, self.backup)
        destination = self.root / 'new-cache'
        report = operator.restore(destination, self.backup)
        self.assertEqual(self.values(destination), ['before'] * 3)
        self.assertEqual(operator.verify_backup(Path(report['pre_restore_backup']), allow_empty=True)['files'], [])

    def test_exclusive_indexer_blocks_both_backup_and_restore(self):
        operator.backup(self.cache, self.backup)
        with exclusive_indexer(self.cache):
            with self.assertRaises(IndexingStateError):
                operator.backup(self.cache, self.root / 'other')
            with self.assertRaises(IndexingStateError):
                operator.restore(self.cache, self.backup)

    def test_corruption_or_manifest_tamper_prevents_restore_before_changes(self):
        operator.backup(self.cache, self.backup)
        (self.backup / operator.DATABASES[0]).write_bytes(b'corrupt')
        self.mutate()
        self.close_connections()
        with self.assertRaisesRegex(operator.RecoveryError, 'checksum'):
            operator.restore(self.cache, self.backup)
        self.assertEqual(self.values(self.cache), ['after'] * 3)
        self.assertFalse((self.cache / operator.JOURNAL).exists())

    def test_stage_failure_retains_journal_and_requires_explicit_resume(self):
        operator.backup(self.cache, self.backup)
        self.mutate()
        self.close_connections()
        def fail(stage, _name):
            if stage == 'displaced':
                raise OSError('simulated disk write failure')
        with self.assertRaisesRegex(OSError, 'simulated'):
            operator.restore(self.cache, self.backup, failure_hook=fail)
        self.assertTrue((self.cache / operator.JOURNAL).exists())
        with self.assertRaisesRegex(operator.RecoveryError, 'resume'):
            operator.restore(self.cache, self.backup)
        operator.restore(self.cache, resume=True)
        self.assertEqual(self.values(self.cache), ['before'] * 3)
        self.assertFalse((self.cache / operator.JOURNAL).exists())

    def test_killed_process_after_partial_publish_resumes_from_pinned_journal(self):
        operator.backup(self.cache, self.backup)
        self.mutate()
        self.close_connections()
        script = '''
import os, sys
from pathlib import Path
from scripts.indexing_state import restore

def kill(stage, name):
    if stage == 'promoted':
        os._exit(73)
restore(Path(sys.argv[1]), Path(sys.argv[2]), failure_hook=kill)
'''
        result = subprocess.run([sys.executable, '-c', script, str(self.cache), str(self.backup)], check=False)
        self.assertEqual(result.returncode, 73)
        self.assertTrue((self.cache / operator.JOURNAL).exists())
        journal = json.loads((self.cache / operator.JOURNAL).read_text())
        self.assertEqual(len(journal['completed']), 1)
        self.assertEqual(self.values(Path(journal['pre_restore_backup'])), ['after'] * 3)
        operator.restore(self.cache, resume=True)
        self.assertEqual(self.values(self.cache), ['before'] * 3)

    def test_live_wal_reader_blocks_replacement_until_it_is_closed(self):
        operator.backup(self.cache, self.backup)
        self.mutate()
        reader = sqlite3.connect(self.cache / operator.DATABASES[0])
        reader.execute('BEGIN')
        reader.execute('SELECT * FROM evidence').fetchall()
        self.connections[0].execute("UPDATE evidence SET value='latest'")
        self.connections[0].commit()
        try:
            with self.assertRaisesRegex(operator.RecoveryError, 'busy'):
                operator.restore(self.cache, self.backup)
            self.assertTrue((self.cache / operator.JOURNAL).exists())
            self.assertEqual(self.values(self.cache)[0], 'latest')
        finally:
            reader.close()
            self.close_connections()
        operator.restore(self.cache, resume=True)
        self.assertEqual(self.values(self.cache), ['before'] * 3)

    def test_changed_backup_during_interruption_cannot_resume(self):
        operator.backup(self.cache, self.backup)
        self.close_connections()
        def fail(stage, _name):
            if stage == 'journal':
                raise RuntimeError('interrupted')
        with self.assertRaises(RuntimeError):
            operator.restore(self.cache, self.backup, failure_hook=fail)
        manifest = self.backup / 'manifest.json'
        manifest.write_text(manifest.read_text() + '\n')
        with self.assertRaisesRegex(operator.RecoveryError, 'manifest changed'):
            operator.restore(self.cache, resume=True)
        self.assertTrue((self.cache / operator.JOURNAL).exists())
