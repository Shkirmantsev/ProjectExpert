"""Independent checked text projections; never complete original source outputs."""
import json
import re

from .portable_format import PortableSnapshotError, add_record, encode, sha, source_path
from .portable_snapshot_reader import eligible_path, validate_payload

PROJECTION = 'checked-text/1'
# Source-wide policy, unknown provenance and transitive dependencies are not
# recoverable by deleting text. Only content-level exclusions may project text.
PROJECTABLE = {'sensitive-source', 'restricted-summary', 'restricted-payload'}


def validate_context(identity, body):
    if (not isinstance(body, dict) or set(body) != {'projection', 'path', 'sourceHash', 'text', 'textHash'}
            or body['projection'] != PROJECTION or not eligible_path(body['path'], '')
            or not isinstance(body['text'], str) or not body['text'].strip()
            or not isinstance(body['sourceHash'], str) or not re.fullmatch('[a-f0-9]{64}', body['sourceHash'])
            or sha(body['text'].encode()) != body['textHash'] or sha(encode(body)) != identity):
        raise PortableSnapshotError('Invalid checked context identity')
    source_path(body['path'])
    validate_payload(encode(body))
    return body


def project_contexts(db, production, generation):
    """Read persisted source outputs only; no parsing, OCR, models or local writes."""
    db.execute('CREATE TEMP TABLE context_vectors(id TEXT PRIMARY KEY,original_id TEXT,original_content TEXT,text_hash TEXT)')
    db.execute('''CREATE TEMP TABLE context_candidates(original_id TEXT PRIMARY KEY,
        sid TEXT,source_hash TEXT,original_content TEXT,text TEXT,preferred INTEGER)''')
    for sid, reason in db.execute("SELECT sid,reason FROM admission WHERE reason<>'' ORDER BY sid"):
        if reason not in PROJECTABLE:
            continue
        rows = list(production.execute('''SELECT p.payload,o.source_hash FROM canonical_payloads p
            JOIN source_payload_membership m USING(address)
            JOIN source_outputs o USING(source_id,source_hash,pipeline_key,metadata_key)
            JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
            WHERE g.generation=? AND g.source_id=?''', (generation, sid)))
        # Inspect provenance even in rejected aggregate payloads. Content rejection
        # must not conceal a protected contributor from otherwise clean fragments.
        restricted = False
        for raw, _ in rows:
            try:
                pending = [json.loads(raw)]
            except (ValueError, TypeError):
                restricted = True; break
            while pending and not restricted:
                node = pending.pop()
                if isinstance(node, list):
                    pending.extend(node)
                elif isinstance(node, dict):
                    for field, item in node.items():
                        pending.append(item)
                        dependencies = []
                        if field in {'sourceIds', 'derivedFrom', 'dependencies'}:
                            if not isinstance(item, list) or any(not isinstance(d, str) or not d.startswith('repo:') for d in item):
                                restricted = True; break
                            dependencies = item
                        elif field == 'documentId' and isinstance(item, str) and item.startswith('repo:'):
                            dependencies = [item]
                        elif field in {'sourcePath', 'sourceReference'} and isinstance(item, str):
                            dependencies = ['repo:' + item]
                        elif field == 'policy' and item is not None and item not in ('', 'SNAPSHOT'):
                            restricted = True; break
                        elif field in {'securityClassification', 'security_class'} and item is not None and (
                                not isinstance(item, str) or item.lower() not in {'public', 'unclassified'}):
                            restricted = True; break
                        for dependency in dependencies:
                            if dependency == sid:
                                continue
                            admission = db.execute('SELECT reason FROM admission WHERE sid=?', (dependency,)).fetchone()
                            if admission is None or admission[0]:
                                restricted = True; break
            if restricted:
                break
        if restricted:
            continue
        for raw, digest in rows:
            try:
                value = validate_payload(raw)
            except PortableSnapshotError:
                continue
            value = value.get('chunk', value)
            if not value.get('rawText') or not value.get('id') or not value.get('contentHash'):
                continue
            contextual = value.get('metadata', {}).get('extensions', {}).get('retrieval_text')
            text = contextual or value.get('contextualText') or value['rawText']
            db.execute('''INSERT INTO context_candidates VALUES(?,?,?,?,?,?)
                ON CONFLICT(original_id) DO UPDATE SET text=excluded.text,preferred=excluded.preferred
                WHERE excluded.preferred>context_candidates.preferred''',
                (value['id'], sid, digest, value['contentHash'], text, int(bool(contextual))))
    for cid, sid, digest, original_content, text, _ in db.execute('SELECT * FROM context_candidates ORDER BY original_id'):
        body = {'projection': PROJECTION, 'path': sid.removeprefix('repo:'), 'sourceHash': digest,
                'text': text, 'textHash': sha(text.encode())}
        identity = sha(encode(body))
        validate_context(identity, body)
        if db.execute("SELECT 1 FROM records WHERE kind='context' AND id=?", (identity,)).fetchone():
            continue
        add_record(db, 'context', identity, body)
        db.execute('INSERT INTO context_vectors VALUES(?,?,?,?)', (identity, cid, original_content, body['textHash']))
    return db.execute("SELECT count(*) FROM records WHERE kind='context'").fetchone()[0]


def context_chunks(db, *, existing_sources=(), inventory=None, reviews=None):
    """Read-only search evidence. Never seed the complete source ingestion cache."""
    existing = set(existing_sources)
    inventory = inventory or {}; reviews = reviews or {}
    for identity, raw in db.execute("SELECT id,body FROM records WHERE kind='context' ORDER BY id"):
        body = json.loads(raw)['body']
        sid = 'repo:' + body['path']
        entry = inventory.get(body['path'])
        if (sid in existing or reviews.get(body['path'], {}).get('classification') == 'confidential'
                or entry and (entry.content_hash != body['sourceHash'] or not eligible_path(entry.path, entry.policy))):
            continue
        yield identity, body
