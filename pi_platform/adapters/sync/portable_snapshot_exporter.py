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
    from pi_platform.adapters.fs.private_cache import ensure_private_cache
    ensure_private_cache(target, cache_root)
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
    from .safe_export_projector import source_reviews
    from .portable_format import encode
    policy_hash = sha(encode(source_reviews(cache_root)))
    staging = cache_root / 'portable-staging' / uuid.uuid4().hex
    staging.mkdir(parents=True, mode=0o700)
    knowledge = staging / 'knowledge'
    knowledge.mkdir(mode=0o700)
    from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
    inventory = {e.path: e for e in RepositorySourceDiscovery().discover(target).entries}
    source_count = 0
    with exclusive_indexer(cache_root), closing(sqlite3.connect(
            f'{(cache_root / "indexing-state.sqlite").as_uri()}?mode=ro', uri=True)) as production:
        production.execute('BEGIN')
        generation = _active(production)
        with spool(cache_root / 'portable-work') as db:
            from .safe_export_projector import project_sources
            reasons, unsupported = project_sources(db, production, generation, inventory, target, cache_root)
            if unsupported:
                reasons['unsupported-source'] = unsupported
            excluded_count = sum(reasons.values())
            for sid, digest, key, metadata, summary, checksum in _sources(production, generation):
                allowed = not db.execute('SELECT reason FROM admission WHERE sid=?', (sid,)).fetchone()[0]
                if not allowed:
                    continue
                if sha(summary) != checksum:
                    raise PortableSnapshotError('Production source summary checksum mismatch')
                body = json.loads(summary)
                addresses = body['addresses']
                path = sid.removeprefix('repo:')
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
            if not source_count:
                import shutil
                shutil.rmtree(staging)
                return {'state': 'no-exportable-sources', 'sources': 0,
                        'excludedSourceCount': excluded_count, 'excludedReasonCounts': reasons,
                        'completeForLocalIndex': False,
                        'cleanupRequired': (target / 'project-knowledge' / ROOT).exists(),
                        'message': 'No shareable sources; review any retained generated files and Git history'}
            if include_vectors:
                _export_vectors(db, cache_root)
            descriptor = write_snapshot(db, knowledge, cap=cap, max_total=maximum_total, max_files=maximum_files,
                scope={'kind': 'eligible-sources-only', 'policyVersion': 'safe-source-export/1',
                       'exportedSourceCount': source_count, 'completeForExportableScope': True})
        with verified_snapshot(knowledge, cache_root) as (_, verified):
            pass
        if (version != _version(target) or input_version != _version(target, include_portable=False)
                or generation != _active(production) or policy_hash != sha(encode(source_reviews(cache_root)))):
            raise PortableSnapshotError('Source version moved during portable export')
    proposal = {'stagingId': staging.name, 'snapshotId': descriptor['snapshotId'],
                'securityPolicyHash': policy_hash,
                'generation': generation, 'version': version,
                'inputVersion': input_version, 'sources': source_count,
                'excludedSources': [], 'excludedSourceCount': excluded_count,
                'excludedReasonCounts': reasons, 'completeForLocalIndex': excluded_count == 0,
                'completeForExportableScope': True, 'vectors': include_vectors,
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
    # Choose the same effective contextual projection as production, independent
    # of payload address order. Never export a stale vector merely because its
    # raw content hash matches (context can change without changing raw text).
    db.execute('CREATE TEMP TABLE vector_chunks(id TEXT PRIMARY KEY,content_hash TEXT,text_hash TEXT,preferred INTEGER)')
    db.execute('CREATE TEMP TABLE pdf_vector_chunks(id TEXT PRIMARY KEY,image_hash TEXT)')
    for (raw,) in db.execute("SELECT body FROM records WHERE kind='payload'"):
        body = json.loads(json.loads(raw)['body']['raw'])
        body = body.get('chunk', body)
        if body.get('kind') == 'media_source':
            db.execute('INSERT INTO vector_chunks VALUES(?,?,?,?)',
                (body['id'], body['contentHash'], body['retrievalTextHash'], 0))
            continue
        if not body.get('rawText') or not body.get('id'):
            continue
        contextual = body.get('metadata', {}).get('extensions', {}).get('retrieval_text')
        text = contextual or body.get('contextualText') or body['rawText']
        if str(body.get('metadata', {}).get('sourcePath', '')).lower().endswith('.pdf'):
            descriptor = body.get('metadata', {}).get('extensions', {}).get('pdf_asset')
            db.execute('INSERT OR REPLACE INTO pdf_vector_chunks VALUES(?,?)',
                       (body['id'], descriptor['byteHash'] if descriptor else None))
        db.execute('''INSERT INTO vector_chunks VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            content_hash=excluded.content_hash,text_hash=excluded.text_hash,preferred=excluded.preferred
            WHERE excluded.preferred>vector_chunks.preferred''',
            (body['id'], body['contentHash'], sha(text.encode()), int(bool(contextual))))
    with closing(sqlite3.connect(f'{path.as_uri()}?mode=ro', uri=True)) as vectors:
        vectors.execute('BEGIN')
        projection_table = vectors.execute("SELECT 1 FROM sqlite_master WHERE name='portable_pdf_projections'").fetchone()
        for cid, content_hash, text_hash in db.execute('SELECT id,content_hash,text_hash FROM vector_chunks ORDER BY id'):
            rows = vectors.execute('''SELECT chunk_id,embedding_profile_hash,content_hash,
                model_revision,dimension,normalization,vector_payload,
                created_from_retrieval_text_hash,created_at FROM embeddings
                WHERE chunk_id=? ORDER BY embedding_profile_hash''', (cid,))
            matches = 0
            for row in rows:
                record = SqliteVectorRecordStore._record_from_row(row)
                profile = record.embedding_profile_hash
                if record.content_hash != content_hash:
                    continue
                body = encode_record(record)
                if record.created_from_retrieval_text_hash != text_hash:
                    pdf = db.execute('SELECT image_hash FROM pdf_vector_chunks WHERE id=?', (cid,)).fetchone()
                    projection = vectors.execute('SELECT body FROM portable_pdf_projections WHERE chunk_id=? AND profile=? AND projection_hash=?',
                        (cid, profile, record.created_from_retrieval_text_hash)).fetchone() if projection_table and pdf else None
                    if projection is None:
                        continue
                    value = json.loads(projection[0])
                    from .portable_pdf_vectors import validate_projection
                    validate_projection(value, canonical_hash=text_hash, image_hash=pdf[0], expected=record.created_from_retrieval_text_hash)
                    body['projection'] = value
                validate_payload(json.dumps(body).encode())
                add_record(db, 'vector', profile + ':' + cid, body)
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


def _audit_retained_files(current, proposed_paths, inventory, cache_root, proposed_records):
    """A safe new root does not sanitize old unreferenced worktree objects."""
    from pi_platform.core.sync.export_policy import sensitive_text, sensitive_file
    from .safe_export_projector import source_reviews
    reviews = source_reviews(cache_root)
    restricted = {}
    def is_restricted(name):
        if name not in restricted:
            entry = inventory.get(name)
            restricted[name] = (reviews.get(name, {}).get('classification') == 'confidential' or
                bool(entry and (not eligible_path(name, entry.policy) or sensitive_file(confined(current.parent, name)))))
        return restricted[name]
    total = count = 0
    for family in ('objects', 'chunks', 'graph', 'sources', 'vectors', 'manifests'):
        directory = current / family
        if directory.is_symlink():
            raise PortableSnapshotError('Linked generated tree requires operator remediation')
        if not directory.exists():
            continue
        for path in directory.rglob('*'):
            if path.is_symlink():
                raise PortableSnapshotError('Linked generated tree requires operator remediation')
            if not path.is_file():
                continue
            relative = path.relative_to(current).as_posix()
            if relative in proposed_paths or path.name == '.gitattributes':
                continue
            count += 1
            raw = read_bounded(confined(current, relative))
            total += len(raw)
            if count > 100000 or total > 2048 * 1024 * 1024:
                raise PortableSnapshotError('Retained generated tree exceeds audit budget')
            if path.suffix not in {'.json', '.jsonl', '.yaml', '.yml'} or sensitive_text(raw.decode('utf-8', errors='replace')):
                raise PortableSnapshotError('Retained generated files require reviewed cleanup; inspect Git history and rotate exposed credentials')
            if path.suffix not in {'.json', '.jsonl'}:
                continue
            try:
                for line in (raw.splitlines() if path.suffix == '.jsonl' else [raw]):
                    value = json.loads(line)
                    envelope = value.get('body', value)
                    if value.get('kind') == 'source':
                        name = envelope.get('path')
                        if is_restricted(name):
                            raise PortableSnapshotError('Retained generated files contain newly restricted sources; reviewed cleanup and Git-history remediation required')
                    elif value.get('kind') == 'payload':
                        payload = validate_payload(envelope['raw'].encode())
                        payload = payload.get('chunk', payload)
                        name = payload.get('metadata', {}).get('sourcePath')
                        if name and is_restricted(name):
                            raise PortableSnapshotError('Retained derived records require reviewed cleanup')
                    elif value.get('kind') == 'vector':
                        from .portable_vectors import decode_record
                        vector = decode_record(envelope)
                        row = proposed_records.execute('SELECT content_hash,text_hash FROM chunks WHERE id=?', (vector.chunk_id,)).fetchone()
                        if row is None or row[0] != vector.content_hash:
                            raise PortableSnapshotError('Retained vector ownership is no longer verified; reviewed cleanup required')
                        if row[1] != vector.created_from_retrieval_text_hash:
                            pdf = proposed_records.execute('SELECT image_hash FROM pdf_chunks WHERE id=?', (vector.chunk_id,)).fetchone()
                            if pdf is None:
                                raise PortableSnapshotError('Retained vector projection requires reviewed cleanup')
                            from .portable_pdf_vectors import validate_projection
                            validate_projection(envelope.get('projection'), canonical_hash=row[1], image_hash=pdf[0],
                                                expected=vector.created_from_retrieval_text_hash)
                    elif value.get('kind') != 'vector' and 'children' not in value:
                        validate_payload(line)
            except (ValueError, KeyError, TypeError) as exc:
                raise PortableSnapshotError('Retained generated files require reviewed cleanup; previous Git history is unchanged') from exc


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
            from .safe_export_projector import source_reviews
            from .portable_format import encode
            if proposal.get('securityPolicyHash') != sha(encode(source_reviews(cache_root))):
                raise PortableSnapshotError('Source security policy moved; restage current generation')
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
            _audit_retained_files(current, set(report['paths']), inventory, cache_root, records)
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
        if (publication_version != _version(target) or
                proposal.get('securityPolicyHash') != sha(encode(source_reviews(cache_root)))):
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
