# Tasks — prepare-phase-4-retrieval

This tasks file mirrors the Phase 4 tasks 70-78 from the canonical
[`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md).
The tasks below are the future implementation work; they will be
executed by the future `implement-phase-4-retrieval` change. This
change ships zero production code.

The 8 Phase 4 capability specs under [`specs/`](specs) are the
authoritative behavioural contract for the implementation work.
The future change depends on the 8 specs being accepted into
`openspec/specs/2026-10-04-*/` before tasks 70-78 can be marked
`[x]`; until then they stay `[ ]` in both the plan change and the
future implementation change.

Verification commands referenced below:

- `python -m unittest tests.<module> -v` — focused regression
  tests;
- `openspec validate prepare-phase-4-retrieval --type change
  --strict` (this change), `openspec validate
  implement-phase-4-retrieval --type change --strict` (future
  change), `openspec validate --all --strict` (canonical harness
  check);
- `python harness.py check` — full harness core gate
  (license-gate, openspec-check, wiki-validate,
  artifact-manifest).

## Phase 4 — Retrieval (preparation only)

### 4.1 — EmbeddingModelPort (task 70)

- [ ] 70. Implement `platform.embeddings.EmbeddingModelPort` with
  multilingual default (DE / EN / UK; optional RU), CPU-capable,
  replaceable provider and a commercially-usable model + runtime
  license.
  → `pi_platform/ports/retrieval/embedding_model.py` (new port),
  `pi_platform/core/retrieval/embedding_model.py` (new core),
  `pi_platform/adapters/retrieval/embedding_model/multilingual_st.py`
  (new default adapter; `sentence-transformers` Apache-2.0 +
  `paraphrase-multilingual-MiniLM-L12-v2` Apache-2.0),
  `pi_platform/adapters/retrieval/embedding_model/hashing.py` (new
  stdlib-only fallback),
  `pi_platform/adapters/retrieval/embedding_model/gpu.py` (new
  optional GPU adapter).
  Verification:
  - `python -m unittest
    tests.test_platform_phase4.EmbeddingModelTests -v`
  - the Phase 1 `python harness.py license-gate` MUST pass with
    the new SPDX entries in
    `distribution/licenses/dependency-inventory.json`;
  - the `embedding-status` CLI MUST report the active backend
    and `model_version()`.

### 4.2 — HybridRetrieval (task 71)

- [ ] 71. Implement `platform.retrieval.HybridRetrieval` with
  dense ANN + sparse BM25 + exact identifier lookup behind a
  single port; identifier detection before vector search; replaceable
  fusion strategy (RRF default vs. linear weighted sum vs. learned
  fusion).
  → `pi_platform/ports/retrieval/hybrid_retrieval.py` (new port),
  `pi_platform/core/retrieval/hybrid_retrieval.py` (new core),
  `pi_platform/adapters/retrieval/hybrid_retrieval.py` (new
  composition adapter),
  `pi_platform/adapters/retrieval/identifier_query_detector.py`
  (new identifier detector).
  Verification:
  - `python -m unittest
    tests.test_platform_phase4.HybridRetrievalTests -v`
  - the Phase 3 `tests.test_platform_phase3.DenseIndexTests` and
    `tests.test_platform_phase3.SparseIndexTests` MUST continue
    to pass byte-for-byte;
  - `python -m pi_platform.cli retrieval-status` MUST exit zero
    and report the active fusion strategy.

### 4.3 — MultiStageRetrieval pipeline (task 72)

- [ ] 72. Implement `platform.retrieval.MultiStageRetrieval` with
  the seven documented stages (candidate generation → fusion →
  metadata / version / security filter → graph expansion →
  hierarchy expansion → rerank → context assembly), explicit
  per-stage budgets and per-stage telemetry.
  → `pi_platform/ports/retrieval/multi_stage_retrieval.py` (new
  port), `pi_platform/core/retrieval/multi_stage_retrieval.py`
  (new core).
  Verification:
  - `python -m unittest
    tests.test_platform_phase4.MultiStageRetrievalTests -v`
  - the per-stage telemetry MUST record `in`, `out`,
    `duration_ms` and `budget_exhausted` for every stage.

### 4.4 — GraphExpansion production (task 73)

- [ ] 73. Implement `platform.retrieval.GraphExpansion`
  production adapter (closes the Phase 3 `graph-expansion` preview
  port) with bounded hops, edge-type filter, default edge-type set
  and budget enforcement. The hierarchy-expansion stage of the
  multi-stage pipeline reuses the same adapter with
  `edge_types=["PART_OF"]`.
  → `pi_platform/adapters/runtime/graph_expansion.py` (new
  production adapter), replaces the Phase 3 stub adapter.
  Verification:
  - `python -m unittest
    tests.test_platform_phase4.GraphExpansionProductionTests -v`
  - the Phase 3 `tests.test_platform_phase3.GraphExpansionTests`
    MUST continue to pass byte-for-byte.

### 4.5 — RerankerPort (task 74)

- [ ] 74. Implement pluggable advanced rerankers (cross-encoder,
  ColBERT-style, multi-vector, BM25-light fallback) behind a
  `RerankerPort`. Operate only on bounded candidate sets.
  → `pi_platform/ports/retrieval/reranker.py` (new port),
  `pi_platform/adapters/retrieval/reranker/cross_encoder.py` (new
  default; `sentence-transformers` cross-encoder helpers +
  `cross-encoder/ms-marco-MiniLM-L-6-v2` MIT),
  `pi_platform/adapters/retrieval/reranker/bm25_light.py` (new
  stdlib-only fallback),
  `pi_platform/adapters/retrieval/reranker/colbert_style.py` (new
  optional ColBERT-style adapter; `pylate` or `colbert-ai` MIT).
  Verification:
  - `python -m unittest tests.test_platform_phase4.RerankerTests
    -v`
  - the Phase 1 license gate MUST pass with the new SPDX entries.

### 4.6 — MetadataFilter (task 75)

- [ ] 75. Implement metadata-driven temporal / version / security
  filters (`validFrom <= queryDate AND (validTo IS NULL OR validTo
  >= queryDate)`) and the deterministic drop-reason ordering.
  → `pi_platform/ports/retrieval/metadata_filter.py` (new port +
  value type), `pi_platform/core/retrieval/metadata_filter.py`
  (new core), `pi_platform/adapters/retrieval/metadata_filter.py`
  (new default adapter).
  Verification:
  - `python -m unittest
    tests.test_platform_phase4.MetadataFilterTests -v`

### 4.7 — ContextAssembler (task 76)

- [ ] 76. Implement `platform.context.ContextAssembler` with
  deduplication, context budget, citations, authoritative-evidence
  preference, conflict detection and uncertainty surfacing.
  → `pi_platform/ports/retrieval/context_assembler.py` (new port),
  `pi_platform/core/retrieval/context_assembler.py` (new core).
  Verification:
  - `python -m unittest
    tests.test_platform_phase4.ContextAssemblerTests -v`

### 4.8 — Retrieval benchmark / evaluation fixture (task 77)

- [ ] 77. Add evaluation fixtures and a retrieval benchmark test
  that records recall / precision, reranker quality, latency,
  cache reuse, branch-switch hydration time, stale-knowledge
  detection and plugin setup success rate.
  → `tests/test_retrieval_benchmark.py` (new benchmark suite).
  Verification:
  - `python -m unittest tests.test_retrieval_benchmark -v`
  - the aggregate metric MUST remain stable across two consecutive
    runs (no flaky ordering).

### 4.9 — Wiki maintenance, dependency-listing change, archive (task 78)

- [ ] 78. Update Wiki (new `modules/retrieval`, `modules/embeddings`,
  `modules/context-assembler`, `interfaces/hybrid-retrieval`,
  `interfaces/reranker`), archive the Phase 4 change, update
  `openspec/CURRENT.md`, record the embedding-model selection in
  `adr/0009-embedding-model-selection.md` and the optional fusion
  strategy in `adr/0010-hybrid-fusion-strategy.md`.
  → `.ai/wiki/modules/retrieval.md` (new),
  `.ai/wiki/modules/embeddings.md` (new),
  `.ai/wiki/modules/context-assembler.md` (new),
  `.ai/wiki/interfaces/hybrid-retrieval.md` (new),
  `.ai/wiki/interfaces/reranker.md` (new),
  `.ai/wiki/adr/0009-embedding-model-selection.md` (new),
  `.ai/wiki/adr/0010-hybrid-fusion-strategy.md` (new, optional),
  `.ai/wiki/architecture/platform-overview.md` (Phase 4 module
  map), `.ai/wiki/glossary/platform.md` (Phase 4 vocabulary),
  `.ai/wiki/INDEX.md` (new entries), `openspec/CURRENT.md` (the
  eight Phase 4 capabilities added), archive
  `implement-phase-4-retrieval` under
  `archive/2026-10-04-implement-phase-4-retrieval/`,
  `plan-v0-8-platform-architecture/tasks.md` (rows 70-78 flipped
  from `[ ]` to `[x]`).

Verification for the slice (tasks 77-78):

  - `python harness.py wiki-validate` MUST pass;
  - `python harness.py openspec-check` MUST pass;
  - `python harness.py check` MUST pass;
  - `openspec validate implement-phase-4-retrieval --type change
    --strict` MUST return `valid`.

## Out-of-scope tasks (this change)

The tasks below belong to later phases and are NOT executed by
the future `implement-phase-4-retrieval` change. They are listed
here only so the future implementation work knows where to draw
the line.

- the query orchestrator, local LLM, task context and capability
  discovery — Phase 5 tasks 79-83;
- the MCP server exposing the retrieval port — Phase 6 task 85;
- the control plane, security, distribution, A2A — Phase 7+
  tasks 86-123.

## Verification of this preparation change

- [ ] `python harness.py check` returns `Harness core checks:
  PASS`.
- [ ] `openspec validate prepare-phase-4-retrieval --type change
  --strict` returns `valid`.
- [ ] `python harness.py wiki-validate` returns `{"ok": true,
  ...}`.
- [ ] `python3 scripts/artifact_manifest.py verify` returns
  `Artifact manifest: PASS`.
- [ ] No production code under `pi_platform/ports/retrieval/`,
  `pi_platform/core/retrieval/`, `pi_platform/adapters/retrieval/`,
  `pi_platform/adapters/runtime/embedding_model/` or any related
  Phase 4 module is added by this change.
- [ ] The `plan-v0-8-platform-architecture/tasks.md` tasks 70-78
  are still `[ ]` (not flipped by this change).

## Preparation close-out

The proposal and all eight deltas were completed and validated
before implementation. Production execution of the checklist
above is tracked in `implement-phase-4-retrieval`; unchecked
production items here do not assert a second implementation.
Both changes are archived together, with preparation using
`--skip-specs` after implementation adoption.