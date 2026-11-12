"""Explicit canonical-state GC; never deletes runtime artifacts or source files.

Stop serving readers before applying. The indexer lease excludes builders, but
cannot prove that an external process has released a generation read handle.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import time
import uuid

from .sqlite_ingestion_cache import exclusive_indexer, IndexingStateError

JOURNAL = 'gc-in-progress.json'


def _sync_directory(path):
    if os.name != 'nt':
        handle = os.open(path, os.O_RDONLY)
        try:
            os.fsync(handle)
        finally:
            os.close(handle)


def _write_journal(path, value):
    handle, temporary = tempfile.mkstemp(prefix='.gc-', dir=path.parent)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def disk_budget_metrics(cache_root, *, min_free_bytes=0, min_free_percent=0,
                        max_payload_bytes=0, max_state_bytes=0, payload_bytes=0):
    """Reusable preflight metrics; exceeding a quota never evicts active state."""
    if min(min_free_bytes, min_free_percent, max_payload_bytes, max_state_bytes, payload_bytes) < 0 or min_free_percent > 100:
        raise ValueError('Disk budgets must be nonnegative; free percentage must be <=100')
    root = Path(cache_root)
    disk = shutil.disk_usage(root)
    state_bytes = sum(path.stat().st_size for name in ('indexing-state.sqlite', 'indexing-state.sqlite-wal', 'indexing-state.sqlite-shm')
                      if (path := root / name).is_file() and not path.is_symlink())
    checks = {'minimum_free_bytes': disk.free >= min_free_bytes,
              'minimum_free_percent': disk.free * 100 >= disk.total * min_free_percent,
              'payload_quota': not max_payload_bytes or payload_bytes <= max_payload_bytes,
              'state_quota': not max_state_bytes or state_bytes <= max_state_bytes}
    return {'free_bytes': disk.free, 'total_bytes': disk.total, 'state_file_bytes': state_bytes,
            'payload_bytes': payload_bytes, 'checks': checks, 'preflight_ok': all(checks.values())}


def _counts(db):
    result = {name: db.execute('SELECT count(*) FROM ' + name).fetchone()[0] for name in
              ('index_jobs', 'generation_sources', 'source_outputs', 'source_payload_membership', 'canonical_payloads')}
    result['payload_bytes'] = db.execute('SELECT coalesce(sum(length(payload)),0) FROM canonical_payloads').fetchone()[0]
    return result


def _plan(db, *, active_job, previous_job, compatibility_hash, ttl_seconds, now):
    if ttl_seconds < 0:
        raise ValueError('Incomplete checkpoint TTL must be nonnegative')
    metadata = dict(db.execute("SELECT key,value FROM schema_meta WHERE key IN ('active_job','previous_job')"))
    authoritative_active = metadata.get('active_job')
    authoritative_previous = metadata.get('previous_job')
    if authoritative_active and active_job and active_job != authoritative_active:
        raise IndexingStateError('GC active job disagrees with the durable publication pointer')
    if authoritative_previous and previous_job and previous_job != authoritative_previous:
        raise IndexingStateError('GC previous job disagrees with the durable publication pointer')
    active_job = authoritative_active or active_job
    previous_job = authoritative_previous or previous_job
    if not active_job:
        raise IndexingStateError('GC requires a durable active_job or an explicit --active-job')
    jobs = [dict(row) for row in db.execute('SELECT * FROM index_jobs ORDER BY fence DESC')]
    by_id = {job['job_id']: job for job in jobs}
    keep = set()
    for identity in (active_job, previous_job):
        if identity:
            if identity not in by_id or by_id[identity]['state'] != 'published':
                raise IndexingStateError('GC publication pointer must reference an existing published job')
            keep.add(identity)
    keep.update(job['job_id'] for job in [job for job in jobs if job['state'] == 'published'][:2])
    # A snapshot may have been committed before the audit-pointer transaction
    # failed. Prepared publications remain reachable until explicitly reconciled.
    keep.update(row[0] for row in db.execute("SELECT job_id FROM publication_intents WHERE state='prepared'"))
    compatible = {by_id[identity]['compatibility_hash'] for identity in keep}
    if compatibility_hash:
        compatible.add(compatibility_hash)
    cutoff = now - ttl_seconds
    newest_ready = set()
    for job in jobs:
        if job['compatibility_hash'] not in compatible:
            continue
        if job['state'] == 'ready' and job['compatibility_hash'] not in newest_ready:
            keep.add(job['job_id'])
            newest_ready.add(job['compatibility_hash'])
        if job['state'] in ('running', 'interrupted', 'failed') and job['updated_at'] >= cutoff:
            keep.add(job['job_id'])
    return {'active_job': active_job, 'previous_job': previous_job,
            'retained_jobs': sorted(keep), 'obsolete_jobs': sorted(set(by_id) - keep),
            'checkpoint_cutoff': cutoff, 'ttl_seconds': ttl_seconds,
            'compatibility_hash': compatibility_hash}


def _delete_unreachable(db, obsolete, cutoff):
    db.execute('CREATE TEMP TABLE gc_obsolete(job_id TEXT PRIMARY KEY)')
    db.executemany('INSERT INTO gc_obsolete VALUES(?)', ((identity,) for identity in obsolete))
    db.execute('DELETE FROM generation_sources WHERE generation IN (SELECT job_id FROM gc_obsolete)')
    # Orphan checkpoints survive until TTL expiry even if their provenance no
    # longer records a compatibility hash; conservatism prevents lost reuse.
    unreachable = '''NOT EXISTS (SELECT 1 FROM generation_sources g WHERE
        g.source_id=o.source_id AND g.source_hash=o.source_hash AND
        g.pipeline_key=o.pipeline_key AND g.metadata_key=o.metadata_key)
        AND o.completed_at < ?'''
    db.execute('''DELETE FROM source_payload_membership WHERE EXISTS (
        SELECT 1 FROM source_outputs o WHERE o.source_id=source_payload_membership.source_id
        AND o.source_hash=source_payload_membership.source_hash
        AND o.pipeline_key=source_payload_membership.pipeline_key
        AND o.metadata_key=source_payload_membership.metadata_key AND ''' + unreachable + ')', (cutoff,))
    db.execute('DELETE FROM source_outputs AS o WHERE ' + unreachable, (cutoff,))
    db.execute('DELETE FROM canonical_payloads WHERE NOT EXISTS (SELECT 1 FROM source_payload_membership m WHERE m.address=canonical_payloads.address)')
    db.execute('DELETE FROM index_stages WHERE job_id IN (SELECT job_id FROM gc_obsolete)')
    # Artifact manifests are retained as evidence. Their files are not removed.
    marked = db.execute("UPDATE index_jobs SET state='collected' WHERE job_id IN (SELECT job_id FROM gc_obsolete) AND state!='collected'").rowcount
    db.execute('DROP TABLE gc_obsolete')
    return marked


def collect(cache_root, *, active_job=None, previous_job=None, compatibility_hash=None,
            ttl_seconds=7 * 86400, apply=False, resume=False, now=None,
            failure_hook=None, min_free_bytes=0, min_free_percent=0,
            max_payload_bytes=0, max_state_bytes=0):
    """Plan by default; apply SQL reachability deletion in one recoverable txn."""
    root = Path(cache_root).resolve()
    hook = failure_hook or (lambda _stage: None)
    with exclusive_indexer(root):
        if (root / 'restore-in-progress.json').exists():
            raise IndexingStateError('Complete interrupted restore before running GC')
        path = root / 'indexing-state.sqlite'
        if not path.is_file() or path.is_symlink():
            raise IndexingStateError('GC requires an existing regular indexing-state.sqlite')
        journal_path = root / JOURNAL
        if journal_path.is_symlink():
            raise IndexingStateError('Refusing symlinked GC journal')
        if journal_path.exists() and not (apply and resume):
            raise IndexingStateError('Interrupted GC exists; use gc --apply --resume with serving stopped')
        if resume and not journal_path.exists():
            raise IndexingStateError('No interrupted GC journal exists')
        db = sqlite3.connect(path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('PRAGMA synchronous=FULL')
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise IndexingStateError('GC refuses corrupt indexing state')
            journal = json.loads(journal_path.read_text()) if resume else None
            if journal and (journal.get('schema_version') != 1 or journal.get('cache_root') != str(root)):
                raise IndexingStateError('GC journal identity mismatch')
            existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='operator_gc_runs'").fetchone()
            if journal and existing:
                complete = db.execute('SELECT metrics_json FROM operator_gc_runs WHERE operation_id=?', (journal['operation_id'],)).fetchone()
                if complete:
                    result = json.loads(complete[0])
                    journal_path.unlink()
                    _sync_directory(root)
                    return result
            instant = time.time() if now is None else now
            if journal:
                old = journal['plan']
                active_job, previous_job = old['active_job'], old['previous_job']
                compatibility_hash, ttl_seconds = old['compatibility_hash'], old['ttl_seconds']
                instant = old['checkpoint_cutoff'] + ttl_seconds
            db.execute('BEGIN IMMEDIATE')
            plan = _plan(db, active_job=active_job, previous_job=previous_job,
                         compatibility_hash=compatibility_hash, ttl_seconds=ttl_seconds, now=instant)
            if journal:
                # Never expand a replay's deletion set after new jobs appear.
                plan['obsolete_jobs'] = sorted(set(plan['obsolete_jobs']) & set(journal['plan']['obsolete_jobs']))
            before = _counts(db)
            result = {'applied': apply, 'plan': plan, 'before': before,
                      'runtime_files_deleted': 0, 'artifact_gc': 'disabled: no reader-safe artifact deletion protocol'}
            if apply:
                journal = journal or {'schema_version': 1, 'cache_root': str(root), 'operation_id': uuid.uuid4().hex, 'plan': plan}
                _write_journal(journal_path, journal)
                hook('marked')
            result['jobs_marked_collected'] = _delete_unreachable(db, plan['obsolete_jobs'], plan['checkpoint_cutoff'])
            hook('deleted')
            after = _counts(db)
            result.update(after=after, removed={key: before[key] - after[key] for key in before},
                          reclaimed_bytes_kind='logical reusable SQLite pages; no VACUUM or physical space claim')
            violations = db.execute('PRAGMA foreign_key_check').fetchone()
            if violations:
                raise IndexingStateError('GC detected a foreign-key inconsistency; deletion rolled back')
            result['budget'] = disk_budget_metrics(root, min_free_bytes=min_free_bytes, min_free_percent=min_free_percent,
                max_payload_bytes=max_payload_bytes, max_state_bytes=max_state_bytes, payload_bytes=after['payload_bytes'])
            if apply:
                db.execute('CREATE TABLE IF NOT EXISTS operator_gc_runs(operation_id TEXT PRIMARY KEY, completed_at REAL NOT NULL, metrics_json TEXT NOT NULL)')
                db.execute('INSERT INTO operator_gc_runs VALUES(?,?,?)', (journal['operation_id'], time.time(), json.dumps(result)))
                hook('before_commit')
                db.commit()
                hook('committed')
                journal_path.unlink()
                _sync_directory(root)
            else:
                db.rollback()
            return result
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
