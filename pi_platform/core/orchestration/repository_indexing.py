"""Build a candidate retrieval runtime from real repository sources.

Canonical files are read-only. Parsed chunks are reused across model switches;
vectors are persisted by embedding profile. Only callers publish the returned
candidate after checking the source version and committing its snapshot.
"""
from pi_platform.core.ingest.failures import CandidateIndexingError
from dataclasses import replace
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

from pi_platform.adapters.ingest.local_pipeline_driver import (
    LocalPipelineDriver, _default_parser_registry, _default_chunker_registry,
)
from pi_platform.core.canonical.value_types import Metadata, Source, KnowledgeState
from pi_platform.core.ingest.runtime_cache import InMemoryRuntimeCache
from pi_platform.core.retrieval.semantic_index_service import ActiveChunk
from pi_platform.core.sync.restore_contract import RestoreRequiresReindex
from pi_platform.ports.ingest.source_adapter import SourceContentFamily
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from .retrieval_composition import build_production_retrieval_runtime


def _family(path):
    from pi_platform.adapters.python.intelligence import python_family
    p = Path(path)
    if family := python_family(p):
        return family
    if p.suffix.lower() in {'.docx', '.pptx', '.xlsx', '.doc', '.ppt', '.xls'}:
        return SourceContentFamily.OFFICE
    if p.suffix.lower() == '.pdf':
        return SourceContentFamily.PDF
    if p.suffix.lower() in {'.md', '.markdown'}:
        return SourceContentFamily.MARKDOWN
    if p.suffix.lower() in {'.html', '.htm'}:
        return SourceContentFamily.HTML
    if p.suffix.lower() == '.java':
        return SourceContentFamily.JAVA_SOURCE
    if p.name == 'pom.xml':
        return SourceContentFamily.MAVEN_POM
    if p.name in {'build.gradle', 'build.gradle.kts'}:
        return SourceContentFamily.GRADLE_BUILD
    if p.name in {'uv.lock', 'poetry.lock'}:
        return SourceContentFamily.PYTHON_LOCK
    if p.name == 'package.json':
        return SourceContentFamily.NODE_MANIFEST
    if p.name in {'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock'}:
        return SourceContentFamily.NODE_LOCK
    return SourceContentFamily.PLAIN_TEXT


def _load_cache(path):
    cache = InMemoryRuntimeCache()
    if path.is_file():
        saved = json.loads(path.read_text(encoding='utf-8'))
        cache.restore(saved)
    return cache


def _candidate_graph(target, cache_root, cache, *, progress=None):
    """Snapshot graph bodies into a disposable generation, never canonical Git."""
    from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
    from pi_platform.adapters.runtime.graph_expansion import ProductionGraphExpansion
    from pi_platform.core.canonical.value_types import Entity, Relation, from_canonical_json
    def canonical_records():
        for raw in cache.iter_records():
            yield json.loads(raw)
        canonical = target / 'project-knowledge' / 'graph'
        if not canonical.is_dir() or (target / 'project-knowledge/manifests/portable-v2.json').exists():
            return
        for path in sorted(canonical.rglob('*')):
            if not path.is_file() or path.is_symlink() or path.suffix not in {'.json', '.jsonl'}:
                continue
            if 'objects' in path.relative_to(canonical).parts:
                continue
            if path.suffix == '.jsonl':
                with path.open(encoding='utf-8') as handle:
                    for line in handle:
                        if line.strip():
                            yield json.loads(line)
            else:
                body = json.loads(path.read_text(encoding='utf-8'))
                yield from body if isinstance(body, list) else [body]
    # Legacy runtime.db retains historical versions. Only the active canonical
    # tree and current ingestion ownership above define this served graph.
    entities, relations = {}, {}
    for record in canonical_records():
        if not isinstance(record, dict):
            continue
        if {'id', 'family', 'label'}.issubset(record):
            entities[record['id']] = from_canonical_json(Entity, json.dumps(record))
        elif {'sourceId', 'targetId', 'family'}.issubset(record):
            relations[(record['sourceId'], record['targetId'], record['family'])] = from_canonical_json(Relation, json.dumps(record))
    bodies = [json.dumps(__import__('dataclasses').asdict(v), sort_keys=True) for v in (*entities.values(), *relations.values())]
    generation = hashlib.sha256('\n'.join(sorted(bodies)).encode()).hexdigest()
    graph = LocalShardedGraph(cache_root / 'indexes' / 'graph' / generation)
    from pi_platform.adapters.runtime.candidate_artifacts import build_graph_shards
    build_graph_shards(graph, tuple(entities.values()), tuple(relations.values()), progress=progress)
    return ProductionGraphExpansion(graph), tuple(sorted(entities))


def _index_dense_generation(runtime, active, *, restore_only=False):
    """Reuse valid ANN files, otherwise rebuild only from valid SQLite vectors."""
    from pi_platform.adapters.runtime.usearch_dense_index import USearchDenseIndex, compute_source_generation
    from pi_platform.core.retrieval.semantic_index_service import IndexingReport

    dense = runtime.dense_index
    semantic = runtime.semantic_index_service
    if isinstance(dense, USearchDenseIndex) and dense._real_usearch:
        profile_hash = runtime.embedding_profile_hash
        generation = compute_source_generation(
            [chunk.chunk_id for chunk in active],
            retrieval_text_hashes=[chunk.retrieval_text_hash for chunk in active],
            embedding_profile_hash=profile_hash,
        )
        dense.select_generation(generation)
        if (Path(dense.index_path).is_file() and Path(dense.key_sidecar_path).is_file()
                and dense.is_compatible_with(embedding_profile_hash=profile_hash, source_generation=generation)):
            vectors = {}
            for start in range(0, len(active), 256):
                batch = active[start:start + 256]
                records = runtime.vector_record_store.get_many([chunk.chunk_id for chunk in batch], profile_hash)
                for chunk in batch:
                    vector = semantic.compatible_cached_vector(chunk, records.get(chunk.chunk_id))
                    if vector is not None:
                        vectors[chunk.chunk_id] = vector
                if len(vectors) != start + len(batch):
                    break
            if len(vectors) == len(active) and dense.load_generation(
                generation, vectors=vectors,
                metadata={chunk.chunk_id: chunk.metadata for chunk in active},
            ):
                count = len(active)
                return IndexingReport(
                    reused_count=count, embedded_count=0, skipped_count=0,
                    source_generation=generation, expected_vector_count=count,
                    persisted_chunk_ids=tuple(chunk.chunk_id for chunk in active),
                ), True
        dense.reset_candidate(output_dimension=runtime.embedding_model.profile().output_dimension)
    report = semantic.embed_active_chunks(active, allow_embedding=not restore_only)
    if isinstance(dense, USearchDenseIndex):
        dense.save_generation(report.source_generation)
    return report, False


def index_repository(*, target, cache_root, inventory, previous_inventory, settings, cli_overrides=None, restore_only=False):
    """Return an unpublished candidate; explicit resumable mode never falls back."""
    import os
    from pi_platform.adapters.runtime.sqlite_ingestion_cache import SqliteIngestionCache, exclusive_indexer
    if os.environ.get('PI_REQUIRE_OFFLINE_ASSETS') == '1':
        from pi_platform.deployment.offline_assets import configure
        configure()
    if os.environ.get('PI_PORTABLE_EXPORT', 'off') not in {'off', 'review', 'approved-auto'}:
        raise ValueError('PI_PORTABLE_EXPORT must be off, review or approved-auto')
    engine = os.environ.get('PI_INDEX_ENGINE', 'resumable').strip().lower()
    if engine not in {'legacy', 'resumable'}:
        raise ValueError('PI_INDEX_ENGINE must be legacy or resumable')
    arguments = dict(target=target, cache_root=cache_root, inventory=inventory,
                     previous_inventory=previous_inventory, settings=settings, cli_overrides=cli_overrides, restore_only=restore_only)
    if restore_only and not (Path(target) / 'project-knowledge/manifests/portable-v2.json').is_file():
        raise RestoreRequiresReindex('No portable snapshot is available')
    from pi_platform.adapters.fs.private_cache import ensure_private_cache
    ensure_private_cache(target, cache_root)
    with exclusive_indexer(cache_root):
        if (Path(cache_root) / 'gc-in-progress.json').exists():
            raise RuntimeError('Interrupted canonical GC; resume scripts/indexing_state.py gc --apply --resume before indexing')
        if (Path(cache_root) / 'restore-in-progress.json').exists():
            raise RuntimeError('Interrupted state restore; complete scripts/indexing_state.py restore --resume before indexing')
        if restore_only and engine == 'legacy':
            raise RestoreRequiresReindex('Restore requires the resumable engine')
        if engine == 'legacy':
            from pi_platform.adapters.sync.portable_format import ROOT
            from pi_platform.adapters.sync.portable_snapshot_reader import verified_snapshot
            root = Path(target) / 'project-knowledge'
            if (root / ROOT).exists():
                with verified_snapshot(root, cache_root):
                    return _index_repository(**arguments)
            return _index_repository(**arguments)
        fingerprint = hashlib.sha256(json.dumps(
            [(e.path, e.content_hash, e.policy) for e in inventory.entries], sort_keys=True).encode()).hexdigest()
        import shutil
        # Conservatively reserve room for candidate canonical data and derived
        # artifacts while retaining the last-good generation. This is a preflight,
        # not a guarantee that later writes cannot exhaust the filesystem.
        source_bytes = 0
        target_root = Path(target).resolve()
        for entry in inventory.entries:
            path = (target_root / entry.path).resolve()
            if not path.is_relative_to(target_root):
                raise ValueError('Inventory source lies outside the target repository')
            try:
                source_bytes += path.stat().st_size
            except OSError:
                pass  # The parser reports missing/unreadable sources precisely.
        disk = shutil.disk_usage(cache_root)
        reserve = max(64 * 1024 * 1024, source_bytes * 2, int(disk.total * 0.01))
        if disk.free < reserve:
            raise RuntimeError(f'Insufficient disk space for indexing candidate: need {reserve} bytes free; '
                               f'available {disk.free}. Preserve the active generation and free space.')
        cache = SqliteIngestionCache(Path(cache_root) / 'indexing-state.sqlite', compatibility_hash=fingerprint)
        try:
            cache.import_legacy(Path(cache_root) / 'ingestion.json')
            from contextlib import ExitStack
            from pi_platform.adapters.sync.portable_format import ROOT
            from pi_platform.adapters.sync.portable_snapshot_reader import verified_snapshot
            with ExitStack() as snapshots:
                portable_root = Path(target) / 'project-knowledge'
                from pi_platform.adapters.sync.portable_format import PortableSnapshotError
                plan, rejected = None, False
                try:
                    if (portable_root / ROOT).exists():
                        plan = snapshots.enter_context(verified_snapshot(portable_root, cache_root))
                except (PortableSnapshotError, OSError):
                    if restore_only:
                        raise RestoreRequiresReindex('Portable snapshot rejected; reindex required') from None
                    rejected = True
                runtime = _index_repository(**arguments, durable_cache=cache, portable_plan=plan, skip_portable=rejected)
            cache.assert_fence()
            cache.finish('ready')
            return runtime
        except BaseException:
            cache.finish('failed')
            raise
        finally:
            cache.close()


def _index_repository(*, target, cache_root, inventory, previous_inventory, settings, cli_overrides=None, durable_cache=None, portable_plan=None, restore_only=False, skip_portable=False):
    """Parse current files, reuse vectors and return an unpublished runtime."""
    from pi_platform.adapters.config.runtime_configuration_resolver import RuntimeConfigurationResolver
    target, cache_root = Path(target).resolve(), Path(cache_root).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfigurationResolver(
        cli_overrides=cli_overrides,
        local_settings_path=target / '.project-intelligence-cache/settings.json',
    ).resolve()
    import os
    if (not restore_only and config.startup_profile == 'production' and config.docling_enabled
            and os.environ.get('PI_PREPARE_DOCLING', '0') == '1'
            and any(_family(e.path) == SourceContentFamily.PDF for e in inventory.entries)):
        from pi_platform.adapters.pdf.real_docling import _pinned_pdf_assets
        _pinned_pdf_assets(do_ocr=True)
    cache_path = cache_root / 'ingestion.json'
    cache = durable_cache if durable_cache is not None else _load_cache(cache_path)
    def progress(stage, total, completed=0, failed=0, degraded=0, state='running'):
        if durable_cache is not None:
            durable_cache.stage(stage, total, completed, failed, degraded, state=state)
    from pi_platform.adapters.sync.portable_format import ROOT as PORTABLE_ROOT
    from pi_platform.adapters.orchestration.knowledge_sync import KnowledgeSyncCoordinator
    portable = (KnowledgeSyncCoordinator(target, cache_root).settings()['share_enabled']
                or (target / 'project-knowledge' / PORTABLE_ROOT).exists()
                or os.environ.get('PI_PORTABLE_EXPORT', 'off') in {'review', 'approved-auto'})
    active_source_ids = {'repo:' + e.path for e in inventory.entries}
    for sid in cache.source_ids():
        if sid.startswith('repo:') and sid not in active_source_ids:
            cache.invalidate_source(sid, stale=False)
    parsers, chunkers = _default_parser_registry(), _default_chunker_registry()
    image_entries = [e for e in inventory.entries if Path(e.path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}]
    image_paths = {e.path for e in image_entries}
    pdf_entries = [e for e in inventory.entries if _family(e.path) == SourceContentFamily.PDF]
    pdf_db = None
    if pdf_entries and config.docling_enabled:
        from pi_platform.adapters.pdf.docling_pdf_adapter import build_real_docling_pdf_adapter
        from pi_platform.adapters.pdf.prescan import PdfPrescanAdapter
        from pi_platform.adapters.runtime.sqlite_ingestion_job_store import SqliteIngestionJobStore
        from pi_platform.adapters.runtime.sqlite_document_graph_store import SqliteDocumentGraphStore
        from pi_platform.adapters.pdf.docling_chunker import PdfStructuralChunker
        pdf_db = sqlite3.connect(cache_root / 'documents-v2.sqlite')
        pdf_db.row_factory = sqlite3.Row
        parsers.register(build_real_docling_pdf_adapter(
            PdfPrescanAdapter(), SqliteIngestionJobStore(pdf_db), SqliteDocumentGraphStore(pdf_db),
            embedding_model_id=settings.model_id, asset_root=cache_root / "document-assets",
        ))
        # Canonical chunks are model-independent. Tokenizer-specific splitting
        # remains a projection at the embedding adapter boundary.
        chunkers.register(PdfStructuralChunker())
    parallel = durable_cache is not None and os.environ.get('PI_INDEX_PARALLEL', '1') == '1'
    from pi_platform.core.ingest.source_decoding_policy import SourceDecodingPolicy, supported_policy_target
    try:
        decoding_policy = SourceDecodingPolicy.load(cache_root)
        # Validate conflicting rules before submitting any parser work.
        for entry in inventory.entries:
            if decoding_policy.profile(entry.path) and not supported_policy_target(entry.path, _family(entry.path)):
                raise ValueError('Legacy decoding rules require a Java or plain-text source')
    except ValueError as exc:
        raise CandidateIndexingError({'configuration_error': 1}) from exc
    driver = LocalPipelineDriver(decoding_policy=decoding_policy, parser_registry=parsers, chunker_registry=chunkers, cache=cache,
                                 parse_workers=None if parallel else 1, parallel_safe_registry=True)
    failures, diagnostics, sources = [], [], []
    require_complete = os.environ.get('PI_INDEX_REQUIRE_COMPLETE', '1') != '0'
    for entry in inventory.entries:
        if entry.path in image_paths:
            continue
        if _family(entry.path) == SourceContentFamily.PDF and not config.docling_enabled:
            cache.invalidate_source('repo:' + entry.path, stale=False)
            continue
        sources.append(Source(
            id='repo:' + entry.path, uri=str(target / entry.path),
            family=_family(entry.path).value, contentHash=entry.content_hash,
            metadata=Metadata(documentId='repo:' + entry.path, version='0.1.0', language='und',
                              sourcePath=entry.path, policy=entry.policy or None,
                              extensions={"portable_identity": "v2"}),
        ))
    from pi_platform.adapters.sync.portable_media import pipeline_key as source_pipeline_key, persist_image, IMAGE_PROJECTION
    media_sources = [Source(id='repo:' + e.path, uri=str(target / e.path), family='image', contentHash=e.content_hash,
        metadata=Metadata(documentId='repo:' + e.path, version='0.1.0', language='und', sourcePath=e.path,
                          policy=e.policy or None, extensions={'portable_identity': 'v2', 'media': 'image'}))
        for e in image_entries]
    eligible = len(sources) + len(media_sources)
    portable_import = {'state': 'rejected-snapshot'} if skip_portable else {}
    if durable_cache is not None:
        from pi_platform.core.canonical.content_address import content_address
        from pi_platform.core.canonical.value_types import to_canonical_json
        cache.select_sources((source.id, source.contentHash,
            content_address(to_canonical_json(source.metadata).decode()), source_pipeline_key(source, driver))
            for source in [*sources, *media_sources])
        if portable and not skip_portable:
            from pi_platform.adapters.sync.portable_snapshot_importer import import_sources
            portable_import = import_sources(target, cache_root, cache, [*sources, *media_sources], driver, plan=portable_plan)
    progress('sources', len(sources) + len(media_sources), len(cache.source_ids()))
    pdf_admission = {}
    try:
        if restore_only:
            missing = sum(cache.source_record(source.id) is None for source in sources)
            missing += sum(cache.source_record(source.id) is None for source in media_sources)
            missing += len(inventory.entries) - len(sources) - len(media_sources)
            if missing:
                raise RestoreRequiresReindex('Current source results are missing or incompatible; reindex required',
                    report={**portable_import, 'missingSources': missing})
            reports = ()
        elif durable_cache is not None and int(os.environ.get('PI_PDF_WORKERS', '1')) > 1 and pdf_entries and config.docling_enabled:
            from pi_platform.adapters.pdf.process_sources import run_pdf_sources
            if pdf_db is not None:
                pdf_db.commit()
                pdf_db.close()
                pdf_db = None
            regular = driver.run_many([source for source in sources if source.family != 'pdf'], target)
            fatal = any(report.error_category in {'configuration_error', 'internal_error', 'cancelled'} for report in regular)
            pdf_reports = () if fatal else run_pdf_sources(
                [source for source in sources if source.family == 'pdf'], target, cache=cache,
                documents_db_path=cache_root / 'documents-v2.sqlite', asset_root=cache_root / 'document-assets',
                embedding_model_id=settings.model_id,
                pipeline_keys={source.id: driver.pipeline_key(source) for source in sources if source.family == 'pdf'},
                resource_pool=driver.resource_pool, diagnostics=pdf_admission)
            by_id = {report.source_id: report for report in (*regular, *pdf_reports)}
            reports = tuple(by_id[source.id] for source in sources if source.id in by_id)
        else:
            reports = driver.run_many(sources, target)
        source_by_id = {source.id: source for source in sources}
        fatal = Counter()
        for report in reports:
            source = source_by_id[report.source_id]
            if not report.ok:
                cache.invalidate_source(source.id, stale=False)
                failures.append({'path': source.metadata.sourcePath, 'error': report.error_message,
                                 'category': report.error_category})
                failed_stage = next((stage for stage in report.stages if stage.error_category), None)
                diagnostics.append({
                    'path': source.metadata.sourcePath, 'sourceHash': source.contentHash,
                    'family': source.family, 'category': report.error_category,
                    'stage': failed_stage.stage if failed_stage else 'source',
                    'attempts': failed_stage.attempts if failed_stage else 1,
                })
                if report.error_category in {"configuration_error", "internal_error", "cancelled"}:
                    fatal[report.error_category] += 1
        if config.embedding_model not in {'gemma', 'gemma-torch'}:
            for source in media_sources:
                cache.invalidate_source(source.id, stale=False)
                failures.append({'path': source.metadata.sourcePath, 'category': 'unsupported_modality',
                                 'error': 'Image embeddings require the Gemma binding'})
                diagnostics.append({'path': source.metadata.sourcePath, 'sourceHash': source.contentHash,
                                    'family': source.family, 'category': 'unsupported_modality',
                                    'stage': 'source', 'attempts': 1})
        if durable_cache is not None and not restore_only:
            from pi_platform.core.ingest.source_failure_report import write_source_failures
            durable_cache.assert_fence()
            write_source_failures(cache_root, job_id=durable_cache.generation,
                                  eligible=eligible, attempted=len(reports) + len(media_sources), failures=diagnostics)
        degraded = sum(report.ok and report.degraded for report in reports)
        if durable_cache is not None and not restore_only and not fatal and len(reports) != len(sources):
            fatal['internal_error'] += 1
        blocked = bool(fatal or (failures and (restore_only or require_complete) and durable_cache is not None))
        if blocked:
            progress('sources', eligible, len(cache.source_ids()), len(failures), degraded, state='failed')
        if fatal:
            raise CandidateIndexingError(dict(fatal))
        if blocked:
            raise CandidateIndexingError(dict(Counter(f['category'] for f in failures)))
    finally:
        if pdf_db is not None:
            pdf_db.commit()
            pdf_db.close()
    if durable_cache is not None:
        if config.embedding_model in {'gemma', 'gemma-torch'}:
            for source in media_sources:
                persist_image(cache, source, driver)
        indexed = len(cache.source_ids())
        if indexed + len(failures) != eligible or (failures and not indexed):
            progress('sources', eligible, indexed, len(failures), degraded, state='failed')
            raise CandidateIndexingError(dict(Counter(f['category'] for f in failures)) or {'internal_error': 1})
    else:
        indexed = eligible - len(failures)
    coverage = {'eligible': eligible, 'indexed': indexed, 'skipped': len(failures)}
    progress('sources', eligible, indexed, len(failures), degraded,
             state='complete_with_skips' if failures else 'complete')
    progress('projection', len(inventory.entries))
    chunks_by_id = {}
    for raw in cache.iter_records():
        data = json.loads(raw)
        body = data.get('chunk', data) if isinstance(data, dict) else {}
        if body.get('rawText') and body.get('id'):
            # Contextual records overwrite their raw counterparts, preserving
            # deterministic retrieval_text produced by the existing pipeline.
            old = chunks_by_id.get(body['id'])
            if old is None or body.get('metadata', {}).get('extensions', {}).get('retrieval_text'):
                chunks_by_id[body['id']] = body
    # Persist the effective retrieval projection per source alongside raw
    # fingerprints. This remains model-independent across vector namespaces.
    projected_entries = []
    for completed, entry in enumerate(inventory.entries, 1):
        source_id = 'repo:' + entry.path
        if durable_cache is not None:
            payloads = cache.source_payloads(source_id)
        else:
            record = cache.source_record(source_id) or {}
            payloads = (cache.get(address) for address in record.get('addresses', ()))
        projected = {}
        for raw in payloads:
            if raw is None:
                continue
            body = json.loads(raw)
            body = body.get('chunk', body) if isinstance(body, dict) else {}
            if body.get('rawText') and body.get('id'):
                text = body.get('metadata', {}).get('extensions', {}).get('retrieval_text') or body.get('contextualText') or body['rawText']
                projected[body['id']] = hashlib.sha256(text.encode()).hexdigest()
        projection_hash = hashlib.sha256(json.dumps(sorted(projected.items())).encode()).hexdigest() if projected else ''
        projected_entries.append(replace(entry, retrieval_text_hash=projection_hash))
        if completed % 256 == 0:
            progress('projection', len(inventory.entries), completed)
    projected_inventory = replace(inventory, entries=tuple(projected_entries))
    catalog, active = {}, []
    for cid, body in sorted(chunks_by_id.items()):
        meta = body.get('metadata', {})
        text = meta.get('extensions', {}).get('retrieval_text') or body.get('contextualText') or body['rawText']
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        metadata = Metadata(**{k: v for k, v in meta.items() if k in Metadata.__dataclass_fields__})
        # Local inbox citations retain their native paths without making
        # persisted chunk identity depend on access policy or engine choice.
        if metadata.policy == 'LOCAL_ONLY' and metadata.sourcePath:
            metadata = replace(metadata, sourcePath=str(target / metadata.sourcePath))
        catalog[cid] = RetrievalHit(
            chunkId=cid, score=0.5, source='sparse', snippet=text,
            contentHash=body.get('contentHash', ''),
            metadata=metadata,
            knowledgeState=KnowledgeState(body.get('provenance', {}).get('knowledgeState', 'verified')), tokenEstimate=max(1, len(text.split())),
        )
        active.append(ActiveChunk(cid, body.get('contentHash', text_hash), text, text_hash, meta))
    # Checked export fragments are search-only evidence. Full local source outputs
    # take precedence; no fragment can satisfy source-cache or restore completeness.
    if portable_plan is not None:
        from pi_platform.adapters.sync.checked_context import context_chunks
        from pi_platform.adapters.sync.safe_export_projector import source_reviews
        context_db, _ = portable_plan
        for cid, body in context_chunks(context_db, existing_sources=cache.source_ids(),
                inventory={entry.path: entry for entry in inventory.entries}, reviews=source_reviews(cache_root)):
            text = body['text']; text_hash = body['textHash']
            meta = {'documentId': 'checked-context:' + cid, 'sourcePath': body['path'], 'version':'0.1.0', 'language':'und',
                    'extensions': {'exportProjection': body['projection'], 'originalSourceHash': body['sourceHash']}}
            catalog[cid] = RetrievalHit(chunkId=cid, score=0.5, source='sparse', snippet=text,
                contentHash=text_hash, metadata=Metadata(**meta), knowledgeState=KnowledgeState.VERIFIED,
                tokenEstimate=max(1, len(text.split())))
            active.append(ActiveChunk(cid, text_hash, text, text_hash, meta))
    for entry in image_entries:
        if config.embedding_model not in {'gemma', 'gemma-torch'}:
            continue
        path = (target / entry.path).resolve()
        if not path.is_relative_to(target):
            raise RuntimeError('Image input is outside the target repository')
        cid = hashlib.sha256(('image:' + entry.path).encode()).hexdigest()
        text = 'Image: ' + entry.path
        meta = {'sourcePath': entry.path, 'documentId': 'repo:' + entry.path,
                'version': entry.content_hash, 'language': 'und',
                'policy': entry.policy or None,
                # The media marker lets the reranker know that this
                # candidate was embedded together with its pixels, so a
                # text-only reranker does not demote it for having no
                # textual representation.
                'extensions': {'media': 'image'}}
        image_hash = hashlib.sha256((text + entry.content_hash + IMAGE_PROJECTION).encode()).hexdigest()
        active.append(ActiveChunk(cid, entry.content_hash, text, image_hash, meta, image_path=str(path)))
        catalog[cid] = RetrievalHit(chunkId=cid, score=0.5, source='dense', snippet=text,
            contentHash=entry.content_hash, metadata=Metadata(**meta),
            knowledgeState=KnowledgeState.VERIFIED, tokenEstimate=max(1, len(text.split())))
    corpus_hash = hashlib.sha256(json.dumps([(c.chunk_id, c.retrieval_text_hash) for c in active]).encode()).hexdigest()
    exact_path = cache_root / 'indexes' / 'exact' / (corpus_hash + '.sqlite')
    exact_path.parent.mkdir(parents=True, exist_ok=True)
    progress('projection', len(inventory.entries), len(inventory.entries), state='complete')
    progress('exact', len(catalog))
    from pi_platform.adapters.runtime.candidate_artifacts import build_exact
    exact = build_exact(exact_path, [(cid, hit.snippet) for cid, hit in catalog.items()], corpus_hash,
                        progress=lambda completed, total: progress('exact', total, completed,
                            state='complete' if completed == total else 'running'))
    if durable_cache is not None:
        cache.artifact('exact', 'sqlite-fts', exact_path, corpus_hash, len(catalog))
    progress('graph', 0)
    graph_expansion, graph_node_ids = _candidate_graph(target, cache_root, cache,
        progress=lambda completed, total: progress('graph', total, completed,
            state='complete' if completed == total else 'running'))
    if durable_cache is not None:
        graph_path = graph_expansion._graph.root if hasattr(graph_expansion, '_graph') else None
        if graph_path is not None:
            cache.artifact('graph', 'sharded-graph', graph_path / 'ready.json', graph_path.name, len(graph_node_ids))
    from pi_platform.ports.retrieval.reranker import RerankPolicy
    rerank_policy = RerankPolicy(
        enabled=config.reranking_enabled,
        family=config.reranking_family,
        top_n=config.reranking_top_n,
        timeout_ms=config.reranking_timeout_ms,
    )
    progress('embedding', len(active))
    runtime = build_production_retrieval_runtime(
        cache_root=cache_root / 'indexes', embedding_alias=config.embedding_model,
        startup_profile=config.startup_profile, device=config.embedding_device,
        model_cache_dir=config.model_cache_dir,
        prefer_real_usearch=config.dense_index == 'usearch', chunk_catalog=catalog, exact_lookup=exact,
        graph_expansion=graph_expansion,
        rerank_policy=rerank_policy,
    )
    pdf_projections = {}
    # A production model must actually load, even for an empty repository.
    if config.startup_profile == 'production':
        from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole
        if not restore_only:
            runtime.embedding_model.embed_request(EmbeddingRequest(text='startup health check', role=EmbeddingRole.QUERY))
        pdf_chunk_ids = {chunk.chunk_id for chunk in active
                         if str(chunk.metadata.get('sourcePath', '')).lower().endswith('.pdf')}
        if pdf_chunk_ids:
            from pi_platform.adapters.pdf.runtime_projection import PdfRuntimeProjection, PDF_RUNTIME_PROJECTION_VERSION
            tokenizer_model = runtime.embedding_model.profile().model_id
            projection = PdfRuntimeProjection(tokenizer_model)
            projected = []
            for chunk in active:
                if chunk.chunk_id not in pdf_chunk_ids:
                    projected.append(chunk)
                    continue
                image_path = None
                body = chunks_by_id[chunk.chunk_id]
                descriptor = body.get('metadata', {}).get('extensions', {}).get('pdf_asset')
                if config.embedding_model in {'gemma', 'gemma-torch'} and descriptor is None:
                    image_path = _figure_image_path(body, cache_root)
                segments = projection(body)
                if not segments:
                    raise RuntimeError(f"PDF projection produced no text for {chunk.chunk_id}")
                # The projection policy participates in vector reuse, while
                # canonical text, anchors and chunk identities stay unchanged.
                projection_identity = {
                    'version': PDF_RUNTIME_PROJECTION_VERSION,
                    'aggregation': 'normalized-mean/v1', 'max_tokens': 512,
                    'canonical_text_hash': chunk.retrieval_text_hash,
                    'segments': segments,
                    'image_hash': (descriptor['byteHash'] if descriptor and config.embedding_model in {'gemma', 'gemma-torch'}
                                   else hashlib.sha256(Path(image_path).read_bytes()).hexdigest() if image_path else None),
                }
                from pi_platform.adapters.sync.portable_pdf_vectors import projection_hash as pdf_projection_hash
                projection_hash = pdf_projection_hash(projection_identity)
                pdf_projections[chunk.chunk_id] = projection_identity
                projected.append(replace(chunk, embedding_segments=segments, image_path=image_path,
                                         retrieval_text_hash=projection_hash))
            active = projected
    if durable_cache is not None:
        runtime.semantic_index_service.set_progress_callback(
            lambda completed, total: progress('embedding', total, completed,
                state='complete' if completed == total else 'running'))
    imported_vectors = 0
    if durable_cache is not None and portable and not skip_portable:
        from pi_platform.adapters.sync.portable_snapshot_importer import import_vectors
        imported_vectors = import_vectors(target, cache_root, runtime, active, plan=portable_plan)
    assets_regenerated = 0
    if pdf_projections and not restore_only:
        from pi_platform.adapters.pdf.portable_assets import ensure_local_asset
        from pi_platform.adapters.runtime.sqlite_vector_record_store import decode_vector_payload
        pages = {}
        resolved = []
        for chunk in active:
            descriptor = chunk.metadata.get('extensions', {}).get('pdf_asset')
            record = runtime.vector_record_store.get(chunk.chunk_id, runtime.embedding_profile_hash) if descriptor else None
            exact = (record is not None and record.created_from_retrieval_text_hash == chunk.retrieval_text_hash
                     and record.model_revision == runtime.embedding_model.profile().model_revision
                     and record.dimension == runtime.embedding_model.profile().output_dimension
                     and record.normalization == runtime.embedding_model.profile().normalization)
            if exact:
                try:
                    runtime.semantic_index_service._validate_vector(decode_vector_payload(record.vector_payload), chunk.chunk_id)
                except (ValueError, RuntimeError):
                    exact = False
            if descriptor and config.embedding_model in {'gemma', 'gemma-torch'} and not exact:
                old = len(pages)
                path = ensure_local_asset(target, cache_root, descriptor, pages=pages)
                assets_regenerated += int(len(pages) != old)
                chunk = replace(chunk, image_path=path)
            resolved.append(chunk)
        active = resolved
    try:
        report, dense_generation_loaded = _index_dense_generation(runtime, active, restore_only=restore_only)
    except RestoreRequiresReindex as exc:
        exc.report.update({**portable_import, 'importedVectors': imported_vectors})
        raise
    if durable_cache is not None:
        from pi_platform.adapters.sync.portable_pdf_vectors import persist_projections
        persist_projections(cache_root, runtime.embedding_profile_hash, pdf_projections)
    progress('embedding', len(active), len(active), state='complete')
    if durable_cache is not None and hasattr(runtime.dense_index, 'index_path'):
        index_path = Path(runtime.dense_index.index_path)
        for path in (index_path, index_path.with_suffix('.meta.json'), Path(str(index_path) + '.keys.json')):
            if path.is_file():
                cache.artifact(path.name, 'dense', path, report.source_generation, len(active))
    progress('sparse', len(catalog))
    for cid, hit in catalog.items():
        runtime.sparse_index.index_document('chunks', cid, hit.snippet, {})
    progress('sparse', len(catalog), len(catalog), state='complete')
    if durable_cache is None:
        saved = {**cache.snapshot(), 'failures': failures}
        from pi_platform.adapters.runtime.candidate_artifacts import atomic_bytes
        atomic_bytes(cache_path, json.dumps(saved, sort_keys=True).encode())
    from pi_platform.core.wiki.llm_wiki import INDEX_FILENAME, LOG_FILENAME
    wiki_prefix = 'project-knowledge/wiki/'
    failed_sources = {failure['path'] for failure in failures}
    indexed_wiki_pages = sum(
        entry.path.startswith(wiki_prefix) and entry.path.endswith('.md')
        and entry.path.removeprefix(wiki_prefix) not in {INDEX_FILENAME, LOG_FILENAME}
        and entry.path not in failed_sources
        for entry in projected_inventory.entries
    )
    return replace(runtime, extra={
        'portable_import': {**portable_import, 'importedVectors': imported_vectors},
        'figure_assets_regenerated': assets_regenerated,
        'source_inventory': projected_inventory,
        'graph_node_ids': graph_node_ids,
        'chunk_ids': tuple(catalog), 'chunk_catalog': catalog,
        'source_generation': report.source_generation,
        'dense_generation_loaded': dense_generation_loaded,
        'indexing_report': report, 'source_failures': failures, 'source_coverage': coverage,
        'indexed_wiki_pages': indexed_wiki_pages,
        'resolved_configuration': config.as_dict(),
        'index_engine': 'resumable' if durable_cache is not None else 'legacy',
        'index_job_id': durable_cache.generation if durable_cache is not None else '',
        'index_fence': durable_cache.fence if durable_cache is not None else 0,
        'source_parse_hits': sum(any(stage.stage == 'parse' and stage.cache_hit for stage in report.stages) for report in reports),
        'source_parse_misses': sum(any(stage.stage == 'parse' and not stage.cache_hit for stage in report.stages) for report in reports),
        'source_admission': driver.last_admission,
        'pdf_admission': pdf_admission,
    })


def _figure_image_path(body, cache_root):
    """Resolve only verified, extracted local PDF image assets for Gemma."""
    from pi_platform.adapters.runtime.sqlite_document_graph_store import SqliteDocumentGraphStore
    asset_ids = [a.get('asset_id') for a in body.get('anchors', ()) if isinstance(a, dict) and a.get('asset_id')]
    if not asset_ids:
        return None
    from contextlib import closing
    with closing(sqlite3.connect(cache_root / 'documents-v2.sqlite')) as db:
        db.row_factory = sqlite3.Row
        asset = SqliteDocumentGraphStore(db).get_asset(asset_ids[0])
    if asset is None:
        raise RuntimeError('PDF figure asset missing from document store')
    path = Path(asset.cas_path).resolve()
    if not path.is_relative_to((cache_root / 'document-assets').resolve()) or not path.is_file():
        raise RuntimeError('PDF figure asset is missing or outside the document asset cache')
    if hashlib.sha256(path.read_bytes()).hexdigest() != asset.byte_hash:
        raise RuntimeError('PDF figure asset checksum mismatch')
    return str(path)
