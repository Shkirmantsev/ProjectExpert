"""Coherent WAL/FTS checkpoints, corruption, bounded extraction and inactive restore."""
from contextlib import closing
import errno
import io
import os
import json
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import threading
import unittest
from unittest.mock import patch

from pi_platform.core.runtime.runtime_checkpoint import (
    CheckpointError, RuntimeCheckpointService, restore_checkpoint, verify_checkpoint,
)
from pi_platform.adapters.runtime.runtime_checkpoint_export import extract_checkpoint
from pi_platform.core.sync.version_snapshot import (
    RuntimeSnapshotService, PersistedActiveVersion, ManifestSnapshot, SourceSnapshot,
)


class RuntimeCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / 'cache'
        self.cache.mkdir()
        RuntimeSnapshotService(cache_root=self.cache).commit(
            active=PersistedActiveVersion(
                project_version='v', branch='main', head='abc', working_tree_fingerprint='fp',
                manifest_snapshot_hash='mh', source_snapshot_hash='sh',
                embedding_profile_identity='profile', active_index_generation='generation', last_refresh_id='refresh'),
            manifest=ManifestSnapshot(snapshot_hash='mh', chunk_ids=(), graph_node_ids=()),
            source=SourceSnapshot(snapshot_hash='sh', source_ids=(), content_hashes={}),
        )
        self.db = self.cache / 'runtime.db'
        with closing(sqlite3.connect(self.db)) as conn, conn:
            conn.execute('PRAGMA journal_mode=WAL')
            conn.execute('CREATE VIRTUAL TABLE evidence USING fts5(text)')
            conn.execute("INSERT INTO evidence VALUES ('searchable evidence')")
        for name in ('objects/hash', 'indexes/graph/gen/shard.jsonl', 'document-assets/page.png'):
            path = self.cache / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'artifact')
        (self.cache / 'settings.json').write_text('{"api_key":"never-export"}')
        (self.cache / 'home').mkdir()
        (self.cache / 'home' / 'secret').write_text('never-export')
        self.destination = self.root / 'backup'

    def test_complete_artifacts_and_online_sqlite_snapshot_omit_credentials(self):
        RuntimeCheckpointService(self.cache).create(self.destination)
        manifest = verify_checkpoint(self.destination, profile='profile')
        self.assertIn('runtime.db', manifest['files'])
        self.assertIn('document-assets/page.png', manifest['files'])
        self.assertFalse((self.destination / 'settings.json').exists())
        self.assertFalse((self.destination / 'home').exists())
        self.assertFalse(list(self.destination.rglob('*-wal')))
        with closing(sqlite3.connect(self.destination / 'runtime.db')) as conn, conn:
            self.assertEqual(conn.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(len(conn.execute("SELECT * FROM evidence WHERE evidence MATCH 'searchable'").fetchall()), 1)
        restored = self.root / 'inactive'
        restore_checkpoint(self.destination, restored, profile='profile')
        self.assertEqual((restored / 'objects/hash').read_bytes(), b'artifact')
        self.assertTrue((restored / 'restored-checkpoint.json').is_file())
        with self.assertRaises(CheckpointError):
            restore_checkpoint(self.destination, restored)
        with self.assertRaises(CheckpointError):
            verify_checkpoint(self.destination, profile='other')

    def test_corruption_and_unlisted_files_rejected(self):
        RuntimeCheckpointService(self.cache).create(self.destination)
        artifact = self.destination / 'objects/hash'
        artifact.write_bytes(b'corrupt!')
        with self.assertRaises(CheckpointError):
            verify_checkpoint(self.destination)
        artifact.write_bytes(b'artifact')
        (self.destination / 'extra').write_text('hidden')
        with self.assertRaises(CheckpointError):
            verify_checkpoint(self.destination)

    def test_disk_full_never_publishes_partial_checkpoint(self):
        with patch('pi_platform.core.runtime.runtime_checkpoint.shutil.copyfile', side_effect=OSError('No space left')):
            with self.assertRaises(OSError):
                RuntimeCheckpointService(self.cache).create(self.destination)
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob('.incomplete-*')))
        self.assertTrue(self.db.exists())

    def test_unready_and_oversize_fail_without_mutating_live_runtime(self):
        with self.assertRaises(CheckpointError):
            RuntimeCheckpointService(self.cache, max_bytes=1).create(self.destination)
        (self.cache / 'readiness.json').write_text('{"consistent":false}')
        with self.assertRaises(CheckpointError):
            RuntimeCheckpointService(self.cache).create(self.destination)
        self.assertFalse(self.destination.exists())

    def test_path_traversal_symlink_and_archive_budget_rejected(self):
        for name, kind in (('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE), ('link', tarfile.SYMTYPE)):
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode='w') as archive:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.linkname = '/tmp/outside'
                info.size = 1 if kind == tarfile.REGTYPE else 0
                archive.addfile(info, io.BytesIO(b'x') if info.size else None)
            stream.seek(0)
            with self.assertRaises(CheckpointError):
                extract_checkpoint(stream, self.root / 'extract', max_bytes=100)
            self.assertFalse((self.root / 'extract').exists())

    def test_non_sqlite_mutation_during_snapshot_rejected(self):
        from pi_platform.core.runtime import runtime_checkpoint as module
        original = module.shutil.copyfile
        def mutate(source, dest):
            result = original(source, dest)
            if Path(source).relative_to(self.cache).as_posix() == 'objects/hash':
                Path(source).write_bytes(b'concurrent changed artifact')
            return result
        with patch.object(module.shutil, 'copyfile', side_effect=mutate):
            with self.assertRaises(CheckpointError):
                RuntimeCheckpointService(self.cache).create(self.destination)
        self.assertFalse(self.destination.exists())

    def test_checkpoint_and_restore_flush_only_writable_file_handles(self):
        # Windows _commit rejects read-only handles. Model that constraint on
        # every host while still performing real SQLite backup and restoration.
        original_open, original_sync = Path.open, os.fsync
        streams = []
        def tracked_open(path, *args, **kwargs):
            stream = original_open(path, *args, **kwargs)
            streams.append(stream)
            return stream
        def writable_sync(descriptor):
            for stream in streams:
                if not stream.closed and stream.fileno() == descriptor and not stream.writable():
                    raise OSError(errno.EBADF, 'Windows requires a writable flush handle')
            return original_sync(descriptor)
        with patch.object(Path, 'open', tracked_open), patch('os.fsync', side_effect=writable_sync):
            RuntimeCheckpointService(self.cache).create(self.destination)
            restore_checkpoint(self.destination, self.root / 'inactive', profile='profile')
        self.assertEqual(verify_checkpoint(self.destination)['generation'], 'generation')


    def test_resumable_source_checkpoint_is_backed_up_from_live_wal_and_restored(self):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache
        cache = SqliteIngestionCache(self.cache / 'indexing-state.sqlite')
        self.addCleanup(cache.close)
        overlay = cache.source_buffer('repo:manual.md')
        overlay.put('chunk', b'canonical parser payload')
        overlay.put('pipeline', json.dumps({'addresses': ['chunk'], 'chunkCount': 1,
                                           'knowledgeState': 'verified'}).encode())
        overlay.complete_source('repo:manual.md', 'source-hash', 'pipeline', ['chunk'], 'metadata')
        self.assertTrue((self.cache / 'indexing-state.sqlite-wal').is_file())
        self.assertGreater((self.cache / 'indexing-state.sqlite-wal').stat().st_size, 0)
        RuntimeCheckpointService(self.cache).create(self.destination)
        manifest = verify_checkpoint(self.destination)
        self.assertIn('indexing-state.sqlite', manifest['files'])
        self.assertFalse((self.destination / 'indexing-state.sqlite-wal').exists())
        restored = self.root / 'inactive'
        restore_checkpoint(self.destination, restored)
        with closing(sqlite3.connect(restored / 'indexing-state.sqlite')) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT source_id,source_hash,pipeline_key FROM source_outputs').fetchall(),
                             [('repo:manual.md', 'source-hash', 'pipeline')])
            self.assertEqual(db.execute('SELECT payload FROM canonical_payloads').fetchall(),
                             [(b'canonical parser payload',)])
        self.assertFalse((restored / 'indexing-state.sqlite-wal').exists())

    def test_interrupted_restore_blocks_managed_checkpoint_export(self):
        (self.cache / 'restore-in-progress.json').write_text('{"schema_version":1}')
        with self.assertRaisesRegex(CheckpointError, 'Interrupted indexing state restore'):
            RuntimeCheckpointService(self.cache).create(self.destination)
        self.assertFalse(self.destination.exists())

    def test_index_builder_lock_blocks_checkpoint_and_checkpoint_holds_it(self):
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer, IndexingStateError
        with exclusive_indexer(self.cache):
            with self.assertRaisesRegex(CheckpointError, 'Another index builder'):
                RuntimeCheckpointService(self.cache).create(self.destination)
        original = RuntimeCheckpointService._create_locked
        def inspect_lock(service, destination):
            with self.assertRaises(IndexingStateError):
                with exclusive_indexer(self.cache):
                    self.fail('checkpoint did not exclude an index builder')
            return original(service, destination)
        with patch.object(RuntimeCheckpointService, '_create_locked', inspect_lock):
            RuntimeCheckpointService(self.cache).create(self.destination)
