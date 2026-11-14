"""Seed only exact-compatible complete sources inside the caller's indexer lock."""
from contextlib import nullcontext
import json
from pathlib import Path
from .portable_format import ROOT, confined
from .portable_snapshot_reader import verified_snapshot, payloads_for


def import_sources(target, cache_root, cache, sources, driver, *, plan=None):
    root = Path(target) / 'project-knowledge'
    if not (root / ROOT).exists():
        return {'importedSources': 0, 'incompatibleSources': 0}
    imported = misses = reused = 0
    from pi_platform.core.canonical import content_address, to_canonical_json
    by_id = {source.id: source for source in sources}
    with (nullcontext(plan) if plan is not None else verified_snapshot(root, cache_root)) as (db, report):
        def complete_sources():
            nonlocal misses, reused
            for sid, raw in db.execute("SELECT id,body FROM records WHERE kind='source' ORDER BY id"):
                body = json.loads(raw)['body']
                source = by_id.get(sid)
                metadata_key = content_address(to_canonical_json(source.metadata).decode()) if source else None
                if (source is None or source.contentHash != body['sourceHash']
                        or driver.pipeline_key(source) != body['pipelineKey'] or metadata_key != body['metadataKey']
                        or (source.metadata.policy or '') != (body['policy'] or '')):
                    misses += 1
                    continue
                if cache.source_record(sid) is not None:
                    reused += 1
                    continue
                # Check actual bytes, not just an externally supplied inventory hash.
                path = confined(Path(target), body['path'])
                from pi_platform.adapters.runtime.sqlite_ingestion_cache import _file_checksum
                if _file_checksum(path) != body['sourceHash']:
                    raise RuntimeError('Source bytes moved during portable import')
                summary = body['summary'].encode()
                addresses = json.loads(summary)['addresses']
                records = dict(payloads_for(db, addresses))
                records[body['pipelineKey']] = summary
                yield sid, body['sourceHash'], body['pipelineKey'], addresses, body['metadataKey'], records
        imported = cache.import_portable_sources(complete_sources())
    return {'snapshotId': report['snapshotId'], 'importedSources': imported, 'incompatibleSources': misses, 'reusedLocalSources': reused}


def import_vectors(target, cache_root, runtime, active, *, plan=None):
    root = Path(target) / 'project-knowledge'
    if not (root / ROOT).exists():
        return 0
    from .portable_vectors import decode_record
    by_id = {chunk.chunk_id: chunk for chunk in active}
    profile = runtime.embedding_model.profile()
    count, batch = 0, []
    def persist(batch):
        if not batch:
            return 0
        existing = runtime.vector_record_store.get_many([r.chunk_id for r in batch], runtime.embedding_profile_hash)
        changed = [r for r in batch if existing.get(r.chunk_id) is None or any(
            getattr(existing[r.chunk_id], key) != getattr(r, key)
            for key in ('content_hash', 'model_revision', 'dimension', 'normalization',
                        'created_from_retrieval_text_hash', 'vector_payload'))]
        if changed:
            runtime.vector_record_store.put_many(changed)
        return len(changed)
    with (nullcontext(plan) if plan is not None else verified_snapshot(root, cache_root)) as (db, _):
        for (raw,) in db.execute("SELECT body FROM records WHERE kind='vector' ORDER BY id"):
            record = decode_record(json.loads(raw)['body'])
            chunk = by_id.get(record.chunk_id)
            if (chunk is None or record.embedding_profile_hash != runtime.embedding_profile_hash
                    or record.model_revision != profile.model_revision
                    or record.normalization != profile.normalization or record.dimension != profile.output_dimension
                    or record.created_from_retrieval_text_hash != chunk.retrieval_text_hash
                    or record.content_hash != chunk.content_hash):
                continue
            batch.append(record)
            if len(batch) >= 256:
                count += persist(batch)
                batch = []
        count += persist(batch)
    return count
