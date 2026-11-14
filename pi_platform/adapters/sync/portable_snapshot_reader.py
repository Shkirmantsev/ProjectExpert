"""Verify complete source membership before a portable snapshot touches runtime."""
from contextlib import contextmanager
import json
from pathlib import Path
import re

from .portable_format import (
    ROOT, PortableSnapshotError, decode, read_snapshot, sha, source_path, spool,
)


def eligible_path(path, policy):
    source_path(path)
    return (policy in {None, '', 'SNAPSHOT'} and not path.startswith(('tmp/', 'local/', '.'))
            and not path.startswith(tuple(f'project-knowledge/{p}/' for p in
                                         ('chunks', 'graph', 'objects', 'manifests', 'sources', 'vectors'))))


def validate_payload(raw, *, local_root=None):
    """Never strip identity-bearing data or guess how to relocate parser assets."""
    try:
        body = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise PortableSnapshotError('Invalid canonical payload') from exc
    if not isinstance(body, dict):
        raise PortableSnapshotError('Canonical payload must be a JSON object')
    def walk(value, key=''):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(v, k)
        elif isinstance(value, list):
            for item in value:
                walk(item, key)
        elif isinstance(value, str):
            if local_root and str(local_root) in value and key not in {'rawText', 'contextualText', 'retrieval_text'}:
                raise PortableSnapshotError('Machine-bound generated metadata cannot be portable')
            if key in {'securityClassification', 'security_class'} and value.lower() not in {'public', 'unclassified'}:
                raise PortableSnapshotError('Restricted/unknown payload security classification')
            if key in {'policy', 'businessDomain'} and value.upper() in {'LOCAL_ONLY', 'REFERENCE', 'CONFIDENTIAL', 'SECRET'}:
                raise PortableSnapshotError('Restricted derived payload classification')
            if key == 'asset_id' and value:
                raise PortableSnapshotError('Parser-private media asset is not portable text; retain local indexing')
            if key in {'sourcePath', 'sourceReference', 'cas_path', 'uri'}:
                source_path(value)
            if key.lower() in {'password', 'secret', 'api_key', 'apikey', 'access_token', 'authorization', 'auth_token', 'refresh_token', 'prompt', 'system_prompt'} and value:
                raise PortableSnapshotError('Credential metadata cannot be exported')
            if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:ghp_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{32,})', value):
                raise PortableSnapshotError('Credential-like content cannot be exported')
    walk(body)
    return body


def payloads_for(db, addresses):
    for address in addresses:
        row = db.execute("SELECT body FROM records WHERE kind='payload' AND id=?", (address,)).fetchone()
        if row is None:
            raise PortableSnapshotError('Incomplete portable source membership')
        yield address, json.loads(row[0])['body']['raw'].encode('utf-8')


def validate_records(db):
    db.execute('CREATE TEMP TABLE membership(source TEXT,address TEXT,PRIMARY KEY(source,address))')
    db.execute('CREATE TEMP TABLE source_paths(folded TEXT PRIMARY KEY)')
    for identity, raw in db.execute("SELECT id,body FROM records WHERE kind='payload' ORDER BY id"):
        payload = json.loads(raw)['body']['raw'].encode('utf-8')
        if sha(payload) != identity:
            raise PortableSnapshotError('Canonical payload address mismatch')
        validate_payload(payload)
    for sid, raw in db.execute("SELECT id,body FROM records WHERE kind='source' ORDER BY id"):
        source = json.loads(raw)['body']
        path = source['path']
        if sid != 'repo:' + source_path(path) or not eligible_path(path, source['policy']):
            raise PortableSnapshotError('Ineligible portable source')
        try:
            db.execute('INSERT INTO source_paths VALUES(?)', (path.casefold(),))
        except Exception as exc:
            raise PortableSnapshotError('Colliding portable source names') from exc
        for key in ('sourceHash', 'pipelineKey', 'metadataKey'):
            if not re.fullmatch('[a-f0-9]{64}', source[key]):
                raise PortableSnapshotError('Invalid portable source compatibility identity')
        summary = json.loads(source['summary'])
        if (any(type(summary.get(key)) is not int or summary[key] < 0
                for key in ('chunkCount', 'entityCount', 'relationCount', 'evidenceCount'))
                or summary.get('knowledgeState') not in {'verified', 'inferred', 'assumption', 'conflicting', 'stale', 'unknown'}
                or type(summary.get('degraded')) is not bool):
            raise PortableSnapshotError('Invalid complete source summary contract')
        addresses = summary['addresses']
        if not isinstance(addresses, list) or any(not isinstance(a, str) or not re.fullmatch('[a-f0-9]{64}', a) for a in addresses):
            raise PortableSnapshotError('Invalid portable source membership')
        source_bytes = 0
        for address, payload in payloads_for(db, dict.fromkeys(addresses)):
            value = json.loads(payload)
            value = value.get('chunk', value)
            owner = value.get('metadata', {}).get('documentId', '')
            if owner.startswith('repo:') and owner != sid:
                raise PortableSnapshotError('Portable payload source ownership mismatch')
            provenance = value.get('provenance', {})
            if provenance.get('sourceHash') and provenance['sourceHash'] != source['sourceHash']:
                raise PortableSnapshotError('Portable source provenance hash mismatch')
            source_bytes += len(payload)
            if source_bytes > 64 * 1024 * 1024:
                raise PortableSnapshotError("Portable source result exceeds 64 MiB import buffer limit")
            db.execute('INSERT INTO membership VALUES(?,?)', (sid, address))
    if db.execute("SELECT count(*) FROM records WHERE kind='payload' AND id NOT IN (SELECT address FROM membership)").fetchone()[0]:
        raise PortableSnapshotError('Unowned portable payload')
    # Chunk identities bind vectors to permitted source membership.
    db.execute('CREATE TEMP TABLE chunks(id TEXT PRIMARY KEY,content_hash TEXT,text_hash TEXT,preferred INTEGER)')
    db.execute('CREATE TEMP TABLE facts(id TEXT PRIMARY KEY)')
    db.execute('CREATE TEMP TABLE refs(id TEXT NOT NULL)')
    for (raw,) in db.execute("SELECT body FROM records WHERE kind='payload'"):
        body = json.loads(json.loads(raw)['body']['raw'])
        body = body.get('chunk', body)
        if body.get('id'):
            db.execute('INSERT OR IGNORE INTO facts VALUES(?)', (body['id'],))
        if {'sourceId', 'targetId'}.issubset(body):
            db.executemany('INSERT INTO refs VALUES(?)', [(body['sourceId'],), (body['targetId'],)])
        if body.get('rawText') and body.get('parentId'):
            db.execute('INSERT INTO refs VALUES(?)', (body['parentId'],))
        for key in ('childIds', 'entityIds', 'sectionIds', 'chunkIds'):
            db.executemany('INSERT INTO refs VALUES(?)', ((value,) for value in body.get(key, [])))
        if body.get('rawText') and body.get('id'):
            previous = db.execute('SELECT content_hash FROM chunks WHERE id=?', (body['id'],)).fetchone()
            if previous and previous[0] != body['contentHash']:
                raise PortableSnapshotError('Conflicting chunk content identity')
            contextual = body.get('metadata', {}).get('extensions', {}).get('retrieval_text')
            text = contextual or body.get('contextualText') or body['rawText']
            db.execute('''INSERT INTO chunks VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
                text_hash=excluded.text_hash,preferred=excluded.preferred
                WHERE excluded.preferred>chunks.preferred''',
                (body['id'], body['contentHash'], sha(text.encode()), int(bool(contextual))))
    if db.execute('SELECT 1 FROM refs WHERE id NOT IN (SELECT id FROM facts) LIMIT 1').fetchone():
        raise PortableSnapshotError('Dangling portable graph/document reference')
    from .portable_vectors import decode_record
    for identity, raw in db.execute("SELECT id,body FROM records WHERE kind='vector'"):
        vector = decode_record(json.loads(raw)['body'])
        if identity != vector.embedding_profile_hash + ':' + vector.chunk_id:
            raise PortableSnapshotError('Vector identity mismatch')
        row = db.execute('SELECT content_hash,text_hash FROM chunks WHERE id=?', (vector.chunk_id,)).fetchone()
        if row != (vector.content_hash, vector.created_from_retrieval_text_hash):
            raise PortableSnapshotError('Unowned vector or wrong chunk content')


@contextmanager
def verified_snapshot(knowledge_root, cache_root, *, root_raw=None):
    with spool(Path(cache_root) / 'portable-work') as db:
        try:
            report = read_snapshot(knowledge_root, db, root_raw=root_raw)
            validate_records(db)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, PortableSnapshotError):
                raise
            raise PortableSnapshotError(f'Invalid portable record contract: {exc}') from exc
        from .portable_format import confined, read_bounded
        if root_raw is None:
            original_root = read_bounded(confined(knowledge_root, ROOT))
            if decode(original_root).get('snapshotId') != report['snapshotId']:
                raise PortableSnapshotError('Portable root moved during verification')
        yield db, report
        if root_raw is None and read_bounded(confined(knowledge_root, ROOT)) != original_root:
            raise PortableSnapshotError('Portable root moved during import')
