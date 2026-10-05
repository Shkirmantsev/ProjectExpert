# Context impact — prepare-phase-4-retrieval

## Knowledge to create

The Wiki nodes below are NOT created by this change; they are
listed as future work the `implement-phase-4-retrieval` change
must perform when it ships the production code.

- `.ai/wiki/modules/retrieval.md` — the Phase 4 retrieval module
  map (`pi_platform/core/retrieval/`,
  `pi_platform/ports/retrieval/`, `pi_platform/adapters/retrieval/`,
  plus the Phase 1 `pi_platform/embedding/embedding_model.py` stub
  that Phase 4 replaces for the public contract).
  `kind: modules`, `status: draft`.
- `.ai/wiki/modules/embeddings.md` — the Phase 4 embedding-model
  module map (`pi_platform/core/retrieval/embedding_model.py`,
  `pi_platform/ports/retrieval/embedding_model.py`,
  `pi_platform/adapters/retrieval/embedding_model/`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/modules/context-assembler.md` — the Phase 4
  context-assembler module map
  (`pi_platform/core/retrieval/context_assembler.py`,
  `pi_platform/ports/retrieval/context_assembler.py`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/interfaces/hybrid-retrieval.md` — the
  `HybridRetrievalPort` port contract, the candidate-generation
  + exact-identifier routing and the fusion-strategy pluggability.
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/reranker.md` — the `RerankerPort` port
  contract, the cross-encoder default, the BM25-light fallback and
  the optional ColBERT-style adapter.
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/adr/0009-embedding-model-selection.md` — ADR slot for
  the embedding-model selection. The design candidate is
  **multilingual sentence-transformers** (Apache-2.0 model +
  Apache-2.0 runtime) on CPU with a stdlib-only hashing fallback;
  rejected alternatives include non-multilingual BERT variants,
  non-Apache / non-MIT model licenses and GPU-only models.
  `kind: adr`, `status: proposed`.
- `.ai/wiki/adr/0010-hybrid-fusion-strategy.md` — ADR slot for
  the hybrid fusion strategy. The design candidate is
  **reciprocal rank fusion (RRF)** with `dense_weight=0.5`,
  `sparse_weight=0.5` defaults; rejected alternatives include
  learned fusion (no labelled training data) and linear weighted
  sum (score-distribution-sensitive).
  `kind: adr`, `status: proposed` (optional).

## Knowledge to update

The Wiki updates below are NOT performed by this change; they are
listed as future work the `implement-phase-4-retrieval` change
must perform alongside the production code.

- `.ai/wiki/architecture/platform-overview.md` — extend the Phase
  1 / 2 / 3 module map with the Phase 4 module map
  (`retrieval/`, `ports/retrieval`, `adapters/retrieval`).
  Reference the new `modules/retrieval.md`,
  `modules/embeddings.md` and `modules/context-assembler.md`
  nodes.
- `.ai/wiki/architecture/system-overview.md` — extend the
  "Principal components" section with the Phase 4 retrieval
  reference and links to the new module / interface nodes.
- `.ai/wiki/glossary/platform.md` — add Phase 4 vocabulary
  entries: `EmbeddingModelPort`, `HybridRetrieval`,
  `MultiStageRetrieval`, `RerankerPort`, `MetadataFilter`,
  `ContextAssembler`, `RetrievalBenchmark`, `ContextBundle`,
  `RetrievalQuery`, `RetrievalHit`, `RetrievalResult`. Status
  flips from `draft` to `active` once the implementation lands.
- `.ai/wiki/glossary/domain.md` — cross-link to the platform
  vocabulary for the new entries.
- `.ai/wiki/project/project-map.md` — add the new module folders
  under "Main source areas" with status `planned` until the
  implementation change lands; flip to `active` once the code
  is on disk.
- `.ai/wiki/project/implementation-roadmap.md` — add the Phase 4
  row to the phase table (currently Phase 1 + Phase 2 + Phase 3
  are marked complete; Phase 4 will be marked `in-progress` by
  the future implementation change and `complete` when its
  archive lands).
- `.ai/wiki/INDEX.md` — add the new Wiki modules, interfaces and
  ADRs once they exist on disk; the future implementation change
  is responsible for the index update.
- `openspec/CURRENT.md` — add the eight Phase 4 capabilities
  once the future `implement-phase-4-retrieval` change is
  archived; this change does NOT modify `openspec/CURRENT.md`.

## Knowledge to review for staleness

- `.ai/wiki/architecture/platform-overview.md` — review the
  Phase 1 / 2 / 3 module map and ensure the Phase 4 extensions
  remain additive; the existing Phase 1 boundary
  (`core/{canonical,git,sync,licensing}` + `ports` +
  `adapters/{fs,git}`) MUST stay unchanged.
- `.ai/wiki/architecture/system-overview.md` — review the
  "Principal components" section to confirm the Phase 4
  retrieval reference does not contradict the existing canonical
  / runtime boundary.
- `.ai/wiki/glossary/platform.md` — review the Phase 1 / 2 / 3
  vocabulary; Phase 4 adds new entries
  (`EmbeddingModelPort`, `HybridRetrieval`,
  `MultiStageRetrieval`, `RerankerPort`, `MetadataFilter`,
  `ContextAssembler`, `RetrievalBenchmark`, `ContextBundle`,
  `RetrievalQuery`, `RetrievalHit`, `RetrievalResult`). The
  existing `PipelineDriver`, `SourceAdapter`, `Chunker`,
  `ContextEnricher`, `LocalSourceInboxScanner`,
  `RuntimeStore`, `SparseIndex`, `DenseIndex`,
  `FullTextIndex`, `Graph`, `GraphExpansion` (Phase 3 preview),
  `KnowledgeState`, `FreshnessTracker` entries remain unchanged.
  The Phase 4 species are documented as Phase 4 additions,
  never as redefinitions of Phase 1 / Phase 2 / Phase 3 terms.
- `.ai/wiki/adr/0005-platform-source-language.md` — review the
  Python 3.11 decision and confirm the Phase 4 retrieval
  libraries land as adapters under
  `pi_platform/adapters/retrieval/` rather than as new
  platform-level language dependencies. The ADR is unchanged in
  this change; the future implementation change adds the
  embedding / reranker libraries without modifying the ADR text.
- `.ai/wiki/adr/0002-canonical-runtime-separation.md` — review
  the canonical / runtime separation invariants; the Phase 4
  retrieval layer respects invariants #1-#4 by composing the
  Phase 3 runtime store, indexes and graph without inventing a
  new runtime store.
- `.ai/wiki/adr/0008-embedded-storage-selection.md` (Phase 3
  ADR) — review the storage-backend selection and confirm the
  Phase 4 retrieval layer composes the chosen storage engine
  through the Phase 3 `RuntimeStorePort`, `SparseIndexPort`,
  `DenseIndexPort`, `GraphPort` and `GraphExpansionPort`
  without bypassing them.

## Affected implementation

Modules/paths the future `implement-phase-4-retrieval` change will
populate (NOT populated by this change):

- `pi_platform/core/retrieval/` — new core subpackage for
  `EmbeddingModel`, `HybridRetrieval`, `MultiStageRetrieval`,
  `Reranker`, `MetadataFilter`, `ContextAssembler`
  implementations;
- `pi_platform/ports/retrieval/` — new ports subpackage for
  `EmbeddingModelPort`, `HybridRetrievalPort`,
  `MultiStageRetrievalPort`, `RerankerPort`, `MetadataFilterPort`,
  `MetadataFilter`, `ContextAssemblerPort`, `RetrievalQuery`,
  `RetrievalResult`, `RetrievalHit`, `ContextBundle`,
  `ContextBudget`;
- `pi_platform/adapters/retrieval/` — new default adapters
  (`MultilingualSentenceTransformerEmbeddingModel`,
  `HashingEmbeddingModel`, `GpuEmbeddingModel`,
  `HybridRetrieval`, `IdentifierQueryDetector`,
  `CrossEncoderReranker`, `Bm25LightReranker`,
  `ColBertStyleReranker`, `MetadataFilterAdapter`,
  `ContextAssemblerAdapter`);
- `pi_platform/adapters/runtime/graph_expansion.py` — new
  production adapter that replaces the Phase 3 stub adapter;
- `pi_platform/embedding/embedding_model.py` — Phase 1 stub
  preserved for backward compatibility; the
  `EmbeddingModel` default adapter implements the same
  `embed` / `embed_batch` / `dimension` / `model_version`
  surface;
- `tests/test_retrieval_benchmark.py` — new Phase 4 evaluation
  fixture;
- `distribution/licenses/dependency-inventory.json` — new SPDX
  entries for the chosen embedding model and runtime
  (`sentence-transformers` Apache-2.0,
  `paraphrase-multilingual-MiniLM-L12-v2` Apache-2.0), the
  reranker (`sentence-transformers` cross-encoder helpers +
  `cross-encoder/ms-marco-MiniLM-L-6-v2` MIT) and the optional
  ColBERT-style runtime (`pylate` or `colbert-ai` MIT);
- `Containerfile` — install steps for the new Python packages;
- `pi_platform/cli/main.py` — extends with `retrieval-status`,
  `embedding-status`, `reranker-status` subcommands.

Primary symbols/interfaces the future change will introduce (NOT
introduced by this change):

- `pi_platform.ports.retrieval.embedding_model.EmbeddingModelPort`,
  `EmbeddingStats`;
- `pi_platform.ports.retrieval.hybrid_retrieval.HybridRetrievalPort`,
  `FusionStrategy`;
- `pi_platform.ports.retrieval.multi_stage_retrieval.MultiStageRetrievalPort`,
  `StageReport`;
- `pi_platform.ports.retrieval.reranker.RerankerPort`,
  `RerankerFamily`;
- `pi_platform.ports.retrieval.metadata_filter.MetadataFilterPort`,
  `MetadataFilter`;
- `pi_platform.ports.retrieval.context_assembler.ContextAssemblerPort`,
  `ContextBundle`, `ContextBudget`, `Citation`;
- `pi_platform.ports.retrieval.shared.RetrievalQuery`,
  `RetrievalHit`, `RetrievalResult`.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md` —
  remains accepted and unaffected. Phase 4 keeps harness core
  skills separated from the Phase 7 agent integration packaging
  work.
- `adr/0002-canonical-runtime-separation.md` — remains accepted and
  unaffected. Phase 4 respects invariants #1-#4 by composing the
  Phase 3 storage layer through the documented ports without
  inventing a new runtime store.
- `adr/0003-license-governance-default.md` — remains accepted and
  unaffected. Every Phase 4 dependency (embedding model,
  reranker, optional cross-encoder runtime, optional ColBERT-style
  runtime) requires an SPDX-tracked inventory entry that passes
  `LicenseGate` before the adapter is registered.
- `adr/0004-ports-and-adapters-extension-style.md` — remains
  accepted and unaffected. Phase 4 adds ports under
  `pi_platform/ports/retrieval/` and adapters under
  `pi_platform/adapters/retrieval/`.
- `adr/0005-platform-source-language.md` — remains accepted and
  unaffected. Phase 4 keeps the Python 3.11 default; the
  embedding / reranker libraries are invoked as adapters under
  `pi_platform/adapters/retrieval/` rather than as new
  platform-level language dependencies.
- `adr/0006-phase-2-parser-selection.md` — remains accepted and
  unaffected. The Phase 4 retrieval surface is independent of the
  Java parser library.
- `adr/0007-phase-2-inbox-policy-default.md` — remains accepted and
  unaffected. The Phase 4 retrieval surface is independent of the
  inbox policy.
- `adr/0008-embedded-storage-selection.md` — remains accepted and
  unaffected. Phase 4 composes the chosen storage backend through
  the Phase 3 ports without bypassing them.
- future `adr/0009-embedding-model-selection.md` — to be authored
  by the future implementation change; documents the
  **multilingual sentence-transformers** (Apache-2.0) on CPU
  choice and the rejected alternatives (non-multilingual BERT
  variants, non-Apache / non-MIT model licenses, GPU-only models).
- future `adr/0010-hybrid-fusion-strategy.md` — to be authored
  by the future implementation change; documents the
  **reciprocal rank fusion (RRF)** default and the rejected
  alternatives (linear weighted sum, learned fusion).

## Acceptance criteria

- [x] Relevant Wiki pages reflect planned/shipped implementation.
  All updates above are additive and link back to the v0.8
  architecture baseline. The future implementation change
  performs the on-disk Wiki edits.
- [x] Generated local context index was refreshed. The Phase 2 /
  Phase 3 `python harness.py wiki-init` already produced the
  local FTS index. The future implementation change will re-run
  `python harness.py wiki-init` after the Phase 4 Wiki edits
  land.
- [x] Links and stable knowledge IDs validate. The new Wiki
  pages will use stable `id` frontmatter values (see Knowledge
  to create above) so that `kb_validate` succeeds.
- [x] Spec/implementation mismatches are resolved or explicitly
  documented. There is no implementation in this change; the
  eight Phase 4 specs describe the planned platform behaviour
  against the v0.8 baseline with no conflict. The cross-phase
  task responsibility matrix in `proposal.md` records the
  explicit ownership split between Phase 4 and the later
  phases.