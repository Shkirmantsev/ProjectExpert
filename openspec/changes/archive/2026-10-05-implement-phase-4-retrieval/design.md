# Design — implement-phase-4-retrieval

The technical design lives in
[`openspec/changes/prepare-phase-4-retrieval/design.md`](../../prepare-phase-4-retrieval/design.md).
This file is a thin reference so the implementation change carries
its own design section.

## Phase 4 module map

- `pi_platform/core/retrieval/` — new core subpackage;
- `pi_platform/ports/retrieval/` — new ports subpackage;
- `pi_platform/adapters/retrieval/` — new default adapters;
- `pi_platform/adapters/runtime/graph_expansion.py` — new
  production adapter that replaces the Phase 3 stub.

## Port surfaces (summary)

- `EmbeddingModelPort` — `embed`, `embed_batch`, `dimension`,
  `model_version`, `license_id`, `stats`;
- `HybridRetrievalPort` — `query`, `exact_id`, `stats`;
- `MultiStageRetrievalPort` — `retrieve(RetrievalQuery) ->
  RetrievalResult`;
- `RerankerPort` — `rerank`, `score`, `model_version`,
  `license_id`, `stats`;
- `MetadataFilterPort` — `apply`, `validate`;
- `ContextAssemblerPort` — `assemble(hits, *, contextBudget,
  query) -> ContextBundle`.

## Default adapters (summary)

- `MultilingualSentenceTransformerEmbeddingModel` — default
  CPU-capable multilingual adapter (`sentence-transformers`
  Apache-2.0 + `paraphrase-multilingual-MiniLM-L12-v2`
  Apache-2.0);
- `HashingEmbeddingModel` — stdlib-only hashing fallback;
- `HybridRetrieval` — composition adapter with reciprocal rank
  fusion (RRF) default;
- `IdentifierQueryDetector` — regex-based identifier detector
  routing to exact lookup;
- `CrossEncoderReranker` — cross-encoder default
  (`cross-encoder/ms-marco-MiniLM-L-6-v2` MIT);
- `Bm25LightReranker` — stdlib-only BM25 fallback;
- `ColBertStyleReranker` — optional ColBERT-style adapter;
- `MetadataFilterAdapter` — default metadata filter adapter;
- `ContextAssemblerAdapter` — default context assembler adapter;
- `graph_expansion.ProductionGraphExpansion` — production
  adapter that replaces the Phase 3 stub.

## Per-stage budgets (multi-stage pipeline)

| Stage | Default budget |
|---|---|
| candidate generation | 50 candidates |
| fusion | 50 candidates |
| metadata filter | 40 candidates |
| graph expansion | 30 entities |
| hierarchy expansion | 30 entities |
| rerank (when enabled) | 20 candidates |
| context assembly | `contextBudget` |

## Risks and mitigations

See [`openspec/changes/prepare-phase-4-retrieval/design.md`](../../prepare-phase-4-retrieval/design.md#risks-and-mitigations)
for the full risk matrix.