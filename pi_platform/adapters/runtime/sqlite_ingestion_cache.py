"""Durable, generation-scoped source results; no production in-memory mirror.

The coordinator holds an OS lock for the lifetime of this adapter. Workers own
only SourceBufferedCache overlays; the adapter serializes short transactions.
"""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import threading
import time
import uuid


class IndexingStateError(RuntimeError):
    pass


@contextmanager
def exclusive_indexer(cache_root):
    """Kernel-owned exclusion survives crashes without timestamp takeovers."""
    root = Path(cache_root)
    root.mkdir(parents=True, exist_ok=True)
    handle = (root / 'indexing.lock').open('a+b')
    locked = False
    try:
        if os.name == 'nt':
            import msvcrt
            # Windows permits locking beyond EOF. Do not initialize/read the
            # byte first: a competing mandatory lock also denies those I/Os.
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise IndexingStateError('Another index builder owns this cache') from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise IndexingStateError('Another index builder owns this cache') from exc
        locked = True
        yield
    finally:
        if locked:
            if os.name == 'nt':
                import msvcrt
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


_SCHEMA = '''
CREATE TABLE IF NOT EXISTS schema_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS canonical_payloads(
 address TEXT PRIMARY KEY, payload BLOB NOT NULL, checksum TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_outputs(
 source_id TEXT NOT NULL, source_hash TEXT NOT NULL, pipeline_key TEXT NOT NULL,
 metadata_key TEXT NOT NULL, summary_json BLOB NOT NULL, checksum TEXT NOT NULL,
 completed_at REAL NOT NULL,
 chunk_count INTEGER NOT NULL CHECK(chunk_count>=0),
 state TEXT NOT NULL CHECK(state IN ('complete','degraded')),
 PRIMARY KEY(source_id, source_hash, pipeline_key, metadata_key));
CREATE TABLE IF NOT EXISTS source_payload_membership(
 source_id TEXT NOT NULL, source_hash TEXT NOT NULL, pipeline_key TEXT NOT NULL,
 metadata_key TEXT NOT NULL, address TEXT NOT NULL REFERENCES canonical_payloads(address),
 PRIMARY KEY(source_id, source_hash, pipeline_key, metadata_key, address),
 FOREIGN KEY(source_id, source_hash, pipeline_key, metadata_key)
 REFERENCES source_outputs(source_id, source_hash, pipeline_key, metadata_key));
CREATE INDEX IF NOT EXISTS source_payload_by_address ON source_payload_membership(address);
CREATE TABLE IF NOT EXISTS generation_sources(
 generation TEXT NOT NULL, source_id TEXT NOT NULL, source_hash TEXT NOT NULL,
 pipeline_key TEXT NOT NULL, metadata_key TEXT NOT NULL,
 PRIMARY KEY(generation, source_id),
 FOREIGN KEY(source_id, source_hash, pipeline_key, metadata_key)
 REFERENCES source_outputs(source_id, source_hash, pipeline_key, metadata_key));
CREATE TABLE IF NOT EXISTS indexer_lease(
 root_id INTEGER PRIMARY KEY CHECK(root_id=1), owner_token TEXT NOT NULL,
 fence INTEGER NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS index_jobs(
 job_id TEXT PRIMARY KEY, compatibility_hash TEXT NOT NULL,
 fence INTEGER NOT NULL, state TEXT NOT NULL, active_stage TEXT,
 created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_compatibility ON index_jobs(compatibility_hash);
CREATE TABLE IF NOT EXISTS publication_intents(
 job_id TEXT PRIMARY KEY REFERENCES index_jobs(job_id), created_at REAL NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('prepared','committed')));
CREATE TABLE IF NOT EXISTS artifact_manifests(
 generation TEXT NOT NULL REFERENCES index_jobs(job_id), artifact_name TEXT NOT NULL,
 kind TEXT NOT NULL, stage_fingerprint TEXT NOT NULL, relative_path TEXT NOT NULL,
 sha256 TEXT NOT NULL, expected_count INTEGER NOT NULL CHECK(expected_count>=0),
 state TEXT NOT NULL CHECK(state IN ('preparing','ready','invalid')),
 PRIMARY KEY(generation,artifact_name));
CREATE TABLE IF NOT EXISTS index_stages(
 job_id TEXT NOT NULL REFERENCES index_jobs(job_id), stage TEXT NOT NULL,
 total_items INTEGER NOT NULL, completed_items INTEGER NOT NULL,
 failed_items INTEGER NOT NULL, degraded_items INTEGER NOT NULL,
 state TEXT NOT NULL, updated_at REAL NOT NULL,
 PRIMARY KEY(job_id,stage));
'''


class SqliteIngestionCache:
    def __init__(self, path, *, generation=None, compatibility_hash=''):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.generation = generation or uuid.uuid4().hex
        self.owner = uuid.uuid4().hex
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        if os.name == 'posix':
            os.chmod(self.path, 0o600)
        try:
            self._db.execute('PRAGMA foreign_keys=ON')
            if self._db.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
                raise IndexingStateError('Indexing state requires SQLite WAL support')
            self._db.execute('PRAGMA synchronous=FULL')
            self._db.execute('PRAGMA busy_timeout=30000')
            result = self._db.execute('PRAGMA quick_check').fetchone()[0]
            if result != 'ok':
                raise IndexingStateError('Indexing state integrity failure; preserve and restore the database')
            self._db.executescript(_SCHEMA)
            version = self._db.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
            if version and version[0] != '1':
                raise IndexingStateError('Unsupported indexing state schema; restore matching runtime')
            with self._db:
                self._db.execute("INSERT OR IGNORE INTO schema_meta VALUES('version','1')")
                prior = self._db.execute('SELECT fence FROM indexer_lease WHERE root_id=1').fetchone()
                self.fence = prior[0] + 1 if prior else 1
                self._db.execute('INSERT OR REPLACE INTO indexer_lease VALUES(1,?,?,?)',
                                 (self.owner, self.fence, time.time()))
                self._db.execute("UPDATE index_jobs SET state='interrupted' WHERE state='running'")
                now = time.time()
                self._db.execute('INSERT INTO index_jobs VALUES(?,?,?,?,?,?,?)',
                                 (self.generation, compatibility_hash, self.fence, 'running', None, now, now))
        except BaseException:
            self._db.close()
            raise

    def close(self):
        self._db.close()

    def _assert_fence(self):
        row = self._db.execute('SELECT owner_token,fence FROM indexer_lease WHERE root_id=1').fetchone()
        if row != (self.owner, self.fence):
            raise IndexingStateError('Stale index builder fence; candidate rejected')

    def assert_fence(self):
        with self._lock:
            self._assert_fence()

    @contextmanager
    def _write(self):
        # Begin before reading the fence: a deferred SELECT followed by a write
        # leaves a lease-takeover race for non-cooperating callers.
        with self._lock:
            try:
                self._db.execute('BEGIN IMMEDIATE')
                self._assert_fence()
                yield
                self._db.commit()
            except BaseException:
                self._db.rollback()
                raise

    @staticmethod
    def _verify_checksum(payload, expected):
        if hashlib.sha256(payload).hexdigest() != expected:
            raise IndexingStateError('Canonical state checksum mismatch; preserve database and restore verified backup')

    def source_buffer(self, source_id):
        return SourceBufferedCache(self, source_id)

    def select_sources(self, sources):
        """Seed candidate only with compatible source and metadata identities.

        Coordinators supply the pipeline key; the driver checks it again before reuse.
        """
        with self._write():
            self._assert_fence()
            for source in sources:
                sid, digest, metadata_key = source[:3]
                pipeline_key = source[3] if len(source) > 3 else None
                self._db.execute('DELETE FROM generation_sources WHERE generation=? AND source_id=?',
                                 (self.generation, sid))
                row = self._db.execute('''SELECT source_id,source_hash,pipeline_key,metadata_key
                    FROM source_outputs WHERE source_id=? AND source_hash=? AND metadata_key=?
                    AND (? IS NULL OR pipeline_key=?)
                    ORDER BY completed_at DESC LIMIT 1''', (sid, digest, metadata_key, pipeline_key, pipeline_key)).fetchone()
                if row:
                    self._db.execute('INSERT OR REPLACE INTO generation_sources VALUES(?,?,?,?,?)',
                                     (self.generation, *row))

    def source_ids(self):
        with self._lock:
            return tuple(r[0] for r in self._db.execute(
                'SELECT source_id FROM generation_sources WHERE generation=? ORDER BY source_id',
                (self.generation,)))

    def source_record(self, sid):
        with self._lock:
            row = self._db.execute('''SELECT o.source_hash,o.pipeline_key,o.metadata_key,o.summary_json,o.checksum
                FROM source_outputs o JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
                WHERE g.generation=? AND g.source_id=?''', (self.generation, sid)).fetchone()
            if row is None:
                return None
            digest, key, metadata, summary, checksum = row
            self._verify_checksum(summary, checksum)
            return {'hash': digest, 'key': key, 'metadata_key': metadata,
                    'addresses': tuple(json.loads(summary)['addresses'])}

    def source_is_current(self, sid, digest, metadata_key=None):
        record = self.source_record(sid)
        return bool(record and record['hash'] == digest and
                    (metadata_key is None or metadata_key == record['metadata_key']))

    def get(self, key):
        with self._lock:
            row = self._db.execute('''SELECT o.summary_json,o.checksum FROM source_outputs o
                JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
                WHERE g.generation=? AND o.pipeline_key=? LIMIT 1''', (self.generation, key)).fetchone()
            if row:
                self._verify_checksum(*row)
                return bytes(row[0])
            row = self._db.execute('''SELECT p.payload,p.checksum FROM canonical_payloads p
                JOIN source_payload_membership m USING(address)
                JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
                WHERE g.generation=? AND p.address=? LIMIT 1''', (self.generation, key)).fetchone()
            if row:
                self._verify_checksum(*row)
            return bytes(row[0]) if row else None

    def iter_records(self):
        # A separate read-only connection gives a bounded streaming snapshot and
        # keeps its cursor away from worker transactions on the writer handle.
        db = sqlite3.connect(f'{self.path.resolve().as_uri()}?mode=ro', uri=True)
        try:
            for payload, checksum in db.execute('''SELECT p.payload,p.checksum
                FROM canonical_payloads p WHERE p.address IN(
                    SELECT m.address FROM generation_sources g JOIN source_payload_membership m
                    USING(source_id,source_hash,pipeline_key,metadata_key) WHERE g.generation=?)
                ORDER BY p.address''', (self.generation,)):
                self._verify_checksum(payload, checksum)
                yield bytes(payload)
        finally:
            db.close()

    def invalidate_source(self, sid, *, stale=True):
        # Invalidation affects only candidate membership; immutable prior versions
        # and older generation readers remain usable.
        with self._write():
            self._assert_fence()
            self._db.execute('DELETE FROM generation_sources WHERE generation=? AND source_id=?',
                             (self.generation, sid))

    def complete_source_atomic(self, sid, digest, key, addresses, metadata_key, records):
        metadata_key = metadata_key or ''
        summary = records[key]
        if set(addresses) - records.keys():
            raise IndexingStateError('Incomplete source output; missing canonical payloads')
        encoded = json.loads(summary)
        if tuple(encoded['addresses']) != tuple(addresses):
            raise IndexingStateError('Source summary membership mismatch')
        with self._write():
            self._assert_fence()
            for address in set(addresses):
                payload = records[address]
                checksum = hashlib.sha256(payload).hexdigest()
                previous = self._db.execute('SELECT payload FROM canonical_payloads WHERE address=?', (address,)).fetchone()
                if previous and bytes(previous[0]) != payload:
                    raise IndexingStateError('Immutable canonical payload address conflict')
                self._db.execute('INSERT OR IGNORE INTO canonical_payloads VALUES(?,?,?)',
                                 (address, payload, checksum))
            identity = (sid, digest, key, metadata_key)
            checksum = hashlib.sha256(summary).hexdigest()
            previous = self._db.execute('SELECT checksum FROM source_outputs WHERE source_id=? AND source_hash=? AND pipeline_key=? AND metadata_key=?', identity).fetchone()
            if previous and previous[0] != checksum:
                raise IndexingStateError('Conflicting immutable source output')
            self._db.execute('INSERT OR IGNORE INTO source_outputs VALUES(?,?,?,?,?,?,?,?,?)',
                             (*identity, summary, checksum, time.time(), encoded.get('chunkCount', 0),
                              'degraded' if encoded.get('degraded', False) else 'complete'))
            self._db.executemany('INSERT OR IGNORE INTO source_payload_membership VALUES(?,?,?,?,?)',
                                 ((*identity, address) for address in set(addresses)))
            self._db.execute('INSERT OR REPLACE INTO generation_sources VALUES(?,?,?,?,?)',
                             (self.generation, *identity))
            counts = self._db.execute("""SELECT count(*),coalesce(sum(o.state='degraded'),0)
                FROM generation_sources g JOIN source_outputs o
                USING(source_id,source_hash,pipeline_key,metadata_key) WHERE g.generation=?""",
                (self.generation,)).fetchone()
            self._db.execute("""UPDATE index_stages SET completed_items=?,degraded_items=?,updated_at=?
                WHERE job_id=? AND stage='sources'""", (*counts, time.time(), self.generation))

    def import_legacy(self, path):
        """One-time import preserves the JSON; ignore orphaned historic records."""
        path = Path(path)
        if not path.is_file():
            return
        with self._lock:
            if self._db.execute("SELECT value FROM schema_meta WHERE key='legacy_import'").fetchone():
                return
            from pi_platform.adapters.runtime.legacy_ingestion_import import legacy_entries
            import shutil
            def file_digest(filename):
                digest = hashlib.sha256()
                with filename.open('rb') as handle:
                    for block in iter(lambda: handle.read(1024 * 1024), b''):
                        digest.update(block)
                return digest.hexdigest()
            backup = path.with_name('ingestion.pre-resumable.json')
            if not backup.exists():
                temporary = backup.with_suffix('.tmp')
                with path.open('rb') as reader, temporary.open('wb') as handle:
                    if os.name == 'posix':
                        os.chmod(temporary, 0o600)
                    shutil.copyfileobj(reader, handle, 1024 * 1024)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, backup)
                if os.name == 'posix':
                    descriptor = os.open(backup.parent, os.O_RDONLY)
                    try:
                        os.fsync(descriptor)
                    finally:
                        os.close(descriptor)
            digest = file_digest(backup)
            if digest != file_digest(path):
                raise IndexingStateError('Legacy backup differs from input; retain both before retrying migration')
            # TEMP tables spool legacy records on disk; no whole-file JSON/cache
            # mirror is constructed. SQL work and source buffers remain bounded.
            self._db.execute('PRAGMA temp_store=FILE')
            self._db.execute('CREATE TEMP TABLE legacy_payloads(address TEXT PRIMARY KEY,payload BLOB NOT NULL)')
            self._db.execute('CREATE TEMP TABLE legacy_sources(source_id TEXT PRIMARY KEY,record TEXT NOT NULL)')
            try:
                with self._db:
                    for section, key, value in legacy_entries(backup):
                        if section == 'records':
                            if not isinstance(value, str):
                                raise IndexingStateError('Legacy canonical record is not text')
                            self._db.execute('INSERT INTO legacy_payloads VALUES(?,?)', (key, value.encode()))
                        else:
                            self._db.execute('INSERT INTO legacy_sources VALUES(?,?)', (key, json.dumps(value)))
                source_cursor = self._db.execute('SELECT source_id,record FROM legacy_sources ORDER BY source_id')
                for sid, raw_record in source_cursor:
                    record = json.loads(raw_record)
                    key, addresses = record['key'], record['addresses']
                    values = {}
                    for address in {*addresses, key}:
                        row = self._db.execute('SELECT payload FROM legacy_payloads WHERE address=?', (address,)).fetchone()
                        if row is None:
                            raise IndexingStateError('Legacy source references a missing payload')
                        values[address] = bytes(row[0])
                    self.complete_source_atomic(sid, record['hash'], key, addresses,
                                                record.get('metadata_key'), values)
                with self._write():
                    self._db.execute('DELETE FROM generation_sources WHERE generation=?', (self.generation,))
                    self._db.execute("INSERT INTO schema_meta VALUES('legacy_import',?)", (digest,))
            finally:
                self._db.execute('DROP TABLE legacy_sources')
                self._db.execute('DROP TABLE legacy_payloads')

    def artifact(self, name, kind, path, fingerprint, expected_count):
        path = Path(path)
        relative = path.resolve().relative_to(self.path.parent.resolve()).as_posix()
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
            raise IndexingStateError('Linked candidate artifact is not publishable')
        checksum = _file_checksum(path)
        with self._write():
            self._db.execute('INSERT OR REPLACE INTO artifact_manifests VALUES(?,?,?,?,?,?,?,?)',
                (self.generation, name, kind, fingerprint, relative, checksum, expected_count, 'ready'))

    def stage(self, name, total, completed=0, failed=0, degraded=0, *, state='running'):
        with self._write():
            self._assert_fence()
            now = time.time()
            self._db.execute('INSERT OR REPLACE INTO index_stages VALUES(?,?,?,?,?,?,?,?)',
                             (self.generation, name, total, completed, failed, degraded, state, now))
            self._db.execute('UPDATE index_jobs SET active_stage=?,updated_at=? WHERE job_id=? AND fence=?',
                             (name, now, self.generation, self.fence))

    def finish(self, state):
        with self._write():
            self._assert_fence()
            now = time.time()
            self._db.execute('UPDATE index_jobs SET state=?,updated_at=? WHERE job_id=? AND fence=?',
                             (state, now, self.generation, self.fence))
            if state == 'failed':
                self._db.execute("UPDATE index_stages SET state='failed',updated_at=? WHERE job_id=? AND state='running'",
                                 (now, self.generation))


class SourceBufferedCache:
    """A failed pipeline only discards its private bytes, never prior state."""
    immutable_payloads = True
    def __init__(self, parent, sid):
        self.parent, self.sid = parent, sid
        self.records = {}
        self.invalidated = False

    def get(self, key):
        if key in self.records:
            return self.records[key]
        if self.invalidated:
            return None
        record = self.parent.source_record(self.sid)
        if record and key == record['key']:
            return self.parent.get(key)
        if record and key in record['addresses']:
            return self.parent.get(key)
        return None

    def put(self, key, payload):
        self.records[key] = payload

    def source_record(self, sid):
        return None if self.invalidated else self.parent.source_record(sid)

    def invalidate_source(self, sid, *, stale=True):
        if sid != self.sid:
            raise IndexingStateError('Source buffer identity mismatch')
        self.invalidated = True

    def complete_source(self, sid, digest, key, addresses, metadata_key=None):
        if sid != self.sid:
            raise IndexingStateError('Source buffer identity mismatch')
        self.parent.complete_source_atomic(sid, digest, key, addresses, metadata_key, self.records)


def indexing_progress(path):
    """Read latest durable status without constructing a writer or taking a lease."""
    path = Path(path)
    if not path.is_file():
        return {}
    db = sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True, timeout=1)
    db.row_factory = sqlite3.Row
    try:
        job = db.execute('SELECT * FROM index_jobs ORDER BY fence DESC LIMIT 1').fetchone()
        if job is None:
            return {}
        result = dict(job)
        result['stages'] = [dict(row) for row in db.execute('SELECT * FROM index_stages WHERE job_id=?', (job['job_id'],))]
        return result
    finally:
        db.close()


@contextmanager
def candidate_publication(cache_root, runtime):
    """Caller-owned publication holds exclusion and validates the latest fence."""
    if runtime.extra.get('index_engine') != 'resumable':
        yield
        return
    path = Path(cache_root) / 'indexing-state.sqlite'
    with exclusive_indexer(cache_root):
        db = sqlite3.connect(path)
        try:
            job_id, fence = runtime.extra['index_job_id'], runtime.extra['index_fence']
            row = db.execute('''SELECT j.state FROM index_jobs j JOIN indexer_lease l
                ON j.fence=l.fence WHERE j.job_id=? AND j.fence=?''', (job_id, fence)).fetchone()
            if row != ('ready',):
                raise IndexingStateError('Stale or incomplete candidate rejected before publication')
            artifacts = db.execute('SELECT artifact_name,kind,relative_path,sha256,state FROM artifact_manifests WHERE generation=?',
                                   (job_id,)).fetchall()
            if not {'exact', 'graph'}.issubset({row[0] for row in artifacts}):
                raise IndexingStateError('Candidate is missing required ready artifact manifests')
            for _, kind, relative, checksum, state in artifacts:
                artifact = Path(cache_root) / relative
                if (state != 'ready' or artifact.is_symlink()
                    or not artifact.resolve().is_relative_to(Path(cache_root).resolve())
                    or _file_checksum(artifact) != checksum):
                    raise IndexingStateError('Candidate artifact checksum mismatch before publication')
                if kind == 'sharded-graph':
                    manifest = json.loads(artifact.read_bytes())
                    for name, expected in manifest['shards'].items():
                        shard = artifact.parent / name
                        if (shard.is_symlink() or not shard.resolve().is_relative_to(artifact.parent.resolve())
                            or _file_checksum(shard) != expected):
                            raise IndexingStateError('Candidate graph shard checksum mismatch before publication')
            # The caller's filesystem snapshot and this SQLite audit pointer are
            # separate transactions. Retain a prepared intent across any failure
            # in that gap so GC cannot discard a possibly published generation.
            with db:
                db.execute("INSERT OR REPLACE INTO publication_intents VALUES(?,?,'prepared')", (job_id, time.time()))
            yield
            with db:
                current = db.execute("SELECT value FROM schema_meta WHERE key='active_job'").fetchone()
                if current and current[0] != job_id:
                    db.execute("INSERT OR REPLACE INTO schema_meta VALUES('previous_job',?)", (current[0],))
                db.execute("INSERT OR REPLACE INTO schema_meta VALUES('active_job',?)", (job_id,))
                db.execute("UPDATE index_jobs SET state='published',updated_at=? WHERE job_id=? AND fence=?",
                           (time.time(), job_id, fence))
                db.execute("UPDATE publication_intents SET state='committed' WHERE job_id=?", (job_id,))
        finally:
            db.close()


def _file_checksum(path):
    checksum = hashlib.sha256()
    try:
        with Path(path).open('rb') as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b''):
                checksum.update(block)
    except OSError as exc:
        raise IndexingStateError('Candidate artifact unavailable; rebuild or restore verified state') from exc
    return checksum.hexdigest()
