"""Bounded, deterministic text snapshots; no live database is a portable artifact."""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tempfile

ROOT = 'manifests/portable-v2.json'
SCHEMA = 'portable/v2'
MAX_BYTES = 8 * 1024 * 1024
READ_MAX_BYTES = 16 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
MAX_FILES = 100000
ATTRIBUTES = {
    'manifests/.gitattributes': b'portable-v2.json -text\nportable-v2/*.json -text\n.gitattributes -text\n',
    'objects/portable-v2/.gitattributes': b'*.jsonl -text\n.gitattributes -text\n',
}


class PortableSnapshotError(ValueError):
    """Declared portable state is corrupt, incomplete, unsafe or incompatible."""


def encode(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False,
                       separators=(',', ':'), allow_nan=False) + '\n').encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source_path(value):
    """Cross-platform source names: do not silently fold case or rewrite identity."""
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise PortableSnapshotError('Unsafe portable source path')
    path = PurePosixPath(value)
    if not path.parts or path.is_absolute() or str(path) != value or any(p in {'.', '..'} for p in path.parts):
        raise PortableSnapshotError('Unsafe portable source path')
    for part in path.parts:
        stem = part.split('.')[0].upper()
        if (part.endswith((' ', '.')) or any(ord(c) < 32 or c in '<>"|?*' for c in part)
                or stem in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)),
                            *(f'LPT{i}' for i in range(1, 10))}):
            raise PortableSnapshotError('Nonportable Windows source name')
    return value


def confined(root, relative):
    root = Path(root).absolute()
    source_path(relative)
    path = root / relative
    for parent in (root, *path.relative_to(root).parents):
        candidate = parent if parent.is_absolute() else root / parent
        if candidate.is_symlink():
            raise PortableSnapshotError('Symlink in portable path')
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise PortableSnapshotError('Portable path escapes canonical root')
    if path.exists():
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise PortableSnapshotError('Portable file must be a regular unlinked file')
    return path


def read_bounded(path, cap=READ_MAX_BYTES):
    with path.open('rb') as handle:
        raw = handle.read(cap + 1)
    if len(raw) > cap:
        raise PortableSnapshotError(f'Oversized portable file: {path.name}')
    return raw


def decode(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise PortableSnapshotError('Duplicate JSON key')
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))
        if encode(value) != raw:
            raise PortableSnapshotError('Noncanonical portable JSON encoding')
        return value
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise PortableSnapshotError(f'Invalid portable JSON: {exc}') from exc


@contextmanager
def spool(directory):
    Path(directory).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='portable-', dir=directory) as name:
        db = sqlite3.connect(Path(name) / 'records.sqlite')
        try:
            db.execute('PRAGMA temp_store=FILE')
            db.execute('CREATE TABLE records(kind TEXT,id TEXT,bucket TEXT,body BLOB,PRIMARY KEY(kind,id))')
            yield db
        finally:
            db.close()


def add_record(db, kind, identity, body):
    if kind not in {'source', 'payload', 'vector'} or not isinstance(identity, str) or not identity:
        raise PortableSnapshotError('Invalid record identity')
    raw = encode({'kind': kind, 'id': identity, 'body': body})
    try:
        db.execute('INSERT INTO records VALUES(?,?,?,?)', (kind, identity, sha(identity.encode())[:2], raw))
    except sqlite3.IntegrityError as exc:
        raise PortableSnapshotError('Duplicate portable record identity') from exc


def write_snapshot(db, root, *, cap=MAX_BYTES, max_total=MAX_TOTAL, max_files=MAX_FILES):
    """Disk-backed ordering; immutable hashed shards/pages; root installed last.

    Prefix buckets are segmented deterministically at record boundaries. Replacing
    a bucket can churn its segments, but cannot rewrite an unrelated bucket.
    """
    root = Path(root)
    total = files = 0
    accounted = set()
    def store(raw, kind):
        nonlocal total, files
        if len(raw) > cap:
            raise PortableSnapshotError(f'Oversized portable {kind}: {len(raw)} bytes')
        digest = sha(raw)
        relative = (f'objects/portable-v2/{digest}.jsonl' if kind == 'shard'
                    else f'manifests/portable-v2/{digest}.json')
        path = confined(root, relative)
        if relative not in accounted:
            accounted.add(relative)
            files += 1
            total += len(raw)
            if total > max_total or files + 1 > max_files:
                raise PortableSnapshotError('Portable snapshot storage budget exceeded')
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            from pi_platform.core.canonical.durable_write import atomic_write_bytes
            atomic_write_bytes(path, raw)
        elif read_bounded(path, cap) != raw:
            raise PortableSnapshotError('Immutable portable file conflict')
        return {'path': relative, 'sha256': digest, 'bytes': len(raw), 'type': kind}

    # Manifest descriptors are also spooled; do not retain millions in RAM.
    db.execute('CREATE INDEX IF NOT EXISTS records_order ON records(kind,bucket,id)')
    db.execute('CREATE TEMP TABLE descriptors(level INTEGER,seq INTEGER,body BLOB,PRIMARY KEY(level,seq))')
    count = seq = 0
    for kind, bucket in db.execute('SELECT DISTINCT kind,bucket FROM records ORDER BY kind,bucket'):
        buffer, records = bytearray(), 0
        def flush():
            nonlocal seq, buffer, records
            if not records:
                return
            desc = {**store(bytes(buffer), 'shard'), 'records': records}
            db.execute('INSERT INTO descriptors VALUES(0,?,?)', (seq, encode(desc)))
            seq += 1
            buffer, records = bytearray(), 0
        for (raw,) in db.execute('SELECT body FROM records WHERE kind=? AND bucket=? ORDER BY id', (kind, bucket)):
            if len(raw) > cap:
                raise PortableSnapshotError(f'Oversized {kind} record: {len(raw)} bytes')
            if len(buffer) + len(raw) > cap:
                flush()
            buffer.extend(raw)
            records += 1
            count += 1
        flush()
    level = 0
    while True:
        n = db.execute('SELECT count(*) FROM descriptors WHERE level=?', (level,)).fetchone()[0]
        if n <= 1:
            refs = [decode(row[0]) for row in db.execute('SELECT body FROM descriptors WHERE level=? ORDER BY seq', (level,))]
            break
        group, sequence = [], 0
        def page():
            nonlocal sequence, group
            desc = store(encode({'children': group}), 'page')
            db.execute('INSERT INTO descriptors VALUES(?,?,?)', (level + 1, sequence, encode(desc)))
            sequence += 1
            group = []
        for (raw,) in db.execute('SELECT body FROM descriptors WHERE level=? ORDER BY seq', (level,)):
            desc = decode(raw)
            if len(encode({'children': [*group, desc]})) > cap:
                if len(group) < 2:
                    raise PortableSnapshotError('Portable cap too small for manifest fanout')
                page()
            group.append(desc)
        if group:
            page()
        level += 1
    for relative, raw in ATTRIBUTES.items():
        path = confined(root, relative)
        if path.exists() and read_bounded(path, cap) != raw:
            raise PortableSnapshotError('Existing portable Git attributes conflict')
        path.parent.mkdir(parents=True, exist_ok=True)
        from pi_platform.core.canonical.durable_write import atomic_write_bytes
        atomic_write_bytes(path, raw)
        total += len(raw)
        files += 1
    body = {'schema': SCHEMA, 'fileCap': cap, 'records': count, 'children': refs}
    body['snapshotId'] = sha(encode(body))
    raw = encode(body)
    if len(raw) > cap or total + len(raw) > max_total or files + 1 > max_files:
        raise PortableSnapshotError('Portable root storage budget exceeded')
    from pi_platform.core.canonical.durable_write import atomic_write_bytes
    path = confined(root, ROOT)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(path, raw)
    db.execute('DROP TABLE descriptors')
    return body


def read_snapshot(root, db, *, cap=READ_MAX_BYTES, max_total=MAX_TOTAL, max_files=MAX_FILES, root_raw=None):
    root = Path(root)
    body = decode(root_raw if root_raw is not None else read_bounded(confined(root, ROOT), cap))
    if not isinstance(body, dict):
        raise PortableSnapshotError('Portable root must be a JSON object')
    identity = body.get('snapshotId')
    if body.get('schema') != SCHEMA or sha(encode({k: v for k, v in body.items() if k != 'snapshotId'})) != identity:
        raise PortableSnapshotError('Portable root schema or identity mismatch')
    declared_cap = body.get('fileCap')
    if type(declared_cap) is not int or not 512 <= declared_cap <= cap:
        raise PortableSnapshotError('Invalid portable file cap')
    cap = declared_cap
    if len(encode(body)) > cap or type(body.get('records')) is not int or body['records'] < 0:
        raise PortableSnapshotError('Invalid portable root size/count')
    total, files, records = len(encode(body)), 1, 0
    seen = set()
    for relative, expected in ATTRIBUTES.items():
        try:
            if read_bounded(confined(root, relative), cap) != expected:
                raise PortableSnapshotError('Portable Git attributes mismatch')
        except OSError as exc:
            raise PortableSnapshotError('Missing portable Git attributes') from exc
        seen.add(relative)
        total += len(expected)
        files += 1
    def visit(desc, depth):
        nonlocal total, files, records
        if depth > 32 or not isinstance(desc, dict):
            raise PortableSnapshotError('Invalid portable manifest depth/descriptor')
        relative, kind = desc.get('path', ''), desc.get('type')
        pattern = (r'objects/portable-v2/([a-f0-9]{64})\.jsonl' if kind == 'shard'
                   else r'manifests/portable-v2/([a-f0-9]{64})\.json' if kind == 'page' else '')
        match = re.fullmatch(pattern, relative) if pattern else None
        if not match or match[1] != desc.get('sha256') or relative in seen:
            raise PortableSnapshotError('Unsafe, duplicate or invalid portable descriptor')
        seen.add(relative)
        files += 1
        if files > max_files:
            raise PortableSnapshotError('Portable file budget exceeded')
        try:
            raw = read_bounded(confined(root, relative), cap)
        except OSError as exc:
            raise PortableSnapshotError(f'Missing portable file: {relative}') from exc
        total += len(raw)
        if total > max_total or len(raw) != desc.get('bytes') or sha(raw) != desc['sha256']:
            raise PortableSnapshotError(f'Portable checksum/size/budget mismatch: {relative}')
        if kind == 'page':
            for child in decode(raw)['children']:
                visit(child, depth + 1)
        else:
            rows = []
            for line in raw.splitlines(keepends=True):
                record = decode(line)
                if (set(record) != {'kind', 'id', 'body'} or record['kind'] not in {'source', 'payload', 'vector'}
                        or not isinstance(record['id'], str) or not record['id']):
                    raise PortableSnapshotError('Invalid portable record identity')
                # decode already proved exact canonical bytes. Do not encode
                # every record a second time just to insert the same bytes.
                rows.append((record['kind'], record['id'], sha(record['id'].encode())[:2], line))
            try:
                db.executemany('INSERT INTO records VALUES(?,?,?,?)', rows)
            except sqlite3.IntegrityError as exc:
                raise PortableSnapshotError('Duplicate portable record identity') from exc
            count = len(rows)
            if count != desc.get('records'):
                raise PortableSnapshotError('Portable shard count mismatch')
            records += count
    try:
        for desc in body['children']:
            visit(desc, 0)
        if records != body['records']:
            raise PortableSnapshotError('Portable root record count mismatch')
    except (KeyError, TypeError) as exc:
        raise PortableSnapshotError('Malformed portable snapshot structure') from exc
    return {**body, 'totalBytes': total, 'fileCount': files, 'paths': sorted({ROOT, *seen})}
