---
id: modules.retrieval
title: Phase 4 retrieval module map
kind: modules
status: active
summary: Phase 4 retrieval ports, cores, adapters and CLI surface (embedding model, hybrid retrieval, multi-stage pipeline, graph expansion, reranker, metadata filters, context assembler, retrieval benchmark).
sourceRefs:
  - pi_platform/ports/retrieval/
  - pi_platform/core/retrieval/
  - pi_platform/adapters/retrieval/
  - pi_platform/adapters/runtime/graph_expansion.py
  - pi_platform/core/retrieval/semantic_index_service.py
  - pi_platform/core/orchestration/retrieval_composition.py
  - openspec/specs/2026-10-04-embedding-model/spec.md
  - openspec/specs/2026-10-04-hybrid-retrieval/spec.md
  - openspec/specs/2026-10-04-multi-stage-retrieval/spec.md
  - openspec/specs/2026-10-04-graph-expansion-production/spec.md
  - openspec/specs/2026-10-04-reranker-port/spec.md
  - openspec/specs/2026-10-04-metadata-filters/spec.md
  - openspec/specs/2026-10-04-context-assembler/spec.md
  - openspec/specs/2026-10-04-retrieval-benchmark/spec.md
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-embedding-port-query-document-roles/spec.md
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-real-embeddinggemma2-binding/spec.md
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-real-qwen3-embedding-binding/spec.md
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-real-usearch-dense-backend/spec.md
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-semantic-index-service/spec.md
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-unified-production-retrieval-composition/spec.md
maintenance:
  mode: authored
related:
  - interfaces.hybrid-retrieval
  - interfaces.reranker
  - modules.embeddings
  - modules.context-assembler
  - modules.release-gate
---

# Phase 4 retrieval modules

The Phase 4 retrieval layer composes the Phase 3 storage surface
(`pi_platform.ports.runtime`) and the §25 embedding model into the
§27 hybrid retrieval, the §29 multi-stage pipeline, the §30
pluggable reranker, the §24 / §56 metadata filters, the §31
production graph expansion and the §32 context assembler.

The retrieval layer ships as a port-and-adapter pair: ports under
`pi_platform/ports/retrieval/`, default cores under
`pi_platform/core/retrieval/`, default adapters under
`pi_platform/adapters/retrieval/`. The Phase 3 stub
`BoundedGraphExpansion` adapter remains in place for Phase 3
regression tests; the production `ProductionGraphExpansion`
adapter replaces it at runtime.

## Port modules (`pi_platform/ports/retrieval/`)

- `embedding_model.py` — `EmbeddingModelPort` abstract base with
  `embed`, `embed_batch`, `dimension`, `model_version`, `license_id`
  and `stats` operations.
- `hybrid_retrieval.py` — `HybridRetrievalPort` plus the
  `RetrievalHit` value type (the lingua-franca record exchanged
  across every Phase 4 stage) and the `dense` / `sparse` / `exact`
  / `hybrid` source vocabulary.
- `multi_stage_retrieval.py` — `MultiStageRetrievalPort` plus
  `RetrievalQuery`, `StageReport`, `RetrievalResult` and the
  seven documented stage names.
- `reranker.py` — `RerankerPort` plus the
  `DEFAULT_RERANK_BUDGET` cap that the multi-stage pipeline
  enforces.
- `metadata_filter.py` — `MetadataFilter` value type, the
  `MetadataFilterPort` abstract base and the documented drop-
  reason constants (`temporal_invalid`, `version_mismatch`,
  `security_denied`, `language_mismatch`, `domain_mismatch`,
  `module_mismatch`, `requirement_mismatch`).
- `context_assembler.py` — `ContextAssemblerPort`, `ContextBudget`,
  `Citation` and `ContextBundle` value types.

## Core modules (`pi_platform/core/retrieval/`)

- `embedding_model.py` — `HashingEmbeddingModel`: stdlib-only
  feature-hashing fallback that satisfies the §25 multilingual
  DE / EN / UK and opt-in RU scenario on a CPU-only machine.
- `hybrid_retrieval.py` — `HybridRetrievalCore`: identifier-
  recognition pre-pass (regex-based engineering-identifier
  grammar) plus the RRF / linear fusion strategies. Pure duck-
  typed callable composition so adapters wire the Phase 3
  dense / sparse ports without coupling.
- `multi_stage_retrieval.py` — `MultiStageRetrievalCore`: the
  seven-stage orchestrator with explicit per-stage budgets
  (default 50 / 50 / 40 / 30 / 30 / 20 / `contextBudget`).
- `reranker.py` — `Bm25LightRerankerCore`: stdlib-only BM25-light
  reranker fallback. Cross-encoder and ColBERT-style rerankers
  are opt-in adapters.
- `metadata_filter.py` — `MetadataFilterCore`: the §24 temporal
  validity rule, the project-version filter, the §56
  security-classification allow-list and the language / domain /
  module / requirement filters.
- `context_assembler.py` — `ContextAssemblerCore`: deduplication,
  context budget enforcement, citation preservation,
  authoritative-evidence preference, conflict detection and
  uncertainty surfacing per §32.
- `semantic_index_service.py` — `SemanticIndexService`: the single
  ingestion-side entry point that writes active chunks into the
  embedding model + dense index + vector record store. Reuse key
  is `sha256(retrieval_text_hash + profile_hash)` so unchanged
  chunks are never recomputed under the same embedding profile.
  `remove_chunks()` is the REMOVED branch the reconcile path uses.

## Adapter modules (`pi_platform/adapters/retrieval/`)

- `hashing_embedding_model.py` — `HashingEmbeddingAdapter`: the
  stdlib-only embedding adapter registered by default.
- `multilingual_st_embedding_model.py` —
  `MultilingualSentenceTransformerEmbeddingModel`: opt-in
  `paraphrase-multilingual-MiniLM-L12-v2` (Apache-2.0) adapter
  via the `sentence-transformers` package.
- `identifier_query_detector.py` — `IdentifierQueryDetector`:
  regex-based identifier pre-pass; routes engineering identifiers
  to the exact-lookup path before any vector search.
- `hybrid_retrieval.py` — `HybridRetrievalAdapter`: production
  composition adapter binding the Phase 3 dense / sparse ports to
  the `HybridRetrievalCore`.
- `bm25_light_reranker.py` — `Bm25LightRerankerAdapter`: stdlib
  reranker fallback (Apache-2.0).
- `cross_encoder_reranker.py` — `CrossEncoderRerankerAdapter`:
  opt-in `cross-encoder/ms-marco-MiniLM-L-6-v2` (MIT) via
  `sentence-transformers`.
- `colbert_style_reranker.py` — `ColBertStyleRerankerAdapter`:
  opt-in ColBERT-style late-interaction reranker (MIT) via
  `colbert-ai`.
- `metadata_filter_adapter.py` — `MetadataFilterAdapter`: default
  §24 / §56 filter adapter.
- `context_assembler_adapter.py` — `ContextAssemblerAdapter`:
  default §32 assembler adapter.
- `embeddinggemma2_embedding_model.py` —
  `EmbeddingGemma2EmbeddingModel`: real production binding for the
  `google/embeddinggemma-2` profile (Apache-2.0). Lazy-loads the
  pinned revision from the local Hugging Face cache, applies
  Matryoshka truncation to 512d, and formats query / document
  roles per the model's documented task prompts. Replaces the
  previous 'pinned-stub' placeholder.
- `qwen3_embedding_model.py` — `Qwen3EmbeddingModel`: real
  production binding for the `Qwen/Qwen3-Embedding-0.6B` profile
  (Apache-2.0), 1024d, with the same role-aware prompting
  contract as the EmbeddingGemma 2 binding.
- `embedding_model_factory.py` — the alias resolver that maps
  `gemma` / `qwen` / legacy aliases / `hashing` to a real
  `EmbeddingModelPort`. Production aliases MUST resolve to a real
  binding or the factory raises `EmbeddingModelError`; the
  hashing backend is permitted only under the `minimal` startup
  profile.

## Production runtime adapter (`pi_platform/adapters/runtime/`)

- `graph_expansion.py` — `ProductionGraphExpansion`: the §31
  production graph-expansion adapter that replaces the Phase 3
  `BoundedGraphExpansion` stub. Walks the Phase 3 `GraphPort`
  (NOT the ANN graph), enforces `hops` / `edge_types` / `budget`
  and applies the documented default edge-type set. The
  `expand()` surface is preserved so Phase 3 regression tests
  keep their binding.
- `usearch_dense_index.py` — `USearchDenseIndex`: the real USearch
  native package as the production dense backend. Persists the
  index across processes (atomic `.tmp` + `os.replace`),
  enforces profile-hash + source-generation compatibility on
  reopen, and rebuilds from the vector record store on a
  profile mismatch. Replaces the previous `usearch-stub`
  backend; the `is_real_usearch_available()` signal is what the
  release gate reads.

## Unified production composition

- `pi_platform/core/orchestration/retrieval_composition.py` —
  `build_production_retrieval_runtime()` is the single
  composition function the web UI, the MCP server, the CLI and
  the evaluation harness all call. The composition wires the
  embedding model (per profile), the dense + sparse + exact
  lookup ports, the hybrid reciprocal-rank merger, the metadata
  filter, the optional cross-encoder reranker, the production
  graph expansion, the context assembler, the multi-stage
  retrieval pipeline and the `SemanticIndexService` once. A
  `ProductionRetrievalRuntime` dataclass exposes every
  collaborator by name so callers can introspect the active
  backend without re-reading the composition source.
  Adding a new collaborator MUST happen here, not at the call
  site.

## CLI surface

The Phase 4 CLI subcommands report the active backend so operators
and agents can introspect the platform without reading source:

- `python -m pi_platform.cli embedding-status` — active embedding
  model, dimension, model version and license identifier.
- `python -m pi_platform.cli retrieval-status` — active fusion
  strategy, per-stage budgets, default graph-expansion edge types
  and adapter name.
- `python -m pi_platform.cli reranker-status` — active reranker
  family, budget and license identifier, cross-encoder and
  ColBERT-style availability.


## Benchmark repeatability

The benchmark compares repeated recall, precision, and MRR with an
absolute tolerance of 0.05. Median wall-clock latency is measured in
milliseconds and allows 50 ms of runner scheduling jitter. Latency
remains measured and compared separately from dimensionless quality
scores; the test does not require sub-millisecond timing stability.
