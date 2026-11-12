"""Spawned PDF worker contracts using explicit text fixtures, never fake release proof."""
from contextlib import closing
import hashlib
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.adapters.pdf.process_sources import run_pdf_sources
from pi_platform.adapters.ingest.local_pipeline_driver import LocalPipelineDriver, _default_parser_registry
from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache
from pi_platform.core.canonical.value_types import Source, Metadata
from pi_platform.core.ingest.records import document_result
from pi_platform.ports.ingest.source_adapter import SourceAdapterPort, SourceContentFamily


class FixturePdfParser(SourceAdapterPort):
    family = SourceContentFamily.PDF
    def __init__(self, db):
        self.db = db
    def parse(self, source, context=None):
        # These durable rows prove that each spawned worker constructed a usable
        # independent connection. A crash preserves its committed page checkpoint.
        self.db.execute('CREATE TABLE IF NOT EXISTS worker_pages(source TEXT PRIMARY KEY,pid INTEGER)')
        self.db.execute('INSERT OR REPLACE INTO worker_pages VALUES(?,?)', (source.id, os.getpid()))
        self.db.commit()
        if Path(source.uri).read_text() == 'crash':
            os._exit(37)
        return document_result(source, [('', 1, Path(source.uri).read_text(), {})], 'pdf', 'fixture-pdf/v1')


def fixture_parser_factory(db, config):
    import time
    time.sleep(0.05)  # Widen concurrent worker initialization deterministically.
    return FixturePdfParser(db)


class PdfProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache_root = self.root / 'cache'
        self.cache = SqliteIngestionCache(self.cache_root / 'indexing-state.sqlite')
        self.addCleanup(self.cache.close)
        registry = _default_parser_registry()
        registry.register(FixturePdfParser(None))
        self.driver = LocalPipelineDriver(parser_registry=registry, parse_workers=1)
        self.sources = []
        for index in range(3):
            path = self.root / f'document-{index}.pdf'
            path.write_text(f'customer payment {index}')
            self.sources.append(Source(id=f'repo:{path.name}', uri=str(path), family='pdf',
                contentHash=hashlib.sha256(path.read_bytes()).hexdigest(), metadata=Metadata(documentId=path.name, version='0.1.0', language='und')))

    def run_workers(self, **overrides):
        args = dict(cache=self.cache, documents_db_path=self.cache_root / 'documents-v2.sqlite',
            asset_root=self.cache_root / 'assets', embedding_model_id='fixture', workers=2,
            pipeline_keys={source.id: self.driver.pipeline_key(source) for source in self.sources},
            estimated_worker_peak=1024, memory_probe=lambda: 1024 * 1024,
            test_parser_factory='tests.test_pdf_process_sources:fixture_parser_factory')
        args.update(overrides)
        with patch('pi_platform.adapters.runtime.host_resources.parse_worker_budget', return_value=4):
            return run_pdf_sources(self.sources, self.root, **args)

    def test_spawn_connections_order_atomic_results_and_completed_source_reuse(self):
        diagnostics = {}
        reports = self.run_workers(diagnostics=diagnostics)
        self.assertEqual([r.source_id for r in reports], [s.id for s in self.sources])
        self.assertTrue(all(r.ok for r in reports), reports)
        self.assertEqual(diagnostics['workers'], 2)
        with closing(sqlite3.connect(self.cache_root / 'documents-v2.sqlite')) as db:
            pids = {row[0] for row in db.execute('SELECT pid FROM worker_pages')}
        self.assertNotIn(os.getpid(), pids)
        self.assertGreaterEqual(len(pids), 2)
        self.assertEqual(len(self.cache.source_ids()), 3)
        records = list(self.cache.iter_records())
        with patch('pi_platform.adapters.pdf.process_sources.worker_entry', side_effect=AssertionError('reparsed')):
            reused = self.run_workers()
        self.assertTrue(all(r.cache_hit_count > 0 for r in reused))
        self.assertEqual(list(self.cache.iter_records()), records)

    def test_crashed_source_has_page_checkpoint_but_no_complete_source_output(self):
        Path(self.sources[0].uri).write_text('crash')
        reports = self.run_workers()
        self.assertFalse(reports[0].ok)
        self.assertIsNone(self.cache.source_record(self.sources[0].id))
        with closing(sqlite3.connect(self.cache_root / 'documents-v2.sqlite')) as db:
            self.assertIsNotNone(db.execute('SELECT pid FROM worker_pages WHERE source=?', (self.sources[0].id,)).fetchone())
        self.assertTrue(all(report.ok for report in reports[1:]))
        Path(self.sources[0].uri).write_text('recovered text')
        self.assertTrue(all(report.ok for report in self.run_workers()))

    def test_windows_broken_pipe_poll_preserves_crash_checkpoint_and_siblings(self):
        import multiprocessing
        context = multiprocessing.get_context('spawn')
        original_pipe = context.Pipe
        injected = []
        first = True
        def pipe(*args, **kwargs):
            nonlocal first
            reader, sender = original_pipe(*args, **kwargs)
            if first:
                first = False
                original_poll = reader.poll
                def poll(timeout=0):
                    try:
                        ready = original_poll(timeout)
                    except (EOFError, BrokenPipeError):
                        ready = True
                    if ready:
                        injected.append(True)
                        raise BrokenPipeError(109, 'The pipe has been ended')
                    return False
                reader.poll = poll
            return reader, sender
        with patch.object(context, 'Pipe', side_effect=pipe):
            self.test_crashed_source_has_page_checkpoint_but_no_complete_source_output()
        self.assertEqual(injected, [True])
        self.assertEqual(list((self.cache_root / 'pdf-worker-spool').iterdir()), [])

    def test_source_deadline_terminates_children_without_publishing_partial_results(self):
        reports = self.run_workers(source_timeout=0.001)
        self.assertTrue(all(not report.ok for report in reports))
        self.assertEqual(self.cache.source_ids(), ())
        self.assertEqual(list((self.cache_root / 'pdf-worker-spool').iterdir()), [])

    def test_spool_size_limit_never_commits_partial_source(self):
        reports = self.run_workers(max_result_bytes=10)
        self.assertTrue(all(not report.ok for report in reports))
        self.assertEqual(self.cache.source_ids(), ())
        self.assertEqual(list(self.cache.iter_records()), [])


if __name__ == '__main__':
    unittest.main()
