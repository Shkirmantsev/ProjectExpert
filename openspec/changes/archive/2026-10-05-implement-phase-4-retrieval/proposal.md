# Proposal — Implement Phase 4 Retrieval Subsystem (tasks 70-78)

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the retrieval layer as the fourth implementation phase.
The Phase 4 capability specs authored by
[`openspec/changes/prepare-phase-4-retrieval/`](../../prepare-phase-4-retrieval/)
give the retrieval subsystem its authoritative behavioural
contract:

- `embedding-model` (§25, §5.4) — the multilingual,
  CPU-capable, replaceable embedding backend;
- `hybrid-retrieval` (§27, §28, §26, §33) — the composition port
  that fuses dense ANN, sparse BM25 and exact-identifier lookup;
- `multi-stage-retrieval` (§29, §33) — the seven-stage pipeline
  orchestrator;
- `graph-expansion-production` (§31) — the production adapter
  that replaces the Phase 3 stub adapter;
- `reranker-port` (§30) — the pluggable advanced reranker
  surface;
- `metadata-filters` (§24, §23, §56) — the temporal / version /
  security filter projection;
- `context-assembler` (§32) — the bounded-context bundle
  builder;
- `retrieval-benchmark` (§49) — the §49 evaluation fixture
  contract.

The Phase 3 storage subsystem
(`openspec/changes/archive/2026-10-05-implement-phase-3-storage/`)
supplies the `RuntimeStore`, `SparseIndex`, `DenseIndex`,
`FullTextIndex`, `GraphPort`, `GraphExpansionPort` (preview),
`ProvenancePort` / `KnowledgeState` and `FreshnessTracker` that
the Phase 4 retrieval layer composes. Without Phase 4
implementation, the platform cannot answer retrieval queries
through the §33 escalation policy, the §49 evaluation gates have
no retrieval benchmark to measure, and the Phase 5 orchestrator
and Phase 6 MCP server have no upstream contract to wire to.

This change ships the production code, registers the SPDX entries
in `distribution/licenses/dependency-inventory.json`, records the
§49 evaluation metrics and archives the preparation change as a
side effect. It depends on the eight Phase 4 capability specs being
accepted into `openspec/specs/2026-10-04-*/`.

## Goal

Implement the Phase 4 retrieval subsystem so that:

- `pi_platform.ports.retrieval.embedding_model.EmbeddingModelPort`
  exposes a multilingual, CPU-capable, replaceable embedding
  backend with a stdlib-only hashing fallback;
- `pi_platform.ports.retrieval.hybrid_retrieval.HybridRetrievalPort`
  composes the Phase 3 `DenseIndexPort`, `SparseIndexPort` and
  exact-identifier lookup behind a single ranked candidate set;
- `pi_platform.ports.retrieval.multi_stage_retrieval.MultiStageRetrievalPort`
  orchestrates the seven documented stages with explicit per-stage
  budgets and per-stage telemetry;
- `pi_platform.adapters.runtime.graph_expansion` replaces the
  Phase 3 stub adapter with the production adapter;
- `pi_platform.ports.retrieval.reranker.RerankerPort` exposes the
  cross-encoder default, the BM25-light fallback and the optional
  ColBERT-style adapter;
- `pi_platform.ports.retrieval.metadata_filter.MetadataFilterPort`
  enforces the §24 temporal rule, the project-version filter and
  the §56 security-classification filter;
- `pi_platform.ports.retrieval.context_assembler.ContextAssemblerPort`
  builds the bounded context bundle with deduplication, budget
  enforcement, citations, authoritative-evidence preference,
  conflict detection and uncertainty surfacing;
- `tests.test_retrieval_benchmark` records recall / precision /
  reranker quality / latency / cache reuse / branch-switch
  hydration time / stale-knowledge detection / plugin setup
  success rate against a fixed evaluation fixture.

What this change does:

- implements the ports, cores and adapters listed above;
- replaces the Phase 3 stub `graph_expansion.py` adapter with the
  production adapter;
- registers SPDX entries for the chosen embedding model,
  reranker and optional ColBERT-style runtime in
  `distribution/licenses/dependency-inventory.json`;
- ships the `tests/test_retrieval_benchmark.py` evaluation
  fixture;
- updates the Wiki, the glossary and the architecture overview
  with the Phase 4 module map;
- records the embedding-model selection in
  `adr/0009-embedding-model-selection.md` and the hybrid fusion
  strategy in the optional
  `adr/0010-hybrid-fusion-strategy.md`;
- updates `openspec/CURRENT.md` to add the eight Phase 4
  capabilities;
- flips `plan-v0-8-platform-architecture/tasks.md` rows 70-78
  from `[ ]` to `[x]`;
- archives this change under
  `openspec/changes/archive/2026-10-04-implement-phase-4-retrieval/`
  and the preparation change under
  `openspec/changes/archive/2026-10-04-prepare-phase-4-retrieval/`.

Out of scope:

- any Phase 5-10 capability (orchestration, MCP, control plane,
  security, distribution, A2A);
- any change to the Phase 3 surface beyond replacing the
  `graph-expansion` stub adapter with the production adapter.

## Affected capabilities

| Capability | Architecture sections | Phase 4 task | Status after archive |
|---|---|---|---|
| `embedding-model` | §25, §5.4 | 70 | accepted |
| `hybrid-retrieval` | §27, §28, §26, §33 | 71 | accepted |
| `multi-stage-retrieval` | §29, §33 | 72 | accepted |
| `graph-expansion-production` | §31 | 73 | accepted (closes Phase 3 preview port) |
| `reranker-port` | §30 | 74 | accepted |
| `metadata-filters` | §24, §23, §56 | 75 | accepted |
| `context-assembler` | §32 | 76 | accepted |
| `retrieval-benchmark` | §49 | 77 | accepted (evaluation fixture contract) |

The Phase 3 `graph-expansion` preview port remains accepted; this
change retires only the Phase 3 stub adapter that the production
adapter replaces.

Naming and adoption conventions:

- archive folder uses `archive/2026-10-04-implement-phase-4-retrieval/`
  (the future archive date; matches the Phase 1 / 2 / 3 archive
  convention);
- delta folders under `specs/` use the future first-acceptance
  date `2026-10-04-<capability>` matching the Phase 1 / 2 / 3
  convention.

## Compatibility / migration impact

This change ships production code. Compatibility notes:

- the Phase 1 `pi_platform.embedding.embedding_model.EmbeddingModel`
  stub is preserved for backward compatibility; the new
  `EmbeddingModel` default adapter implements the same
  `embed` / `embed_batch` / `dimension` / `model_version` surface;
- the Phase 3 `graph_expansion.py` stub adapter is replaced with
  the production adapter; the port surface is unchanged;
- `distribution/licenses/dependency-inventory.json` grows with the
  new embedding / reranker SPDX entries; `LicenseGate` MUST pass
  before the adapters are registered;
- `openspec/CURRENT.md` is updated to add the eight Phase 4
  capabilities under "Project product capabilities";
- `plan-v0-8-platform-architecture/tasks.md` rows 70-78 flip from
  `[ ]` to `[x]`;
- the Phase 1 / Phase 2 / Phase 3 regression suites MUST continue
  to pass byte-for-byte.

## Related knowledge

- `kb://architecture.platform-overview` — Phase 4 module map
  added by this change;
- `kb://glossary.platform` — Phase 4 vocabulary added by this
  change;
- `kb://adr.embedding-model-selection` — ADR authored by this
  change;
- `kb://adr.hybrid-fusion-strategy` — optional ADR authored by
  this change.