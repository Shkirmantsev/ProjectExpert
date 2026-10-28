"""Build a candidate retrieval runtime from real repository sources.

Canonical files are read-only. Parsed chunks are reused across model switches;
vectors are persisted by embedding profile. Only callers publish the returned
candidate after checking the source version and committing its snapshot.
"""
from dataclasses import replace
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
from pi_platform.ports.ingest.source_adapter import SourceContentFamily
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from .retrieval_composition import build_production_retrieval_runtime


def _family(path):
    from pi_platform.adapters.python.intelligence import python_family
    p = Path(path)
    if family := python_family(p):
        return family
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
        cache._store = {k: v.encode() for k, v in saved.get('records', {}).items()}
        cache._sources = saved.get('sources', {})
        cache._owners = {k: set(v) for k, v in saved.get('owners', {}).items()}
    return cache


def _candidate_graph(target, cache_root, cache):
    """Snapshot graph bodies into a disposable generation, never canonical Git."""
    from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
    from pi_platform.adapters.runtime.graph_expansion import ProductionGraphExpansion
    from pi_platform.core.canonical.value_types import Entity, Relation, from_canonical_json
    records = [json.loads(raw) for raw in cache._store.values()]
    canonical = target / 'project-knowledge' / 'graph'
    if canonical.is_dir():
        for path in sorted(canonical.rglob('*')):
            if not path.is_file() or path.is_symlink() or path.suffix not in {'.json', '.jsonl'}:
                continue
            if 'objects' in path.relative_to(canonical).parts:
                continue  # historical content-addressed bodies are not active nodes
            texts = path.read_text(encoding='utf-8').splitlines() if path.suffix == '.jsonl' else [path.read_text(encoding='utf-8')]
            for text in texts:
                if text.strip():
                    body = json.loads(text)
                    records.extend(body if isinstance(body, list) else [body])
    # Legacy runtime.db retains historical versions. Only the active canonical
    # tree and current ingestion ownership above define this served graph.
    entities, relations = {}, {}
    for record in records:
        if not isinstance(record, dict):
            continue
        if {'id', 'family', 'label'}.issubset(record):
            entities[record['id']] = from_canonical_json(Entity, json.dumps(record))
        elif {'sourceId', 'targetId', 'family'}.issubset(record):
            relations[(record['sourceId'], record['targetId'], record['family'])] = from_canonical_json(Relation, json.dumps(record))
    bodies = [json.dumps(__import__('dataclasses').asdict(v), sort_keys=True) for v in (*entities.values(), *relations.values())]
    generation = hashlib.sha256('\n'.join(sorted(bodies)).encode()).hexdigest()
    graph = LocalShardedGraph(cache_root / 'indexes' / 'graph' / generation)
    for entity in entities.values():
        graph.upsert_entity(entity)
    for relation in relations.values():
        graph.upsert_relation(relation)
    return ProductionGraphExpansion(graph), tuple(sorted(entities))


def _index_dense_generation(runtime, active):
    """Reuse valid ANN files, otherwise rebuild only from valid SQLite vectors."""
    import math
    from pi_platform.adapters.runtime.usearch_dense_index import USearchDenseIndex, compute_source_generation
    from pi_platform.core.retrieval.semantic_index_service import decode_vector_payload

    dense = runtime.dense_index
    generation = compute_source_generation(
        [chunk.chunk_id for chunk in active],
        retrieval_text_hashes=[chunk.retrieval_text_hash for chunk in active],
        embedding_profile_hash=runtime.embedding_profile_hash,
    )
    loaded = False
    if isinstance(dense, USearchDenseIndex) and dense._real_usearch:
        profile = runtime.embedding_model.profile()
        vectors = {}
        for chunk in active:
            record = runtime.vector_record_store.get(chunk.chunk_id, runtime.embedding_profile_hash)
            if record is None:
                continue
            try:
                vector = decode_vector_payload(record.vector_payload)
                valid = (
                    record.created_from_retrieval_text_hash == chunk.retrieval_text_hash
                    and record.dimension == profile.output_dimension
                    and record.model_revision == profile.model_revision
                    and record.normalization == profile.normalization
                    and len(vector) == profile.output_dimension
                    and all(math.isfinite(value) for value in vector)
                )
                if profile.normalization == "l2":
                    valid = valid and abs(sum(value * value for value in vector) - 1.0) < 0.02
            except (ValueError, TypeError, RuntimeError):
                valid = False
            if valid:
                vectors[chunk.chunk_id] = vector
            else:
                runtime.vector_record_store.delete(chunk.chunk_id, runtime.embedding_profile_hash)
        if len(vectors) == len(active):
            loaded = dense.load_generation(
                generation, vectors=vectors,
                metadata={chunk.chunk_id: chunk.metadata for chunk in active},
            )
        if not loaded:
            dense.select_generation(generation)
            dense.reset_candidate(output_dimension=profile.output_dimension)
    report = runtime.semantic_index_service.embed_active_chunks(active)
    if isinstance(dense, USearchDenseIndex) and not loaded:
        dense.save_generation(report.source_generation)
    return report, loaded


def index_repository(*, target, cache_root, inventory, previous_inventory, settings, cli_overrides=None):
    """Parse current files, reuse vectors and return an unpublished runtime."""
    from pi_platform.adapters.config.runtime_configuration_resolver import RuntimeConfigurationResolver
    target, cache_root = Path(target).resolve(), Path(cache_root).resolve()
    cache_root.mkdir(parents=True, exist_ok=True)
    config = RuntimeConfigurationResolver(
        cli_overrides=cli_overrides,
        local_settings_path=target / '.project-intelligence-cache/settings.json',
    ).resolve()
    import os
    if (config.startup_profile == 'production' and config.docling_enabled
            and os.environ.get('PI_PREPARE_DOCLING', '0') == '1'
            and any(_family(e.path) == SourceContentFamily.PDF for e in inventory.entries)):
        from pi_platform.adapters.pdf.real_docling import _pinned_pdf_assets
        _pinned_pdf_assets(do_ocr=True)
    cache_path = cache_root / 'ingestion.json'
    cache = _load_cache(cache_path)
    active_source_ids = {'repo:' + e.path for e in inventory.entries}
    for sid in tuple(cache._sources):
        if sid.startswith('repo:') and sid not in active_source_ids:
            cache.invalidate_source(sid, stale=False)
    parsers, chunkers = _default_parser_registry(), _default_chunker_registry()
    image_entries = [e for e in inventory.entries if Path(e.path).suffix.lower() in {'.png', '.jpg', '.jpeg', '.webp'}]
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
    driver = LocalPipelineDriver(parser_registry=parsers, chunker_registry=chunkers, cache=cache)
    failures = []
    try:
        for entry in inventory.entries:
            if entry in image_entries:
                continue
            if _family(entry.path) == SourceContentFamily.PDF and not config.docling_enabled:
                cache.invalidate_source('repo:' + entry.path, stale=False)
                continue
            source = Source(
                id='repo:' + entry.path, uri=str(target / entry.path),
                family=_family(entry.path).value, contentHash=entry.content_hash,
                metadata=Metadata(documentId='repo:' + entry.path, version='0.1.0', language='und', sourcePath=entry.path),
            )
            report = driver.run(source, target)
            if not report.ok:
                cache.invalidate_source(source.id, stale=False)
                if report.error_category in {"configuration_error", "internal_error"}:
                    raise RuntimeError(f"Ingestion failed for {entry.path}: {report.error_message}")
                failures.append({'path': entry.path, 'error': report.error_message, 'category': report.error_category})
    finally:
        if pdf_db is not None:
            pdf_db.commit()
            pdf_db.close()
    chunks_by_id = {}
    for raw in cache._store.values():
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
    for entry in inventory.entries:
        record = cache.source_record('repo:' + entry.path) or {}
        projected = {}
        for address in record.get('addresses', ()):
            raw = cache._store.get(address)
            if raw is None:
                continue
            body = json.loads(raw)
            body = body.get('chunk', body) if isinstance(body, dict) else {}
            if body.get('rawText') and body.get('id'):
                text = body.get('metadata', {}).get('extensions', {}).get('retrieval_text') or body.get('contextualText') or body['rawText']
                projected[body['id']] = hashlib.sha256(text.encode()).hexdigest()
        projection_hash = hashlib.sha256(json.dumps(sorted(projected.items())).encode()).hexdigest() if projected else ''
        projected_entries.append(replace(entry, retrieval_text_hash=projection_hash))
    projected_inventory = replace(inventory, entries=tuple(projected_entries))
    catalog, active = {}, []
    for cid, body in sorted(chunks_by_id.items()):
        meta = body.get('metadata', {})
        text = meta.get('extensions', {}).get('retrieval_text') or body.get('contextualText') or body['rawText']
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        catalog[cid] = RetrievalHit(
            chunkId=cid, score=0.5, source='sparse', snippet=text,
            contentHash=body.get('contentHash', ''),
            metadata=Metadata(**{k: v for k, v in meta.items() if k in Metadata.__dataclass_fields__}),
            knowledgeState=KnowledgeState.VERIFIED, tokenEstimate=max(1, len(text.split())),
        )
        active.append(ActiveChunk(cid, body.get('contentHash', text_hash), text, text_hash, meta))
    for entry in image_entries:
        if config.embedding_model not in {'gemma', 'gemma-torch'}:
            failures.append({'path': entry.path, 'category': 'unsupported_modality',
                             'error': 'Image embeddings require the Gemma binding'})
            continue
        path = (target / entry.path).resolve()
        if not path.is_relative_to(target):
            raise RuntimeError('Image input is outside the target repository')
        cid = hashlib.sha256(('image:' + entry.path).encode()).hexdigest()
        text = 'Image: ' + entry.path
        meta = {'sourcePath': entry.path, 'documentId': 'repo:' + entry.path,
                'version': entry.content_hash, 'language': 'und',
                # The media marker lets the reranker know that this
                # candidate was embedded together with its pixels, so a
                # text-only reranker does not demote it for having no
                # textual representation.
                'extensions': {'media': 'image'}}
        image_hash = hashlib.sha256((text + entry.content_hash + 'gemma-image-v1').encode()).hexdigest()
        active.append(ActiveChunk(cid, entry.content_hash, text, image_hash, meta, image_path=str(path)))
        catalog[cid] = RetrievalHit(chunkId=cid, score=0.5, source='dense', snippet=text,
            contentHash=entry.content_hash, metadata=Metadata(**meta),
            knowledgeState=KnowledgeState.VERIFIED, tokenEstimate=max(1, len(text.split())))
    from pi_platform.adapters.runtime.sqlite_fts_full_text_index import SqliteFtsFullTextIndex
    corpus_hash = hashlib.sha256(json.dumps([(c.chunk_id, c.retrieval_text_hash) for c in active]).encode()).hexdigest()
    exact_path = cache_root / 'indexes' / 'exact' / (corpus_hash + '.sqlite')
    exact_path.parent.mkdir(parents=True, exist_ok=True)
    exact = SqliteFtsFullTextIndex(db_path=str(exact_path))
    for cid, hit in catalog.items():
        exact.index_document('chunks', cid, hit.snippet, {})
    graph_expansion, graph_node_ids = _candidate_graph(target, cache_root, cache)
    from pi_platform.ports.retrieval.reranker import RerankPolicy
    rerank_policy = RerankPolicy(
        enabled=config.reranking_enabled,
        family=config.reranking_family,
        top_n=config.reranking_top_n,
        timeout_ms=config.reranking_timeout_ms,
    )
    runtime = build_production_retrieval_runtime(
        cache_root=cache_root / 'indexes', embedding_alias=config.embedding_model,
        startup_profile=config.startup_profile, device=config.embedding_device,
        model_cache_dir=config.model_cache_dir,
        prefer_real_usearch=config.dense_index == 'usearch', chunk_catalog=catalog, exact_lookup=exact,
        graph_expansion=graph_expansion,
        rerank_policy=rerank_policy,
    )
    # A production model must actually load, even for an empty repository.
    if config.startup_profile == 'production':
        from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole
        runtime.embedding_model.embed_request(EmbeddingRequest(text='startup health check', role=EmbeddingRole.QUERY))
        pdf_chunks = [chunk for chunk in active
                      if str(chunk.metadata.get('sourcePath', '')).lower().endswith('.pdf')]
        if pdf_chunks:
            from pi_platform.adapters.pdf.runtime_projection import PdfRuntimeProjection, PDF_RUNTIME_PROJECTION_VERSION
            tokenizer_model = runtime.embedding_model.profile().model_id
            projection = PdfRuntimeProjection(tokenizer_model)
            projected = []
            for chunk in active:
                if chunk not in pdf_chunks:
                    projected.append(chunk)
                    continue
                image_path = None
                body = chunks_by_id[chunk.chunk_id]
                if config.embedding_model in {'gemma', 'gemma-torch'}:
                    image_path = _figure_image_path(body, cache_root)
                segments = projection(body)
                if not segments:
                    raise RuntimeError(f"PDF projection produced no text for {chunk.chunk_id}")
                # The projection policy participates in vector reuse, while
                # canonical text, anchors and chunk identities stay unchanged.
                projection_hash = hashlib.sha256(json.dumps({
                    'version': PDF_RUNTIME_PROJECTION_VERSION,
                    'aggregation': 'normalized-mean/v1', 'max_tokens': 512,
                    'canonical_text_hash': chunk.retrieval_text_hash,
                    'segments': segments,
                    'image_hash': hashlib.sha256(Path(image_path).read_bytes()).hexdigest() if image_path else None,
                }, sort_keys=True).encode()).hexdigest()
                projected.append(replace(chunk, embedding_segments=segments, image_path=image_path,
                                         retrieval_text_hash=projection_hash))
            active = projected
    report, dense_generation_loaded = _index_dense_generation(runtime, active)
    for cid, hit in catalog.items():
        runtime.sparse_index.index_document('chunks', cid, hit.snippet, {})
    saved = {
        'records': {k: v.decode() for k, v in cache._store.items()},
        'sources': cache._sources, 'owners': {k: sorted(v) for k, v in cache._owners.items()},
        'failures': failures,
    }
    temporary = cache_path.with_suffix('.tmp')
    temporary.write_text(json.dumps(saved, sort_keys=True), encoding='utf-8')
    temporary.replace(cache_path)
    return replace(runtime, extra={
        'source_inventory': projected_inventory,
        'graph_node_ids': graph_node_ids,
        'chunk_ids': tuple(catalog), 'chunk_catalog': catalog,
        'source_generation': report.source_generation,
        'dense_generation_loaded': dense_generation_loaded,
        'indexing_report': report, 'source_failures': failures,
        'resolved_configuration': config.as_dict(),
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
