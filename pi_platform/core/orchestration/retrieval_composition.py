"""Production retrieval runtime composition (open spec change PR 7, plan §27–§28).

Covers the ``unified-production-retrieval-composition`` spec delta:
the web UI, the MCP server, the CLI and the evaluation harness MUST
build the production retrieval stack through exactly one
composition. Two surfaces MUST NOT have materially different search
semantics for the same query and configuration.

The composition wires the documented Phase 4 retrieval stack:

* role-aware embedding model (resolved by alias through the
  :class:`EmbeddingModelFactory`);
* persisted :class:`VectorRecordStorePort` (authoritative storage);
* :class:`DenseIndexPort` (USearch HNSW by default;
  :class:`FlatDenseIndex` fallback for tests and the
  ``minimal`` startup profile);
* :class:`SparseIndexPort` (BM25-light);
* optional :class:`FullTextIndexPort` (SQLite FTS5) for exact
  identifier lookup;
* :class:`HybridRetrievalPort` that fuses dense, sparse and exact
  candidates through reciprocal-rank fusion;
* :class:`MetadataFilterPort` for the additive v0.8 refinement
  filters;
* :class:`RerankerPort` (BM25-light by default; production callers
  may override);
* :class:`GraphExpansionPort` for graph support evidence;
* :class:`ContextAssemblerPort` for the bounded context bundle;
* :class:`MultiStageRetrievalPort` orchestrator;
* :class:`SemanticIndexService` that owns the embedding-side
  indexing loop and reuses stored vectors across runs.

The composition is intentionally tolerant of test overrides: every
collaborator accepts an optional pre-built instance so unit tests
can inject fakes without paying the model-load cost.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from pi_platform.adapters.retrieval.bm25_light_reranker import (
    Bm25LightRerankerAdapter,
)
from pi_platform.adapters.retrieval.context_assembler_adapter import (
    ContextAssemblerAdapter,
)
from pi_platform.adapters.retrieval.hybrid_retrieval import (
    HybridRetrievalAdapter,
)
from pi_platform.adapters.retrieval.identifier_query_detector import (
    IdentifierQueryDetector,
)
from pi_platform.adapters.retrieval.metadata_filter_adapter import (
    MetadataFilterAdapter,
)
from pi_platform.adapters.retrieval.embedding_model_factory import (
    EmbeddingModelFactory,
    GEMMA_ALIAS,
    HASHING_ALIAS,
    PRODUCTION_ALIASES,
    QWEN_ALIAS,
    StartupProfile,
)
from pi_platform.adapters.runtime.bm25_sparse_index import Bm25SparseIndex
from pi_platform.adapters.runtime.flat_dense_index import FlatDenseIndex
from pi_platform.adapters.runtime.graph_expansion import ProductionGraphExpansion
from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
from pi_platform.adapters.runtime.sqlite_vector_record_store import (
    SqliteVectorRecordStore,
)
from pi_platform.adapters.runtime.usearch_dense_index import (
    DenseKeyStore,
    USearchDenseIndex,
    is_real_usearch_available,
)
from pi_platform.core.retrieval.hybrid_retrieval import (
    HybridRetrievalCore,
    IDENTIFIER_PATTERN,
)
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)
from pi_platform.core.retrieval.semantic_index_service import (
    SemanticIndexService,
)
from pi_platform.ports.retrieval.context_assembler import ContextAssemblerPort
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelPort
from pi_platform.ports.runtime.graph_expansion import GraphExpansionPort
from pi_platform.ports.runtime.graph import GraphPort

from pi_platform.ports.retrieval.hybrid_retrieval import (
    HybridRetrievalPort,
    RetrievalHit,
)
from pi_platform.ports.retrieval.metadata_filter import MetadataFilterPort
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalPort,
)
from pi_platform.ports.retrieval.reranker import RerankerPort
from pi_platform.ports.runtime.dense_index import DenseIndexPort
from pi_platform.ports.runtime.full_text_index import FullTextIndexPort
from pi_platform.ports.runtime.sparse_index import SparseIndexPort
from pi_platform.ports.runtime.vector_record_store import (
    VectorRecordStorePort,
)


__all__ = [
    "ProductionRetrievalRuntime",
    "DEFAULT_RERANK_BUDGET",
    "DEFAULT_TOP_K",
    "DEFAULT_CONTEXT_TOKEN_LIMIT",
    "build_production_retrieval_runtime",
    "build_sparse_index",
    "build_dense_index",
    "build_hybrid_retrieval",
    "build_reranker",
    "build_graph_expansion",
    "build_context_assembler",
    "build_metadata_filter",
    "build_multi_stage_retrieval",
    "build_semantic_index_service",
    "vector_record_store_from_db",
]


DEFAULT_RERANK_BUDGET = 50
DEFAULT_TOP_K = 50
DEFAULT_CONTEXT_TOKEN_LIMIT = 4000


@dataclass(frozen=True)
class ProductionRetrievalRuntime:
    """The composition result returned by
    :func:`build_production_retrieval_runtime`.

    Every field is a port or a service the consumers (UI, MCP, CLI,
    evaluation) MUST use; constructing a parallel port stack outside
    the composition would re-introduce a separate UI / MCP search
    path and break the spec's "one composition for all consumers"
    contract.
    """

    embedding_model: EmbeddingModelPort
    vector_record_store: VectorRecordStorePort
    dense_index: DenseIndexPort
    sparse_index: SparseIndexPort
    exact_lookup: FullTextIndexPort | None
    hybrid_retrieval: HybridRetrievalPort
    metadata_filter: MetadataFilterPort
    reranker: RerankerPort
    graph_expansion: GraphExpansionPort
    context_assembler: ContextAssemblerPort
    multi_stage_retrieval: MultiStageRetrievalPort
    semantic_index_service: SemanticIndexService
    embedding_profile_hash: str
    backend_name: str = "usearch"
    extra: Mapping[str, Any] = field(default_factory=dict)

    def stage_report(self) -> Mapping[str, Any]:
        """Return a single capability dict for status endpoints.

        The dict is the production truth: every stage reports the
        same backend name, the same profile hash and the same
        ``semantic_index_service`` instance.
        """

        return {
            "embedding_alias": getattr(
                self.embedding_model, "profile", lambda: None,
            )().__class__.__name__,
            "embedding_profile_hash": self.embedding_profile_hash,
            "backend": self.backend_name,
            "dense_backend": self.dense_index.stats().get(
                "backend", "unknown",
            ),
            "vector_records": self.vector_record_store.stats().get(
                "records", 0,
            ),
            "vectors": self.dense_index.stats().get("vectors", 0),
            "sparse_documents": self.sparse_index.stats().get(
                "documents", 0,
            ),
            "has_exact_lookup": self.exact_lookup is not None,
        }


def _default_cache_root() -> str:
    return os.path.join(
        ".project-intelligence-cache",
        "indexes",
    )


def build_sparse_index(
    *, sparse_index: SparseIndexPort | None = None,
) -> SparseIndexPort:
    """Return the production :class:`SparseIndexPort`.

    Defaults to :class:`Bm25SparseIndex` (stdlib-only BM25). Tests
    may inject a fake.
    """

    if sparse_index is not None:
        return sparse_index
    return Bm25SparseIndex()


def build_dense_index(
    *,
    embedding_profile_hash: str,
    cache_root: str,
    output_dimension: int,
    prefer_real_usearch: bool = True,
    dense_index: DenseIndexPort | None = None,
) -> DenseIndexPort:
    """Return the production :class:`DenseIndexPort`.

    When the optional :mod:`usearch` package is importable and
    ``prefer_real_usearch`` is True (the default), the real
    :class:`USearchDenseIndex` adapter is used. Otherwise the
    deterministic :class:`FlatDenseIndex` is used (CI / minimal
    profile).
    """

    if dense_index is not None:
        return dense_index
    if prefer_real_usearch and is_real_usearch_available():
        return USearchDenseIndex(
            embedding_profile_hash=embedding_profile_hash,
            cache_root=cache_root,
            output_dimension=output_dimension,
        )
    return FlatDenseIndex(
        embedding_profile_hash=embedding_profile_hash,
        output_dimension=output_dimension,
    )


def build_reranker(
    *, reranker: RerankerPort | None = None,
    budget: int = DEFAULT_RERANK_BUDGET,
) -> RerankerPort:
    """Return the production :class:`RerankerPort`.

    Defaults to :class:`Bm25LightRerankerAdapter`. Tests may inject
    a fake.
    """

    if reranker is not None:
        return reranker
    return Bm25LightRerankerAdapter(budget=budget)


def build_graph_expansion(
    *,
    graph_expansion: GraphExpansionPort | None = None,
    graph: GraphPort | None = None,
) -> GraphExpansionPort:
    """Return the production :class:`GraphExpansionPort`.

    The default production adapter requires a :class:`GraphPort` so
    expansion can read the canonical knowledge graph. When no graph
    is injected, an empty :class:`LocalShardedGraph` rooted at a
    cache directory is created; that is the right default for a
    fresh install (no canonical knowledge yet) and for tests.
    """

    if graph_expansion is not None:
        return graph_expansion
    if graph is None:
        graph = LocalShardedGraph(Path(_default_cache_root()) / "graph")
    return ProductionGraphExpansion(graph=graph)


def build_context_assembler(
    *, context_assembler: ContextAssemblerPort | None = None,
) -> ContextAssemblerPort:
    """Return the production :class:`ContextAssemblerPort`."""

    if context_assembler is not None:
        return context_assembler
    return ContextAssemblerAdapter()


def build_metadata_filter(
    *, metadata_filter: MetadataFilterPort | None = None,
) -> MetadataFilterPort:
    """Return the production :class:`MetadataFilterPort`."""

    if metadata_filter is not None:
        return metadata_filter
    return MetadataFilterAdapter()


def vector_record_store_from_db(
    db_path: str,
    *,
    factory: Callable[[str], Any] | None = None,
) -> VectorRecordStorePort:
    """Build a file-backed :class:`SqliteVectorRecordStore` whose operations
    close their owned SQLite connections at ``db_path``.

    The helper is the production entry point for the SQLite-backed
    vector record store; tests use the in-memory
    :class:`InMemoryVectorRecordStore` from
    :mod:`pi_platform.core.retrieval.semantic_index_service` instead.
    """

    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    # File-backed adapter closes every owned connection deterministically.
    return SqliteVectorRecordStore(db_path=db_path)


def build_hybrid_retrieval(
    *,
    dense_index: DenseIndexPort,
    sparse_index: SparseIndexPort,
    exact_lookup: FullTextIndexPort | None,
    hybrid_retrieval: HybridRetrievalPort | None = None,
    embedding_model: EmbeddingModelPort | None = None,
    chunk_catalog: Mapping[str, RetrievalHit] | None = None,
) -> HybridRetrievalPort:
    """Return the production :class:`HybridRetrievalPort`.

    The adapter wraps a :class:`HybridRetrievalCore` with callable
    bridges to the dense, sparse and exact ports so the production
    composition is the single source of truth for the dense +
    sparse + exact channels.
    """

    if hybrid_retrieval is not None:
        return hybrid_retrieval

    def _dense_query(text: str, top_k: int) -> Sequence[RetrievalHit]:
        if embedding_model is None:
            return ()
        from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole
        vector = embedding_model.embed_request(EmbeddingRequest(text=text, role=EmbeddingRole.QUERY))
        hits = []
        for hit in dense_index.query(vector, top_k=top_k):
            base = (chunk_catalog or {}).get(hit.chunkId)
            if base is not None:
                hits.append(replace(base, score=min(1.0, max(0.0, float(hit.score))), source="dense"))
        return tuple(hits)

    def _sparse_query(text: str, top_k: int) -> Sequence[RetrievalHit]:
        sparse_hits = sparse_index.query(text, top_k=top_k)
        return tuple(
            replace((chunk_catalog or {}).get(h.documentId) or RetrievalHit(
                chunkId=h.documentId, score=0.0, source="sparse", snippet=h.snippet or "",
            ), score=min(1.0, max(0.0, float(h.score))), source="sparse")
            for h in sparse_hits
        )

    def _exact_lookup_fn(identifier: str) -> Sequence[RetrievalHit]:
        if exact_lookup is None:
            return ()
        # Identifiers are literal text, never SQLite FTS query syntax. Dashes,
        # dots and quotes in protocol/Java names must not become operators.
        exact_hits = exact_lookup.query('"' + identifier.replace('"', '""') + '"', top_k=10)
        return tuple(
            replace((chunk_catalog or {}).get(h.documentId) or RetrievalHit(
                chunkId=h.documentId,
                score=0.0,
                source="exact",
                snippet=h.snippet or "",
            ), score=min(1.0, max(0.0, float(h.score))), source="exact")
            for h in exact_hits
        )

    identifier_detector = IdentifierQueryDetector()

    return HybridRetrievalAdapter(
        dense_query=_dense_query,
        sparse_query=_sparse_query,
        identifier_detector=identifier_detector,
        exact_lookup=_exact_lookup_fn,
        fusion_strategy="rrf",
    )


def build_multi_stage_retrieval(
    *,
    hybrid_retrieval: HybridRetrievalPort,
    metadata_filter: MetadataFilterPort,
    graph_expansion: GraphExpansionPort,
    reranker: RerankerPort,
    context_assembler: ContextAssemblerPort,
    multi_stage_retrieval: MultiStageRetrievalPort | None = None,
) -> MultiStageRetrievalPort:
    """Return the production :class:`MultiStageRetrievalPort`.

    The multi-stage orchestrator is the only place where the stage
    order (candidate → fusion → metadata → rerank → selection →
    graph expansion → context assembly) is enforced; building a
    parallel orchestrator outside the composition would re-create
    the "UI-only search path" the spec explicitly bans.
    """

    if multi_stage_retrieval is not None:
        return multi_stage_retrieval
    from pi_platform.core.retrieval.selection import SelectionCore
    return MultiStageRetrievalCore(
        selection=SelectionCore(),
        hybrid=hybrid_retrieval,
        metadata=metadata_filter,
        graph_expansion=graph_expansion,
        reranker=reranker,
        context_assembler=context_assembler,
    )


def build_semantic_index_service(
    *,
    embedding_model: EmbeddingModelPort,
    vector_record_store: VectorRecordStorePort,
    dense_index: DenseIndexPort,
    dense_key_store: DenseKeyStore | None = None,
) -> SemanticIndexService:
    """Return the production :class:`SemanticIndexService`.

    The service is the single entry point that the reconcile loop
    uses to apply a chunk diff; it is intentionally not part of the
    query path (it is an ingestion-time concern).
    """

    return SemanticIndexService(
        embedding_model=embedding_model,
        vector_record_store=vector_record_store,
        dense_index=dense_index,
        dense_key_store=dense_key_store,
    )


def build_production_retrieval_runtime(
    *,
    cache_root: Path | str | None = None,
    embedding_alias: str = GEMMA_ALIAS,
    device: str = "auto",
    model_cache_dir: str | None = None,
    startup_profile: str = StartupProfile.PRODUCTION,
    embedding_model: EmbeddingModelPort | None = None,
    vector_record_store: VectorRecordStorePort | None = None,
    sparse_index: SparseIndexPort | None = None,
    exact_lookup: FullTextIndexPort | None = None,
    dense_index: DenseIndexPort | None = None,
    reranker: RerankerPort | None = None,
    graph_expansion: GraphExpansionPort | None = None,
    context_assembler: ContextAssemblerPort | None = None,
    metadata_filter: MetadataFilterPort | None = None,
    hybrid_retrieval: HybridRetrievalPort | None = None,
    multi_stage_retrieval: MultiStageRetrievalPort | None = None,
    embedding_model_factory: EmbeddingModelFactory | None = None,
    prefer_real_usearch: bool = True,
    rerank_budget: int = DEFAULT_RERANK_BUDGET,
    chunk_catalog: Mapping[str, RetrievalHit] | None = None,
) -> ProductionRetrievalRuntime:
    """Build the production retrieval runtime.

    This is the single composition entry point the web UI, the MCP
    server, the CLI and the evaluation harness MUST use. Two
    surfaces MUST NOT build parallel retrieval stacks; if a consumer
    needs to override a single collaborator it does so by passing a
    pre-built port here, not by composing its own stack.

    ``embedding_alias`` defaults to :data:`GEMMA_ALIAS`. The factory
    refuses to silently substitute hashing for a production alias
    (see :class:`EmbeddingModelFactory`); callers that want the
    ``minimal`` profile must request ``startup_profile='minimal'``
    AND ``embedding_alias='hashing'`` explicitly.
    """

    # --- 1. embedding model ----------------------------------------
    factory = embedding_model_factory or EmbeddingModelFactory(
        startup_profile=startup_profile,
    )
    resolved_alias = (
        embedding_alias.strip().lower()
        if embedding_alias else GEMMA_ALIAS
    )
    if resolved_alias not in (PRODUCTION_ALIASES | {HASHING_ALIAS}):
        raise ValueError(
            f"unknown embedding alias {embedding_alias!r}; expected "
            f"one of {sorted(PRODUCTION_ALIASES | {HASHING_ALIAS})}"
        )
    embedding_model_port = embedding_model or factory.build(
        resolved_alias, device=device, cache_folder=str(Path(model_cache_dir) / "hub") if model_cache_dir else None,
    )
    embedding_profile = embedding_model_port.profile()
    embedding_profile_hash = embedding_profile.identity()

    if startup_profile == StartupProfile.PRODUCTION and resolved_alias == HASHING_ALIAS:
        raise ValueError("hashing requires the explicit minimal startup profile")
    if (startup_profile == StartupProfile.PRODUCTION and dense_index is None
            and (not prefer_real_usearch or not is_real_usearch_available())):
        raise RuntimeError("Production requires real USearch; install pi-platform[production] or select minimal explicitly")

    # --- 2. vector record store ------------------------------------
    if vector_record_store is None:
        cache_root_path = Path(cache_root) if cache_root else Path(
            _default_cache_root(),
        )
        db_path = str(cache_root_path / "embeddings.sqlite")
        store = vector_record_store_from_db(db_path)
    else:
        store = vector_record_store

    # --- 3. dense index --------------------------------------------
    cache_root_path = Path(cache_root) if cache_root else Path(
        _default_cache_root(),
    )
    profile_cache_root = str(
        cache_root_path / "dense" / embedding_profile_hash,
    )
    dense = dense_index or build_dense_index(
        embedding_profile_hash=embedding_profile_hash,
        cache_root=profile_cache_root,
        output_dimension=embedding_profile.output_dimension,
        prefer_real_usearch=prefer_real_usearch and startup_profile != StartupProfile.MINIMAL,
    )
    # When the caller injected a flat dense index for tests we
    # still keep the production profile-hash namespace contract:
    # the flat index stores profile_hash as a per-key field.
    if isinstance(dense, USearchDenseIndex):
        dense_key_store = DenseKeyStore(
            os.path.join(profile_cache_root, "dense_keys.sqlite"),
        )
        dense._dense_key_store = dense_key_store
    else:
        dense_key_store = None
    backend_name = (
        dense.stats().get("backend", "unknown")
        if isinstance(dense, USearchDenseIndex)
        else "flat"
    )

    # --- 4. sparse index -------------------------------------------
    sparse = build_sparse_index(sparse_index=sparse_index)

    # --- 5. hybrid retrieval ---------------------------------------
    hybrid = build_hybrid_retrieval(
        dense_index=dense,
        sparse_index=sparse,
        exact_lookup=exact_lookup,
        hybrid_retrieval=hybrid_retrieval,
        embedding_model=embedding_model_port,
        chunk_catalog=chunk_catalog,
    )

    # --- 6. metadata filter ----------------------------------------
    meta = build_metadata_filter(metadata_filter=metadata_filter)

    # --- 7. reranker -----------------------------------------------
    rnk = build_reranker(reranker=reranker, budget=rerank_budget)

    # --- 8. graph expansion ----------------------------------------
    graph = build_graph_expansion(graph_expansion=graph_expansion, graph=LocalShardedGraph(cache_root_path / "graph"))

    # --- 9. context assembler --------------------------------------
    assembler = build_context_assembler(
        context_assembler=context_assembler,
    )

    # --- 10. multi-stage retrieval ---------------------------------
    multi = build_multi_stage_retrieval(
        hybrid_retrieval=hybrid,
        metadata_filter=meta,
        graph_expansion=graph,
        reranker=rnk,
        context_assembler=assembler,
        multi_stage_retrieval=multi_stage_retrieval,
    )

    # --- 11. semantic index service --------------------------------
    semantic_index_service = build_semantic_index_service(
        embedding_model=embedding_model_port,
        vector_record_store=store,
        dense_index=dense,
        dense_key_store=dense_key_store,
    )

    return ProductionRetrievalRuntime(
        embedding_model=embedding_model_port,
        vector_record_store=store,
        dense_index=dense,
        sparse_index=sparse,
        exact_lookup=exact_lookup,
        hybrid_retrieval=hybrid,
        metadata_filter=meta,
        reranker=rnk,
        graph_expansion=graph,
        context_assembler=assembler,
        multi_stage_retrieval=multi,
        semantic_index_service=semantic_index_service,
        embedding_profile_hash=embedding_profile_hash,
        backend_name=str(backend_name),
    )
