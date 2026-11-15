"""Disk-backed complete-source admission and transitive dependency closure."""
import json

from .portable_format import PortableSnapshotError, confined, sha
from .portable_snapshot_reader import eligible_path, validate_payload
from pi_platform.core.sync.export_policy import sensitive_file


def source_reviews(cache_root):
    from .portable_format import decode, read_bounded, confined
    path = cache_root / 'security-state' / 'source-reviews.json'
    return decode(read_bounded(confined(path.parent, path.name))) if path.exists() else {}


def project_sources(db, production, generation, inventory, target, cache_root):
    from pathlib import Path
    import os
    import subprocess
    reviews = source_reviews(cache_root)
    tracked = None
    if (target / '.git').exists():
        result = subprocess.run(['git', '-C', str(target), 'ls-files', '-z'],
                                capture_output=True, check=True)
        tracked = {os.fsdecode(path) for path in result.stdout.split(b'\0') if path}
    db.executescript('''
        CREATE TEMP TABLE admission(sid TEXT PRIMARY KEY,reason TEXT NOT NULL);
        CREATE TEMP TABLE owners(address TEXT,sid TEXT,PRIMARY KEY(address,sid));
        CREATE INDEX owner_source ON owners(sid);
        CREATE TEMP TABLE facts(id TEXT,sid TEXT,PRIMARY KEY(id,sid));
        CREATE TEMP TABLE refs(sid TEXT,id TEXT,PRIMARY KEY(sid,id));
        CREATE TEMP TABLE dependencies(cause TEXT,dependent TEXT,PRIMARY KEY(cause,dependent));
    ''')
    rows = production.execute('''SELECT o.source_id,o.source_hash,o.summary_json,o.checksum
        FROM source_outputs o JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
        WHERE g.generation=? ORDER BY o.source_id''', (generation,))
    for sid, digest, summary, checksum in rows:
        entry = inventory.get(sid.removeprefix('repo:'))
        if not sid.startswith('repo:') or entry is None or entry.content_hash != digest:
            raise PortableSnapshotError('Published generation does not match current source inventory')
        if sha(summary) != checksum:
            raise PortableSnapshotError('Production source summary checksum mismatch')
        reason = ''
        if not eligible_path(entry.path, entry.policy):
            reason = 'source-policy'
        else:
            review = reviews.get(entry.path, {})
            if review.get('classification') == 'confidential':
                reason = 'restricted-source'
            try:
                if sensitive_file(confined(target, entry.path)):
                    reason = 'sensitive-source'
            except Exception:
                reason = 'source-detector-unavailable'
            if tracked is not None and entry.path not in tracked:
                reason = reason or 'untracked-source'
        try:
            validate_payload(summary, local_root=target)
        except PortableSnapshotError:
            reason = reason or 'restricted-summary'
        db.execute('INSERT INTO admission VALUES(?,?)', (sid, reason))
        payloads = production.execute('''SELECT p.address,p.payload,p.checksum
            FROM canonical_payloads p JOIN source_payload_membership m USING(address)
            JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
            WHERE g.generation=? AND g.source_id=?''', (generation, sid))
        present = set()
        portable_identity = False
        for address, raw, checksum in payloads:
            if sha(raw) != checksum or checksum != address:
                raise PortableSnapshotError('Corrupt production source payload')
            present.add(address)
            db.execute('INSERT INTO owners VALUES(?,?)', (address, sid))
            try:
                value = validate_payload(raw, local_root=target)
            except PortableSnapshotError:
                db.execute("UPDATE admission SET reason='restricted-payload' WHERE sid=? AND reason=''", (sid,))
                continue
            value = value.get('chunk', value)
            portable_identity |= 'portable_identity' in value.get('metadata', {}).get('extensions', {})
            if value.get('id'):
                db.execute('INSERT OR IGNORE INTO facts VALUES(?,?)', (value['id'], sid))
            refs = []
            if {'sourceId', 'targetId'}.issubset(value):
                refs.extend((value['sourceId'], value['targetId']))
            if value.get('rawText') and value.get('parentId'):
                refs.append(value['parentId'])
            for key in ('childIds', 'entityIds', 'sectionIds', 'chunkIds'):
                refs.extend(value.get(key, []))
            db.executemany('INSERT OR IGNORE INTO refs VALUES(?,?)', ((sid, ref) for ref in refs))
            # Follow declared contributors at every nesting level, including
            # contextual enrichment and graph metadata added by adapters.
            pending = [value]
            while pending:
                node = pending.pop()
                if isinstance(node, list):
                    pending.extend(node)
                elif isinstance(node, dict):
                    for field, item in node.items():
                        pending.append(item)
                        if field in {'sourceIds', 'derivedFrom', 'dependencies'}:
                            dependencies = item
                            if not isinstance(dependencies, list) or any(not isinstance(d, str) or not d.startswith('repo:') for d in dependencies):
                                db.execute("UPDATE admission SET reason='unknown-provenance' WHERE sid=?", (sid,))
                                continue
                            db.executemany('INSERT OR IGNORE INTO dependencies VALUES(?,?)', ((d, sid) for d in dependencies))
                        elif field == 'documentId' and isinstance(item, str) and item.startswith('repo:'):
                            db.execute('INSERT OR IGNORE INTO dependencies VALUES(?,?)', (item, sid))
                        elif field in {'sourcePath', 'sourceReference'} and isinstance(item, str):
                            db.execute('INSERT OR IGNORE INTO dependencies VALUES(?,?)', ('repo:' + item, sid))
        if set(json.loads(summary)['addresses']) != present:
            raise PortableSnapshotError('Incomplete production source membership')
        if not portable_identity:
            db.execute("UPDATE admission SET reason='portable-reindex-required' WHERE sid=? AND reason=''", (sid,))
    # Shared payloads taint every co-owner, including transitive co-ownership.
    db.execute('''INSERT OR IGNORE INTO dependencies SELECT a.sid,b.sid FROM owners a
        JOIN owners b USING(address) WHERE a.sid<>b.sid''')
    db.execute('''INSERT OR IGNORE INTO dependencies SELECT f.sid,r.sid FROM refs r
        JOIN facts f ON f.id=r.id WHERE f.sid<>r.sid''')
    db.execute("""UPDATE admission SET reason='unknown-reference' WHERE reason='' AND sid IN
        (SELECT sid FROM refs WHERE id NOT IN (SELECT id FROM facts))""")
    db.execute("""UPDATE admission SET reason='unknown-provenance' WHERE reason='' AND sid IN
        (SELECT dependent FROM dependencies WHERE cause NOT IN (SELECT sid FROM admission))""")
    db.execute("""WITH RECURSIVE denied(sid) AS (
        SELECT sid FROM admission WHERE reason<>'' UNION
        SELECT d.dependent FROM dependencies d JOIN denied ON d.cause=denied.sid)
        UPDATE admission SET reason='protected-dependency' WHERE reason='' AND sid IN denied""")
    missing = set(inventory) - {r[0].removeprefix('repo:') for r in db.execute('SELECT sid FROM admission')}
    # Unsupported media is excluded explicitly rather than blocking safe text.
    return dict(db.execute("SELECT reason,count(*) FROM admission WHERE reason<>'' GROUP BY reason")), len(missing)
