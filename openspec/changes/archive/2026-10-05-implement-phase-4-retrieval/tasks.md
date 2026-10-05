# Tasks — implement-phase-4-retrieval

This tasks file mirrors
[`openspec/changes/prepare-phase-4-retrieval/tasks.md`](../../prepare-phase-4-retrieval/tasks.md).
The Phase 4 tasks 70-78 are owned by this implementation change.
The eight Phase 4 capability specs under
[`openspec/changes/prepare-phase-4-retrieval/specs/`](../../prepare-phase-4-retrieval/specs/)
(and mirrored under [`specs/`](specs)) are the authoritative
behavioural contract.

The Phase 3 storage surface is the prerequisite. This change does
NOT modify the Phase 3 surface beyond replacing the
`graph_expansion.py` stub adapter with the production adapter.

## Phase 4 — Retrieval (tasks 70-78)

### 4.1 — EmbeddingModelPort (task 70)

- [ ] 70. Implement `platform.embeddings.EmbeddingModelPort`.
  See [`prepare-phase-4-retrieval/tasks.md`](../../prepare-phase-4-retrieval/tasks.md#41--embeddingmodelport-task-70)
  for the file map.

### 4.2 — HybridRetrieval (task 71)

- [ ] 71. Implement `platform.retrieval.HybridRetrieval`.

### 4.3 — MultiStageRetrieval pipeline (task 72)

- [ ] 72. Implement `platform.retrieval.MultiStageRetrieval`.

### 4.4 — GraphExpansion production (task 73)

- [ ] 73. Implement `platform.retrieval.GraphExpansion` production
  adapter.

### 4.5 — RerankerPort (task 74)

- [ ] 74. Implement pluggable advanced rerankers.

### 4.6 — MetadataFilter (task 75)

- [ ] 75. Implement metadata-driven filters.

### 4.7 — ContextAssembler (task 76)

- [ ] 76. Implement `platform.context.ContextAssembler`.

### 4.8 — Retrieval benchmark (task 77)

- [ ] 77. Add the `tests/test_retrieval_benchmark.py` evaluation
  fixture.

### 4.9 — Wiki maintenance and archive (task 78)

- [ ] 78. Update Wiki (new `modules/retrieval`,
  `modules/embeddings`, `modules/context-assembler`,
  `interfaces/hybrid-retrieval`, `interfaces/reranker`),
  `adr/0009-embedding-model-selection.md`, optional
  `adr/0010-hybrid-fusion-strategy.md`, archive this change under
  `archive/2026-10-04-implement-phase-4-retrieval/`, archive the
  preparation change under
  `archive/2026-10-04-prepare-phase-4-retrieval/`, update
  `openspec/CURRENT.md`, flip
  `plan-v0-8-platform-architecture/tasks.md` rows 70-78 to `[x]`.

Verification for the slice (tasks 77-78):

  - `python harness.py wiki-validate` MUST pass;
  - `python harness.py openspec-check` MUST pass;
  - `python harness.py check` MUST pass;
  - `openspec validate implement-phase-4-retrieval --type change
    --strict` MUST return `valid`;
  - the Phase 1 / Phase 2 / Phase 3 regression suites MUST
    remain green.

## Out-of-scope tasks (this change)

- Phase 5: orchestrator, local LLM, task context, capability
  discovery (tasks 79-83);
- Phase 6: MCP server (task 85);
- Phase 7+: control plane, security, distribution, A2A (tasks
  86-123).