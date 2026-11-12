"""Real artifact recovery and WAL-independent promotion tests."""
from contextlib import closing
import hashlib
import errno
import os
import stat
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.adapters.runtime.candidate_artifacts import build_exact, build_graph_shards
from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
from pi_platform.core.canonical.value_types import Entity, Relation


class CandidateArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_fts_resume_after_committed_batch_and_standalone_final(self):
        path = self.root / 'exact.sqlite'
        rows = [(str(i), f'customer refund {i}') for i in range(7)]
        def interrupt(completed, total):
            if completed == 4:
                raise RuntimeError('power off after committed batch')
        with self.assertRaisesRegex(RuntimeError, 'power off'):
            build_exact(path, rows, 'fingerprint', batch_size=2, progress=interrupt)
        self.assertFalse(path.exists())
        building = self.root / 'exact.building.sqlite'
        with closing(sqlite3.connect(building)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM build_chunks').fetchone()[0], 4)
        checkpoints = []
        result = build_exact(path, rows, 'fingerprint', batch_size=2,
                             progress=lambda done, total: checkpoints.append(done))
        self.assertEqual(checkpoints, [4, 6, 7])
        self.assertEqual(result.stats()['documents'], 7)
        self.assertFalse(building.exists())
        self.assertFalse(path.with_name(path.name + '-wal').exists())
        # Copy only the main file into a new directory: no hidden WAL dependency.
        copy = self.root / 'copy.sqlite'
        copy.write_bytes(path.read_bytes())
        with closing(sqlite3.connect(copy)) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute("SELECT count(*) FROM runtime_fulltext_fts WHERE runtime_fulltext_fts MATCH 'refund'").fetchone()[0], 7)
        original = path.read_bytes()
        build_exact(path, rows, 'fingerprint')
        self.assertEqual(path.read_bytes(), original)

    @unittest.skipUnless(os.name == 'posix', 'Models Windows file-handle rules using POSIX descriptor access flags')
    def test_fts_promotion_uses_a_writable_handle_for_durable_flush(self):
        import fcntl
        native_fsync = os.fsync
        def windows_flush_rules(descriptor):
            if stat.S_ISREG(os.fstat(descriptor).st_mode):
                access = fcntl.fcntl(descriptor, fcntl.F_GETFL) & os.O_ACCMODE
                if access == os.O_RDONLY:
                    raise OSError(errno.EBADF, 'Windows cannot flush a read-only file handle')
            return native_fsync(descriptor)
        with patch('pi_platform.adapters.runtime.candidate_artifacts.os.fsync', side_effect=windows_flush_rules):
            result = build_exact(self.root / 'durable.sqlite', [('a', 'refund')], 'fingerprint')
        self.assertEqual(result.stats()['documents'], 1)

    def test_fts_failed_new_candidate_preserves_old(self):
        old = self.root / 'old.sqlite'
        build_exact(old, [('old', 'last good refund')], 'old')
        before = old.read_bytes()
        def fail(*args):
            raise OSError('disk full')
        with patch('pi_platform.adapters.runtime.candidate_artifacts.os.replace', side_effect=fail):
            with self.assertRaises(OSError):
                build_exact(self.root / 'new.sqlite', [('new', 'new billing')], 'new')
        self.assertEqual(old.read_bytes(), before)

    def test_graph_reuses_shards_and_repairs_interruption(self):
        graph = LocalShardedGraph(self.root / 'graph')
        entities = [Entity('a', 'Component', 'Billing'), Entity('b', 'Component', 'Ledger')]
        relations = [Relation('a', 'b', 'DEPENDS_ON')]
        build_graph_shards(graph, entities, relations)
        path = graph._shard_path_for_entity('nodes', 'a')
        timestamp = path.stat().st_mtime_ns
        build_graph_shards(graph, entities, relations)
        self.assertEqual(path.stat().st_mtime_ns, timestamp)
        path.write_bytes(b'partial write')
        build_graph_shards(graph, entities, relations)
        self.assertEqual(graph.get_entity('a').label, 'Billing')
        self.assertEqual(len(graph.get_relations('a')), 1)


if __name__ == '__main__':
    unittest.main()
