"""SQLite work must grow linearly when importing many completed sources."""
from pathlib import Path
import tempfile
import unittest

from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache
from pi_platform.adapters.sync.portable_format import encode, sha


class CheckpointScaleTests(unittest.TestCase):
    def test_source_progress_does_not_rescan_all_previous_sources(self):
        def import_work(count):
            with tempfile.TemporaryDirectory() as temporary:
                cache = SqliteIngestionCache(Path(temporary) / 'indexing-state.sqlite')
                self.addCleanup(cache.close)
                cache.stage('sources', count)
                work = [0]
                def tick():
                    work[0] += 100
                    return 0
                cache._db.set_progress_handler(tick, 100)
                summary = encode({'addresses': [], 'chunkCount': 0, 'entityCount': 0,
                    'relationCount': 0, 'evidenceCount': 0, 'knowledgeState': 'verified', 'degraded': False})
                cache.import_portable_sources((f'repo:source-{i}.md', sha(str(i).encode()), 'a' * 64,
                    (), 'b' * 64, {'a' * 64: summary}) for i in range(count))
                cache._db.set_progress_handler(None, 0)
                self.assertEqual(cache._db.execute("SELECT completed_items FROM index_stages WHERE stage='sources'").fetchone()[0], count)
                cache.close()
                return work[0]
        small, large = import_work(200), import_work(400)
        self.assertLess(large, small * 2.8, f'Doubling sources used {large}/{small} SQLite instructions')
