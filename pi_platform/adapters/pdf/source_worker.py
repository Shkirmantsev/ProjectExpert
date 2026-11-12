"""Spawn-only PDF worker entrypoint; no vendor objects cross this boundary.

The coordinator passes paths and neutral records. SQLite, Docling and model
objects are constructed after native thread limits are set in the child.
"""
from dataclasses import replace
import importlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time


class SourceSpoolCache:
    """Bounded source-local output; never a durable source-completion marker."""
    immutable_payloads = True

    def __init__(self, path, max_bytes, max_records):
        self.db = sqlite3.connect(path)
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE records(address TEXT PRIMARY KEY,payload BLOB NOT NULL)')
        self.db.execute('CREATE TABLE completion(metadata TEXT NOT NULL)')
        self.max_bytes, self.max_records = max_bytes, max_records
        self.bytes = self.count = 0

    def get(self, key):
        return None

    def source_record(self, sid):
        return None

    def put(self, key, payload):
        from pi_platform.ports.ingest.source_adapter import SourceAdapterError
        previous = self.db.execute('SELECT length(payload) FROM records WHERE address=?', (key,)).fetchone()
        size = self.bytes + len(payload) - (previous[0] if previous else 0)
        count = self.count + (0 if previous else 1)
        if size > self.max_bytes or count > self.max_records:
            raise SourceAdapterError('PDF source output exceeds bounded worker spool limit')
        self.db.execute('INSERT OR REPLACE INTO records VALUES(?,?)', (key, payload))
        self.bytes, self.count = size, count

    def complete_source(self, sid, digest, key, addresses, metadata_key=None):
        self.db.execute('INSERT INTO completion VALUES(?)', (json.dumps({
            'sid': sid, 'digest': digest, 'key': key, 'metadata_key': metadata_key,
        }, sort_keys=True),))
        self.db.commit()

    def close(self):
        self.db.close()


def build_pdf_parser(db, config):
    """Production factory; called only inside the spawned process."""
    from pi_platform.adapters.pdf.docling_pdf_adapter import build_real_docling_pdf_adapter
    from pi_platform.adapters.pdf.prescan import PdfPrescanAdapter
    from pi_platform.adapters.runtime.sqlite_ingestion_job_store import SqliteIngestionJobStore
    from pi_platform.adapters.runtime.sqlite_document_graph_store import SqliteDocumentGraphStore
    return build_real_docling_pdf_adapter(
        PdfPrescanAdapter(), SqliteIngestionJobStore(db), SqliteDocumentGraphStore(db),
        embedding_model_id=config['embedding_model_id'], asset_root=config['asset_root'],
    )


def worker_entry(task, sender):
    """One source per child bounds vendor lifetime and allows reliable termination."""
    config, source = task['config'], task['source']
    threads = str(config['threads'])
    for key in ('OMP_NUM_THREADS', 'MKL_NUM_THREADS', 'OPENBLAS_NUM_THREADS',
                'NUMEXPR_NUM_THREADS', 'PI_PARSE_WORKERS', 'PI_INDEX_WORKERS'):
        os.environ[key] = threads
    db = spool = None
    try:
        from pi_platform.adapters.ingest.local_pipeline_driver import (
            LocalPipelineDriver, _default_parser_registry, _default_chunker_registry,
        )
        from pi_platform.adapters.pdf.docling_chunker import PdfStructuralChunker
        from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer, IndexingStateError
        # WAL transition and schema construction need stronger exclusion than a
        # busy timeout. Once initialized, independent workers keep their own
        # connections and never reset journal mode during another writer's job.
        deadline = time.monotonic() + 30
        while True:
            try:
                with exclusive_indexer(Path(config['documents_db_path']).parent / 'pdf-worker-init'):
                    db = sqlite3.connect(config['documents_db_path'], timeout=30)
                    db.row_factory = sqlite3.Row
                    db.execute('PRAGMA busy_timeout=30000')
                    mode = db.execute('PRAGMA journal_mode').fetchone()[0].lower()
                    if mode != 'wal' and db.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
                        raise RuntimeError('PDF worker requires SQLite WAL support')
                    db.execute('PRAGMA synchronous=FULL')
                    factory = build_pdf_parser
                    if config.get('test_parser_factory'):
                        module, name = config['test_parser_factory'].split(':', 1)
                        factory = getattr(importlib.import_module(module), name)
                    parser = factory(db, config)
                    db.commit()
                break
            except (IndexingStateError, sqlite3.OperationalError) as exc:
                if db is not None:
                    db.close()
                    db = None
                busy = isinstance(exc, IndexingStateError) or 'locked' in str(exc).lower() or 'busy' in str(exc).lower()
                if not busy or time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
        parsers, chunkers = _default_parser_registry(), _default_chunker_registry()
        parsers.register(parser)
        chunkers.register(PdfStructuralChunker())
        spool = SourceSpoolCache(task['spool_path'], config['max_result_bytes'], config['max_result_records'])
        driver = LocalPipelineDriver(parser_registry=parsers, chunker_registry=chunkers,
                                     cache=spool, parse_workers=1)
        actual_key = driver.pipeline_key(source)
        if actual_key != task['pipeline_key']:
            raise ValueError('PDF worker pipeline compatibility key differs from coordinator')
        report = driver.run(source, task['project_root'])
        # Large address lists live only in the bounded source spool. The IPC
        # message contains a compact report and a descriptor, not canonical data.
        report = replace(report, stages=tuple(replace(stage, content_addresses=()) for stage in report.stages))
        result = {'report': report, 'spool_path': task['spool_path'], 'pid': os.getpid()}
    except Exception as exc:
        from pi_platform.ports.ingest.pipeline_driver import PipelineReport
        category = 'configuration_error' if isinstance(exc, ValueError) else 'transient'
        result = {'report': PipelineReport(source.id, source.contentHash, (),
                    error_category=category, error_message=f'PDF worker failed: {type(exc).__name__}: {exc}'),
                  'spool_path': task['spool_path'], 'pid': os.getpid()}
    finally:
        if spool is not None:
            spool.close()
        if db is not None:
            db.close()
    if result['report'].ok:
        digest = hashlib.sha256()
        with Path(task['spool_path']).open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                digest.update(block)
        result['spool_sha256'] = digest.hexdigest()
    try:
        sender.send(result)
    finally:
        sender.close()
