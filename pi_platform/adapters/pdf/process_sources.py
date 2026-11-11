"""Opt-in spawned PDF sources with coordinator-only canonical publication."""
from contextlib import nullcontext
import hashlib
import json
import logging
import multiprocessing
from multiprocessing.connection import wait
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from pi_platform.adapters.pdf.source_worker import worker_entry
from pi_platform.ports.ingest.pipeline_driver import PipelineReport, StageOutcome
from pi_platform.core.canonical.value_types import KnowledgeState

log = logging.getLogger(__name__)


def _cached_report(source, cache, key):
    record = cache.source_record(source.id)
    if not record or record['hash'] != source.contentHash or record['key'] != key:
        return None
    data = json.loads(cache.get(key))
    return PipelineReport(source.id, source.contentHash,
        tuple(StageOutcome(stage, True, data['chunkCount'], 0, source_id=source.id, outcome='skipped')
              for stage in ('parse', 'chunk', 'enrich', 'emit', 'store')),
        chunk_count=data['chunkCount'], entity_count=data['entityCount'],
        relation_count=data['relationCount'], evidence_count=data['evidenceCount'],
        cache_hit_count=data['chunkCount'], knowledge_state=KnowledgeState(data['knowledgeState']), sources=(source,),
        degraded=bool(data.get('degraded', False)))


def _commit_spool(task, report, cache, *, max_bytes, max_records):
    """Read a closed worker file; one bounded source overlay commits atomically."""
    path = Path(task['spool_path'])
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    if path.is_symlink() or digest.hexdigest() != task['spool_sha256']:
        raise RuntimeError('PDF worker spool checksum mismatch')
    db = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro&immutable=1', uri=True)
    try:
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise RuntimeError('PDF worker spool integrity failure')
        completion = db.execute('SELECT metadata FROM completion').fetchall()
        if len(completion) != 1:
            raise RuntimeError('PDF worker output is incomplete')
        meta = json.loads(completion[0][0])
        source = task['source']
        if (meta['sid'], meta['digest'], meta['key']) != (source.id, source.contentHash, task['pipeline_key']):
            raise RuntimeError('PDF worker source identity mismatch')
        overlay = cache.source_buffer(source.id)
        total = count = 0
        for key, raw in db.execute('SELECT address,payload FROM records ORDER BY address'):
            total += len(raw)
            count += 1
            if total > max_bytes or count > max_records:
                raise RuntimeError('PDF worker source exceeds coordinator admission limit')
            overlay.put(key, bytes(raw))
        summary = json.loads(overlay.get(meta['key']))
        if summary['chunkCount'] != report.chunk_count:
            raise RuntimeError('PDF worker report differs from canonical output')
        overlay.complete_source(source.id, source.contentHash, meta['key'],
                                summary['addresses'], meta['metadata_key'])
    finally:
        db.close()


def run_pdf_sources(sources, project_root, *, cache, documents_db_path, asset_root,
                    embedding_model_id, pipeline_keys, workers=None, resource_pool=None,
                    diagnostics=None, memory_probe=None, estimated_worker_peak=None,
                    max_result_bytes=None, max_result_records=100000, source_timeout=None,
                    cancellation=None, test_parser_factory=None):
    """Spawn fresh source workers; return reports in the original source order.

    ``test_parser_factory`` is an explicit test-only import path. It is never
    configured from environment or used by the production factory. PDFs use
    their existing page-batch checkpoints in a connection owned by each child.
    """
    from pi_platform.adapters.runtime.host_resources import parse_worker_budget, probe_available_memory
    if not hasattr(cache, 'source_buffer'):
        raise ValueError('Spawned PDF sources require a buffered durable cache')
    if test_parser_factory is not None and not test_parser_factory.startswith('tests.'):
        raise ValueError('Fixture parser factory must be a test module')
    sources = tuple(sources)
    if any(source.family != 'pdf' for source in sources):
        raise ValueError('PDF source helper accepts only PDF sources')
    requested = int(workers if workers is not None else os.environ.get('PI_PDF_WORKERS', '1'))
    if requested < 1:
        raise ValueError('PI_PDF_WORKERS must be positive')
    cpu = min(parse_worker_budget(), resource_pool.capacity if resource_pool else parse_worker_budget())
    threads = min(cpu, max(1, int(os.environ.get('PI_PDF_THREADS', '1'))))
    admitted = max(1, min(requested, cpu // threads))
    max_bytes = int(max_result_bytes or os.environ.get('PI_PDF_RESULT_MAX_BYTES', str(128 * 1024 * 1024)))
    timeout = float(source_timeout or os.environ.get('PI_PDF_SOURCE_TIMEOUT_SECONDS', '3600'))
    if max_bytes < 1 or max_result_records < 1 or timeout <= 0:
        raise ValueError('Invalid PDF worker output/timeout limit')
    available = (memory_probe or probe_available_memory)()
    largest = 0
    unknown = False
    for source in sources:
        try:
            largest = max(largest, Path(source.uri).stat().st_size)
        except OSError:
            unknown = True
    # Explicit heuristic includes model/native overhead, source amplification and
    # the coordinator's complete source overlay. Hardware promotion needs RSS data.
    peak = int(estimated_worker_peak if estimated_worker_peak is not None else
               int(os.environ.get('PI_PDF_WORKER_PEAK_BYTES', str(1024 * 1024 * 1024))) + largest * 32 + max_bytes)
    if peak <= 0:
        raise ValueError('Invalid PDF worker memory estimate')
    memory_budget = None if available is None else max(0, int(available // 2))
    if unknown or memory_budget is None:
        admitted = 1
    else:
        if memory_budget < peak:
            raise ValueError('PDF memory budget cannot admit one estimated worker; reduce model/output cost or supply measured limits')
        admitted = min(admitted, memory_budget // peak)
    info = diagnostics if diagnostics is not None else {}
    info.update(workers=admitted, threads_per_worker=threads, cpu_cost=admitted * threads,
                estimated_worker_peak_bytes=peak, memory_budget_bytes=memory_budget,
                requested_workers=requested, worker_pids=[], completed_sources=0)
    log.info('PDF process admission=%s', info)
    reports, tasks = {}, []
    root = Path(documents_db_path).resolve().parent
    root.mkdir(parents=True, exist_ok=True)
    staging = root / 'pdf-worker-spool'
    staging.mkdir(exist_ok=True)
    config = {'documents_db_path': str(Path(documents_db_path).resolve()),
              'asset_root': str(Path(asset_root).resolve()), 'embedding_model_id': embedding_model_id,
              'threads': threads, 'max_result_bytes': max_bytes, 'max_result_records': max_result_records,
              'test_parser_factory': test_parser_factory}
    for index, source in enumerate(sources):
        key = pipeline_keys[source.id]
        cached = _cached_report(source, cache, key)
        if cached is not None:
            reports[index] = cached
            continue
        descriptor, name = tempfile.mkstemp(prefix=hashlib.sha256(source.id.encode()).hexdigest()[:12] + '-',
                                            suffix='.sqlite', dir=staging)
        os.close(descriptor)
        tasks.append((index, {'config': config, 'source': source, 'pipeline_key': key,
                             'project_root': str(Path(project_root).resolve()), 'spool_path': name}))
    if not tasks:
        return tuple(reports[index] for index in sorted(reports))
    context = multiprocessing.get_context('spawn')
    running, next_task = [], 0
    token_lease = resource_pool.acquire(admitted * threads) if resource_pool else nullcontext()
    try:
        with token_lease:
            while running or next_task < len(tasks):
                if cancellation is not None and cancellation.is_cancelled():
                    break
                while next_task < len(tasks) and len(running) < admitted:
                    index, task = tasks[next_task]
                    next_task += 1
                    reader, sender = context.Pipe(duplex=False)
                    process = context.Process(target=worker_entry, args=(task, sender))
                    try:
                        process.start()
                    finally:
                        sender.close()
                    running.append((index, task, process, reader, time.monotonic()))
                wait([row[3] for row in running], timeout=0.1)
                for row in tuple(running):
                    index, task, process, reader, started = row
                    result = None
                    error = None
                    if reader.poll():
                        try:
                            result = reader.recv()
                        except (EOFError, OSError):
                            error = f'PDF worker exited without a complete result (exit_code={process.exitcode})'
                    elif not process.is_alive():
                        error = f'PDF worker crashed (exit_code={process.exitcode})'
                    elif time.monotonic() - started > timeout:
                        error = f'PDF worker exceeded {timeout}s source timeout'
                        process.terminate()
                    else:
                        continue
                    process.join(timeout=5)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
                        if process.is_alive():
                            process.kill()
                            process.join(timeout=5)
                        if process.is_alive():
                            raise RuntimeError('PDF worker did not stop after bounded terminate/kill grace')
                    reader.close()
                    running.remove(row)
                    source = task['source']
                    if result is not None:
                        report = result['report']
                        if result['spool_path'] != task['spool_path'] or report.source_id != source.id:
                            raise RuntimeError('PDF worker returned another source identity')
                        info['worker_pids'].append(result['pid'])
                        if report.ok:
                            task['spool_sha256'] = result['spool_sha256']
                            _commit_spool(task, report, cache, max_bytes=max_bytes, max_records=max_result_records)
                            info['completed_sources'] += 1
                    else:
                        report = PipelineReport(source.id, source.contentHash, (), error_category='transient',
                                                error_message=error, sources=(source,))
                    reports[index] = report
                    Path(task['spool_path']).unlink(missing_ok=True)
                    process.close()
                    if report.error_category in ('configuration_error', 'cancelled', 'internal_error'):
                        return tuple(reports[index] for index in sorted(reports))
        return tuple(reports[index] for index in sorted(reports))
    finally:
        for _, _, process, reader, _ in running:
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
            if process.is_alive():
                process.kill()
                process.join(timeout=5)
            reader.close()
            process.close()
        for _, task in tasks:
            for suffix in ('', '-journal', '-wal', '-shm'):
                Path(task['spool_path'] + suffix).unlink(missing_ok=True)
