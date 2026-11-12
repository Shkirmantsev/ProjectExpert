"""Resumable derived artifacts; closed standalone databases are promoted."""
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3

from pi_platform.adapters.runtime.sqlite_fts_full_text_index import SqliteFtsFullTextIndex


def atomic_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('wb') as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if os.name == 'posix':
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def _valid_exact(path, fingerprint, expected):
    if not path.is_file():
        return False
    try:
        with closing(sqlite3.connect(f'{path.resolve().as_uri()}?mode=ro', uri=True)) as db:
            identity = db.execute('SELECT fingerprint FROM build_identity').fetchone()
            count = db.execute('SELECT count(*) FROM runtime_fulltext_fts').fetchone()[0]
            rows = dict(db.execute('SELECT chunk_id,text_hash FROM build_chunks'))
            actual = {cid: hashlib.sha256(text.encode()).hexdigest()
                      for cid, text in db.execute('SELECT document_id,text FROM runtime_fulltext_fts')}
            return (identity == (fingerprint,) and count == len(expected) and rows == expected and actual == expected
                    and db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok')
    except sqlite3.DatabaseError:
        return False


def build_exact(path, documents, fingerprint, *, batch_size=256, progress=None):
    """Resume committed rows; backup live WAL into a self-contained final file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    documents = sorted(documents, key=lambda row: row[0])
    expected = {cid: hashlib.sha256(text.encode()).hexdigest() for cid, text in documents}
    if len(expected) != len(documents):
        raise ValueError('Duplicate exact index document identity')
    if _valid_exact(path, fingerprint, expected):
        if progress:
            progress(len(documents), len(documents))
        return SqliteFtsFullTextIndex(db_path=str(path))
    building = path.with_name(path.stem + '.building.sqlite')
    with closing(sqlite3.connect(building)) as db:
        if db.execute('PRAGMA journal_mode=WAL').fetchone()[0].lower() != 'wal':
            raise RuntimeError('Exact index requires SQLite WAL support')
        db.execute('PRAGMA synchronous=FULL')
        db.execute('CREATE VIRTUAL TABLE IF NOT EXISTS runtime_fulltext_fts USING fts5(document_id UNINDEXED,family UNINDEXED,text)')
        db.execute('CREATE TABLE IF NOT EXISTS build_identity(fingerprint TEXT PRIMARY KEY)')
        db.execute('CREATE TABLE IF NOT EXISTS build_chunks(chunk_id TEXT PRIMARY KEY,text_hash TEXT NOT NULL)')
        old = db.execute('SELECT fingerprint FROM build_identity').fetchone()
        if old and old != (fingerprint,):
            raise RuntimeError('Exact building artifact fingerprint mismatch; preserve for diagnosis')
        with db:
            db.execute('INSERT OR IGNORE INTO build_identity VALUES(?)', (fingerprint,))
        committed = dict(db.execute('SELECT chunk_id,text_hash FROM build_chunks'))
        if any(expected.get(cid) != digest for cid, digest in committed.items()):
            raise RuntimeError('Exact building artifact contains unexpected records')
        actual = {}
        for cid, text in db.execute('SELECT document_id,text FROM runtime_fulltext_fts'):
            actual.setdefault(cid, []).append(hashlib.sha256(text.encode()).hexdigest())
        # Reconcile the authoritative rows rather than trusting a cursor/count.
        invalid = {cid for cid in set(committed) | set(actual)
                   if actual.get(cid) != [expected.get(cid)] or cid not in committed}
        with db:
            db.executemany('DELETE FROM runtime_fulltext_fts WHERE document_id=?', ((cid,) for cid in invalid))
            db.executemany('DELETE FROM build_chunks WHERE chunk_id=?', ((cid,) for cid in invalid))
        for cid in invalid:
            committed.pop(cid, None)
        pending = [(cid, text) for cid, text in documents if cid not in committed]
        count = len(committed)
        if progress:
            progress(count, len(documents))
        for start in range(0, len(pending), batch_size):
            batch = pending[start:start + batch_size]
            with db:
                db.executemany('INSERT INTO runtime_fulltext_fts(document_id,family,text) VALUES(?,\'chunks\',?)', batch)
                db.executemany('INSERT INTO build_chunks VALUES(?,?)', ((cid, expected[cid]) for cid, _ in batch))
            count += len(batch)
            if progress:
                progress(count, len(documents))
        if db.execute('PRAGMA wal_checkpoint(TRUNCATE)').fetchone()[0] != 0:
            raise RuntimeError('Exact artifact WAL checkpoint is busy')
        temporary = path.with_name(path.name + '.ready.tmp')
        with closing(sqlite3.connect(temporary)) as standalone:
            db.backup(standalone)
            standalone.execute('PRAGMA journal_mode=DELETE')
            if standalone.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('Exact artifact integrity validation failed')
    if not _valid_exact(temporary, fingerprint, expected):
        raise RuntimeError('Exact artifact row validation failed')
    with temporary.open('r+b') as handle:
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    if os.name == 'posix':
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    # Retain committed staging until final promotion is known complete. Deleting
    # closed files here is safe and never touches a previously served artifact.
    for suffix in ('', '-wal', '-shm'):
        building.with_name(building.name + suffix).unlink(missing_ok=True)
    return SqliteFtsFullTextIndex(db_path=str(path))


def build_graph_shards(graph, entities, relations, *, progress=None):
    """Write each deterministic shard once; restart checks bytes before reuse."""
    from pi_platform.core.canonical.value_types import to_canonical_json
    groups = {}
    edge_sources = set()
    for entity in sorted(entities, key=lambda item: item.id):
        relative = f'nodes/{graph._id_hash(entity.id)[:2]}/shard.jsonl'
        groups.setdefault(relative, []).append(to_canonical_json(entity).rstrip(b'\n'))
    for relation in sorted(relations, key=lambda item: (item.sourceId, item.targetId, item.family)):
        relative = f'edges/{graph._id_hash(relation.sourceId)[:2]}/shard.jsonl'
        groups.setdefault(relative, []).append(to_canonical_json(relation).rstrip(b'\n'))
        edge_sources.add((relation.sourceId, relative))
    groups['edge-index.jsonl'] = [json.dumps({'sourceId': sid, 'shardPath': relative}, sort_keys=True).encode()
                                  for sid, relative in sorted(edge_sources)]
    checksums = {}
    for count, (relative, lines) in enumerate(sorted(groups.items()), 1):
        payload = b'\n'.join(lines) + (b'\n' if lines else b'')
        digest = hashlib.sha256(payload).hexdigest()
        path = graph.root / relative
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            atomic_bytes(path, payload)
        checksums[relative] = digest
        if progress:
            progress(count, len(groups))
    atomic_bytes(graph.root / 'ready.json', json.dumps({'version': 1, 'shards': checksums,
        'entities': len(entities), 'relations': len(relations)}, sort_keys=True).encode())
