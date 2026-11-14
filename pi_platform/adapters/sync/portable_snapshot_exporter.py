"""Project a published production generation, stage privately, publish root last."""
from contextlib import closing
import json
import os
from pathlib import Path
import sqlite3
import uuid

from .portable_format import ROOT, PortableSnapshotError, add_record, confined, decode, read_bounded, sha, spool, write_snapshot
from .portable_snapshot_reader import eligible_path, validate_payload, verified_snapshot


def _version(target, *, include_portable=True):
    from pi_platform.core.sync.version_monitor import read_project_version
    from dataclasses import asdict
    return asdict(read_project_version(target, include_portable=include_portable))


def _active(db):
    row = db.execute("SELECT value FROM schema_meta WHERE key='active_job'").fetchone()
    if not row or db.execute('SELECT state FROM index_jobs WHERE job_id=?', row).fetchone() != ('published',):
        raise PortableSnapshotError('No published resumable generation to export')
    return row[0]


def _sources(db, generation):
    return db.execute('''SELECT o.source_id,o.source_hash,o.pipeline_key,o.metadata_key,o.summary_json,o.checksum
        FROM source_outputs o JOIN generation_sources g
        USING(source_id,source_hash,pipeline_key,metadata_key)
        WHERE g.generation=? ORDER BY o.source_id''', (generation,))


def stage_export(target, cache_root, *, include_vectors=False, cap=None):
    """No Git-owned writes; caller serializes against index publication."""
    from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer
    target, cache_root = Path(target).resolve(), Path(cache_root).resolve()
    if cap is None:
        cap = int(os.environ.get('PI_PORTABLE_SHARD_MIB', '8')) * 1024 * 1024
    if not 1024 * 1024 <= cap <= 16 * 1024 * 1024:
        raise PortableSnapshotError('Portable shard cap must be 1 through 16 MiB')
    maximum_total = int(os.environ.get('PI_PORTABLE_MAX_TOTAL_MIB', '2048')) * 1024 * 1024
    maximum_files = int(os.environ.get('PI_PORTABLE_MAX_FILES', '100000'))
    if not 1 <= maximum_files <= 100000 or not 1 <= maximum_total <= 2048 * 1024 * 1024:
        raise PortableSnapshotError('Portable storage budget outside supported bounds')
    version = _version(target)
    input_version = _version(target, include_portable=False)
    staging = cache_root / 'portable-staging' / uuid.uuid4().hex
    staging.mkdir(parents=True, mode=0o700)
    knowledge = staging / 'knowledge'
    knowledge.mkdir(mode=0o700)
    from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
    inventory = {e.path: e for e in RepositorySourceDiscovery().discover(target).entries}
    excluded, source_count = [], 0
    with exclusive_indexer(cache_root), closing(sqlite3.connect(
            f'{(cache_root / "indexing-state.sqlite").as_uri()}?mode=ro', uri=True)) as production:
        production.execute('BEGIN')
        generation = _active(production)
        with spool(cache_root / 'portable-work') as db:
            # Track admission in disk-backed tables; a denied co-owner denies the
            # complete source output, never just an individual chunk/edge.
            db.execute('CREATE TEMP TABLE admitted(sid TEXT PRIMARY KEY,allowed INTEGER)')
            for sid, digest, key, metadata, summary, checksum in _sources(production, generation):
                path = sid.removeprefix('repo:')
                entry = inventory.get(path)
                if not sid.startswith('repo:') or entry is None or entry.content_hash != digest:
                    raise PortableSnapshotError('Published generation does not match current source inventory')
                allowed = eligible_path(path, entry.policy)
                db.execute('INSERT INTO admitted VALUES(?,?)', (sid, int(allowed)))
                if not allowed:
                    excluded.append(sid)
            if set(inventory) - {row[0].removeprefix('repo:') for row in db.execute('SELECT sid FROM admitted')}:
                raise PortableSnapshotError('Published generation lacks complete source coverage (media may be unsupported)')
            denied_addresses = '''SELECT m.address FROM source_payload_membership m
                JOIN generation_sources g USING(source_id,source_hash,pipeline_key,metadata_key)
                WHERE g.generation=? AND g.source_id=?'''
            db.execute('CREATE TEMP TABLE denied(address TEXT PRIMARY KEY)')
            for (sid,) in db.execute('SELECT sid FROM admitted WHERE allowed=0'):
                db.executemany('INSERT OR IGNORE INTO denied VALUES(?)', production.execute(denied_addresses, (generation, sid)))
            for sid, digest, key, metadata, summary, checksum in _sources(production, generation):
                allowed = db.execute('SELECT allowed FROM admitted WHERE sid=?', (sid,)).fetchone()[0]
                if not allowed:
                    continue
                if sha(summary) != checksum:
                    raise PortableSnapshotError('Production source summary checksum mismatch')
                body = json.loads(summary)
                addresses = body['addresses']
                if any(db.execute('SELECT 1 FROM denied WHERE address=?', (a,)).fetchone() for a in addresses):
                    excluded.append(sid)
                    continue
                path = sid.removeprefix('repo:')
                if not any('portable_identity' in json.loads(row[0]).get('metadata', {}).get('extensions', {})
                           or 'portable_identity' in json.loads(row[0]).get('chunk', {}).get('metadata', {}).get('extensions', {})
                           for row in production.execute('''SELECT p.payload FROM canonical_payloads p
                               JOIN source_payload_membership m USING(address)
                               WHERE m.source_id=? AND m.source_hash=? AND m.pipeline_key=? AND m.metadata_key=?''',
                               (sid, digest, key, metadata))):
                    raise PortableSnapshotError('Source lacks portable identity; enable PI_PORTABLE_EXPORT=review and reindex once')
                add_record(db, 'source', sid, {'path': path, 'policy': inventory[path].policy or '',
                           'sourceHash': digest, 'pipelineKey': key, 'metadataKey': metadata,
                           'summary': bytes(summary).decode('utf-8')})
                for address in addresses:
                    if db.execute("SELECT 1 FROM records WHERE kind='payload' AND id=?", (address,)).fetchone():
                        continue
                    row = production.execute('''SELECT p.payload,p.checksum FROM canonical_payloads p
                        JOIN source_payload_membership m USING(address)
                        WHERE m.source_id=? AND m.source_hash=? AND m.pipeline_key=? AND m.metadata_key=? AND address=?''',
                        (sid, digest, key, metadata, address)).fetchone()
                    if row is None or sha(row[0]) != row[1] or sha(row[0]) != address:
                        raise PortableSnapshotError('Incomplete/corrupt production source payload')
                    validate_payload(row[0], local_root=target)
                    add_record(db, 'payload', address, {'raw': bytes(row[0]).decode('utf-8')})
                source_count += 1
            if include_vectors:
                _export_vectors(db, cache_root)
            descriptor = write_snapshot(db, knowledge, cap=cap, max_total=maximum_total, max_files=maximum_files)
        with verified_snapshot(knowledge, cache_root) as (_, verified):
            pass
        if (version != _version(target) or input_version != _version(target, include_portable=False)
                or generation != _active(production)):
            raise PortableSnapshotError('Source version moved during portable export')
    proposal = {'stagingId': staging.name, 'snapshotId': descriptor['snapshotId'],
                'generation': generation, 'version': version,
                'inputVersion': input_version, 'sources': source_count,
                'excludedSources': excluded, 'vectors': include_vectors,
                'totalBytes': verified['totalBytes'], 'fileCount': verified['fileCount']}
    from pi_platform.core.canonical.durable_write import atomic_write_bytes
    from .portable_format import encode
    atomic_write_bytes(staging / 'proposal.json', encode(proposal))
    return {**proposal, 'changedPaths': changed_paths(knowledge, target / 'project-knowledge', verified['paths'])}


def _export_vectors(db, cache_root):
    from pi_platform.adapters.runtime.sqlite_vector_record_store import SqliteVectorRecordStore
    from .portable_vectors import encode_record
    path = cache_root / 'indexes' / 'embeddings.sqlite'
    if not path.exists():
        raise PortableSnapshotError('No production vector store')
    store = SqliteVectorRecordStore(db_path=str(path))
    # Choose the same effective contextual projection as production, independent
    # of payload address order. Never export a stale vector merely because its
    # raw content hash matches (context can change without changing raw text).
    db.execute('CREATE TEMP TABLE vector_chunks(id TEXT PRIMARY KEY,content_hash TEXT,text_hash TEXT,preferred INTEGER)')
    for (raw,) in db.execute("SELECT body FROM records WHERE kind='payload'"):
        body = json.loads(json.loads(raw)['body']['raw'])
        body = body.get('chunk', body)
        if not body.get('rawText') or not body.get('id'):
            continue
        contextual = body.get('metadata', {}).get('extensions', {}).get('retrieval_text')
        text = contextual or body.get('contextualText') or body['rawText']
        db.execute('''INSERT INTO vector_chunks VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            content_hash=excluded.content_hash,text_hash=excluded.text_hash,preferred=excluded.preferred
            WHERE excluded.preferred>vector_chunks.preferred''',
            (body['id'], body['contentHash'], sha(text.encode()), int(bool(contextual))))
    with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as vectors:
        for cid, content_hash, text_hash in db.execute('SELECT id,content_hash,text_hash FROM vector_chunks ORDER BY id'):
            profiles = vectors.execute('SELECT embedding_profile_hash FROM embeddings WHERE chunk_id=? ORDER BY embedding_profile_hash', (cid,)).fetchall()
            matches = 0
            for (profile,) in profiles:
                record = store.get(cid, profile)
                if record.content_hash != content_hash or record.created_from_retrieval_text_hash != text_hash:
                    continue
                add_record(db, 'vector', profile + ':' + cid, encode_record(record))
                matches += 1
            if not matches:
                raise PortableSnapshotError('No exact retrieval-text vector for an eligible chunk; use standard mode')


def changed_paths(staged, current, paths):
    changed = []
    for relative in paths:
        path = confined(staged, relative)
        existing = confined(current, relative)
        if not existing.exists() or read_bounded(existing) != read_bounded(path):
            changed.append(relative)
    return changed


def _immutable_bytes(root, relative, cap):
    from .portable_format import ATTRIBUTES
    raw = read_bounded(confined(root, relative), cap)
    expected = ATTRIBUTES.get(relative)
    if (expected is not None and raw != expected) or (expected is None and sha(raw) != Path(relative).stem):
        raise PortableSnapshotError('Portable immutable file changed during publication')
    return raw


def _verify_installed_files(root, report):
    # Semantic contracts were already verified in the private spool. Exact byte
    # hashes prove installed files have the same contracts without reparsing and
    # rebuilding a second/third SQLite verification spool for a large corpus.
    for relative in report['paths']:
        if relative != ROOT:
            _immutable_bytes(root, relative, report['fileCap'])


def publish_export(target, cache_root, staging_id, *, authorize):
    """Authorize exact verified content, recheck version, install root LAST.

    Immutable files are harmless if interrupted. The previous root's referenced
    files remain untouched. Unreferenced cleanup is deliberately separate.
    """
    from pi_platform.adapters.runtime.sqlite_ingestion_cache import exclusive_indexer
    from pi_platform.core.canonical.durable_write import atomic_write_bytes
    target, cache_root = Path(target).resolve(), Path(cache_root).resolve()
    if not isinstance(staging_id, str) or not __import__('re').fullmatch('[a-f0-9]{32}', staging_id):
        raise PortableSnapshotError('Invalid portable staging ID')
    staging = cache_root / 'portable-staging' / staging_id
    proposal = decode(read_bounded(confined(staging, 'proposal.json')))
    knowledge, current = staging / 'knowledge', target / 'project-knowledge'
    with exclusive_indexer(cache_root), closing(sqlite3.connect(
            f'{(cache_root / "indexing-state.sqlite").as_uri()}?mode=ro', uri=True)) as production:
        with verified_snapshot(knowledge, cache_root) as (records, report):
            from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
            inventory = {e.path: e for e in RepositorySourceDiscovery().discover(target).entries}
            for (raw,) in records.execute("SELECT body FROM records WHERE kind='source'"):
                body = json.loads(raw)['body']
                entry = inventory.get(body['path'])
                if entry is None or entry.content_hash != body['sourceHash'] or (entry.policy or '') != (body['policy'] or ''):
                    raise PortableSnapshotError('Stale portable source checkout; restage current generation')
            root_raw = read_bounded(confined(knowledge, ROOT))
            if proposal['snapshotId'] != report['snapshotId']:
                raise PortableSnapshotError('Portable proposal identity mismatch')
        authorize(report['snapshotId'])
        publication_version = _version(target)
        if proposal['version'] != publication_version or proposal['generation'] != _active(production):
            # Identical current root is an idempotent retry after successful publish.
            if not (proposal['generation'] == _active(production)
                    and proposal.get('inputVersion') == _version(target, include_portable=False)
                    and (current / ROOT).exists()
                    and read_bounded(confined(current, ROOT)) == read_bounded(confined(knowledge, ROOT))):
                raise PortableSnapshotError('Stale portable proposal; reindex/stage current source version')
        paths = changed_paths(knowledge, current, report['paths'])
        # Preflight every path before writes; protect operator Git attributes.
        # Hash-addressed corrupt files may be restored from the verified stage.
        for relative in paths:
            existing = confined(current, relative)
            if relative.endswith('.gitattributes') and existing.exists():
                raise PortableSnapshotError('Existing portable Git attributes conflict')
        for relative in paths:
            if relative == ROOT:
                continue
            path = confined(current, relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(path, _immutable_bytes(knowledge, relative, report["fileCap"]))
        # Verify the installed immutable tree against the proposed root BEFORE
        # replacing the pointer. This also catches staging edits during copying.
        _verify_installed_files(current, report)
        authorize(report['snapshotId'])
        if publication_version != _version(target):
            raise PortableSnapshotError('Checkout moved during portable publication')
        if ROOT in paths:
            path = confined(current, ROOT)
            previous = read_bounded(path) if path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                atomic_write_bytes(path, root_raw)
                if read_bounded(path) != root_raw:
                    raise PortableSnapshotError("Portable root changed after replacement")
            except BaseException:
                # Never overwrite a concurrent external checkout while rolling
                # back our own pointer. All previous immutable files are retained.
                if path.exists() and read_bounded(path) == root_raw:
                    if previous is not None:
                        atomic_write_bytes(path, previous)
                    else:
                        path.unlink()
                raise
    return {**proposal, 'changedPaths': paths, 'published': True}
