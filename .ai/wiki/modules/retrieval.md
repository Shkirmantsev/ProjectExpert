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
  - openspec/specs/2026-10-04-embedding-model/spec.md
  - openspec/specs/2026-10-04-hybrid-retrieval/spec.md
  - openspec/specs/2026-10-04-multi-stage-retrieval/spec.md
  - openspec/specs/2026-10-04-graph-expansion-production/spec.md
  - openspec/specs/2026-10-04-reranker-port/spec.md
  - openspec/specs/2026-10-04-metadata-filters/spec.md
  - openspec/specs/2026-10-04-context-assembler/spec.md
  - openspec/specs/2026-10-04-retrieval-benchmark/spec.md
maintenance:
  mode: authored
related:
  - interfaces.hybrid-retrieval
  - interfaces.reranker
  - modules.embeddings
  - modules.context-assembler
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

## Production runtime adapter (`pi_platform/adapters/runtime/`)

- `graph_expansion.py` — `ProductionGraphExpansion`: the §31
  production graph-expansion adapter that replaces the Phase 3
  `BoundedGraphExpansion` stub. Walks the Phase 3 `GraphPort`
  (NOT the ANN graph), enforces `hops` / `edge_types` / `budget`
  and applies the documented default edge-type set. The
  `expand()` surface is preserved so Phase 3 regression tests
  keep their binding.

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
