# Proposal — Prepare the v0.8 Phase 4 Retrieval Capability Specs

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the retrieval layer as the fourth implementation phase:
eight behavioural capabilities (`embedding-model`,
`hybrid-retrieval`, `multi-stage-retrieval`,
`graph-expansion-production`, `reranker-port`, `metadata-filters`,
`context-assembler`, `retrieval-benchmark`) that turn the Phase 3
runtime store, indexes and sharded graph into the multilingual
hybrid-retrieval pipeline, the multi-stage orchestrated pipeline,
the production graph-expansion adapter, the pluggable reranker, the
metadata-driven filters, the context assembler and the evaluation
fixture that the §33 retrieval-first escalation policy requires.

The Phase 1 foundation
(`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`),
the Phase 2 ingestion subsystem
(`openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`)
and the Phase 3 storage subsystem
(`openspec/changes/archive/2026-10-05-implement-phase-3-storage/`)
are prerequisites. Phase 1 supplies the canonical value-type
catalogue, the SHA-256 content address, the Git-version-aware
runtime and the license gate; Phase 2 supplies the `PipelineDriver`,
the `SourceAdapter` family, the `Chunker`, the `ContextEnricher`
and the nine Phase 2 capability specs that emit the canonical
chunks and entity/relation records the Phase 3 runtime store hosts;
Phase 3 supplies the `RuntimeStore`, the `SparseIndex`, the
`DenseIndex`, the `FullTextIndex`, the canonical sharded
`GraphPort`, the `GraphExpansionPort` preview port, the
`ProvenancePort` / `KnowledgeState` and the `FreshnessTracker`
that the Phase 4 retrieval layer composes into the documented
pipeline.

Without Phase 4 specs there is no authoritative behavioural
contract for the embedding model, the hybrid retrieval composition,
the multi-stage pipeline, the production graph expansion, the
pluggable reranker, the metadata-driven filters, the context
assembler or the retrieval benchmark fixture. The §33
retrieval-first escalation policy has no formal contract to teach
agents; Phase 5's query orchestrator, Phase 6's MCP server and
Phase 7's control plane have no upstream contract to wire to; and
the §49 integration quality-gate evaluation suite has no
retrieval-benchmark fixture to record recall / precision /
latency / cache reuse.

This change resolves the gap by authoring the eight Phase 4
capability specs, the supporting design, context-impact and tasks,
while shipping zero production code. The implementation work ships
under a future `implement-phase-4-retrieval` change that depends on
the eight Phase 4 specs being accepted into
`openspec/specs/2026-10-04-*`. The
`openspec/changes/implement-phase-4-retrieval/` change folder is
created by this preparation change as a documented plan that
carries the same eight delta specs verbatim so the future
archive step promotes the same delta set into the canonical
specs directory.

## Goal

Author the Phase 4 capability specs and change artifacts so that a
later `implement-phase-4-retrieval` change can:

- fill in the Phase 1 placeholder `EmbeddingModelPort` with a real
  multilingual, CPU-capable, replaceable-provider embedding backend
  per the §25 requirements and the §5.4 model-license gate. The
  design candidate is **multilingual sentence-transformers
  (paraphrase-multilingual-MiniLM-L12-v2, Apache-2.0) on CPU** with
  an opt-in cross-encoder or ColBERT-style reranker, but the choice
  remains replaceable through the port so the enterprise-scale
  profile can substitute a different backend without changing the
  public contract;
- implement the `HybridRetrieval` composition port that fuses
  dense ANN, sparse BM25 and exact-identifier lookup into a single
  ranked candidate set per §27, the candidate-generation stage of
  §29 and the §33 retrieval-first escalation policy. The fusion
  strategy (RRF vs. linear weighted sum vs. learned fusion)
  remains configurable through
  `project-context.yaml:retrieval.fusion.strategy`;
- implement the `MultiStageRetrieval` orchestrator that runs the
  seven documented stages (candidate gen → fusion → metadata
  filter → graph expansion → hierarchy expansion → rerank →
  context assembly) with explicit per-stage budgets per §29;
- replace the Phase 3 `GraphExpansionPort` stub adapter with the
  production adapter (`pi_platform/adapters/runtime/graph_expansion.py`)
  that walks the canonical `GraphPort` and applies the
  documented `hops`, `edge_types` and `budget` parameters per §31;
- expose the `RerankerPort` (cross-encoder, ColBERT-style,
  multi-vector) that operates only on bounded candidate sets per
  §30;
- expose the `MetadataFilter` value type and `MetadataFilterPort`
  that enforce the §24 `validFrom <= queryDate AND (validTo IS
  NULL OR validTo >= queryDate)` rule, the §23 metadata
  correctness-projection rule, the project-version filter and the
  §56 security-classification filter;
- expose the `ContextAssemblerPort` that deduplicates, enforces the
  context budget, preserves citations, prefers authoritative evidence,
  detects conflicting hits and surfaces uncertainty per §32;
- ship the `tests/test_retrieval_benchmark.py` evaluation fixture
  that records recall / precision / reranker quality / latency /
  cache reuse / branch-switch hydration time / stale-knowledge
  detection / plugin setup success rate per §49.

What this change does:

- proposes the eight Phase 4 capability specs under
  `openspec/changes/prepare-phase-4-retrieval/specs/`;
- documents the technical design covering the
  `EmbeddingModelPort`, the `HybridRetrieval` composition port,
  the `MultiStageRetrieval` orchestrator, the production
  `GraphExpansion` adapter, the `RerankerPort`,
  `MetadataFilter` / `MetadataFilterPort`, the
  `ContextAssemblerPort` and the retrieval benchmark fixture;
- creates the `implement-phase-4-retrieval` change folder under
  `openspec/changes/implement-phase-4-retrieval/` and mirrors the
  eight delta specs verbatim so the future implementation archive
  carries the same delta set;
- lists the Wiki, ADR and context-impact nodes the future
  `implement-phase-4-retrieval` change will need to create or
  update;
- enumerates Phase 4 tasks 70-78 (mirroring
  [`plan-v0-8-platform-architecture/tasks.md`](../../changes/plan-v0-8-platform-architecture/tasks.md))
  with concrete verification commands so a contributor or AI agent
  can execute them deterministically.

Out of scope for this change:

- any production code under `pi_platform/ports/retrieval/`,
  `pi_platform/core/retrieval/`, `pi_platform/adapters/retrieval/`,
  `pi_platform/ports/runtime/embedding_model.py`,
  `pi_platform/adapters/runtime/embedding_model/` or any other
  Phase 4 module;
- any addition to the runtime dependency inventory (no embedding
  model, no reranker, no ColBERT-style runtime, no multi-vector
  library — those land in the future
  `implement-phase-4-retrieval` change after each SPDX-tracked
  license inventory entry passes `LicenseGate`);
- the query orchestrator, local LLM, task context and capability
  discovery — Phase 5 tasks 79-83;
- the MCP server exposing the retrieval ports — Phase 6 task 85;
- the Wiki materialisation, control plane, security, distribution,
  A2A — Phase 7+ tasks 86-123;
- archiving this change. The change stays active (proposal-only)
  until the future `implement-phase-4-retrieval` change uses it as
  prerequisite. The `plan-v0-8-platform-architecture` change remains
  the authoritative source for Phase 4-10 task ordering; tasks
  70-78 stay `[ ]`.

## Affected capabilities

This change introduces the following additive capability specs.
None of the five accepted Phase 1 specs, none of the nine accepted
Phase 2 specs and none of the nine accepted Phase 3 specs is
modified or retired. Phase 4 specs depend on the Phase 1 specs
(canonical schema, Git-version-aware runtime, repository layout,
license governance), the Phase 2 specs (content-addressed
processing, semantic-structural chunking, context enrichment) and
the Phase 3 specs (runtime store, sparse / dense / full-text
indexes, sharded graph, the Phase 3 `graph-expansion` preview port,
provenance / `KnowledgeState`, freshness tracking) but do not
alter their normative content.

| New capability | Architecture sections | Phase 4 task(s) | Spec delta path |
|---|---|---|---|
| `embedding-model` | §25, §5.4 | 70, 78 | [`specs/2026-10-04-embedding-model/spec.md`](specs/2026-10-04-embedding-model/spec.md) |
| `hybrid-retrieval` | §27, §28, §26, §33 | 71, 78 | [`specs/2026-10-04-hybrid-retrieval/spec.md`](specs/2026-10-04-hybrid-retrieval/spec.md) |
| `multi-stage-retrieval` | §29, §33 | 72, 78 | [`specs/2026-10-04-multi-stage-retrieval/spec.md`](specs/2026-10-04-multi-stage-retrieval/spec.md) |
| `graph-expansion-production` | §31, §29 | 73, 78 | [`specs/2026-10-04-graph-expansion-production/spec.md`](specs/2026-10-04-graph-expansion-production/spec.md) |
| `reranker-port` | §30 | 74, 78 | [`specs/2026-10-04-reranker-port/spec.md`](specs/2026-10-04-reranker-port/spec.md) |
| `metadata-filters` | §24, §23, §56 | 75, 78 | [`specs/2026-10-04-metadata-filters/spec.md`](specs/2026-10-04-metadata-filters/spec.md) |
| `context-assembler` | §32 | 76, 78 | [`specs/2026-10-04-context-assembler/spec.md`](specs/2026-10-04-context-assembler/spec.md) |
| `retrieval-benchmark` | §49, §70 | 77, 78 | [`specs/2026-10-04-retrieval-benchmark/spec.md`](specs/2026-10-04-retrieval-benchmark/spec.md) |

Note on count: this change produces eight capability specs that
cover tasks 70-77. Task 78 (Wiki maintenance) is the
`implement-phase-4-retrieval` close-out task and does not require
its own capability spec; its wiki and ADR outputs are documented in
[`context-impact.md`](context-impact.md) so the future archive step
can flip the plan row from `[ ]` to `[x]`.

The eight specs cover Phase 4 tasks 70-77 from
[`plan-v0-8-platform-architecture/tasks.md`](../../changes/plan-v0-8-platform-architecture/tasks.md).
Tasks 70-78 remain `[ ]` in the plan change after this change is
archived; they will be flipped to `[x]` by the future
`implement-phase-4-retrieval` change when it lands.

Cross-phase task responsibility:

- the embedding-model selection (task 70) is owned by Phase 4 but
  the chosen model remains replaceable through the
  `EmbeddingModelPort` so the enterprise-scale profile can
  substitute a different model without changing the public
  contract;
- the `HybridRetrieval` (task 71) exposes a composition port that
  the Phase 5 orchestrator (task 79) wires into the `Level 0 /
  Level 1 / Level 2` delegation policy;
- the `MultiStageRetrieval` (task 72) consumes the Phase 4 ports
  and exposes the per-stage telemetry that the
  `retrieval-benchmark` (task 77) consumes;
- the `graph-expansion-production` (task 73) replaces the Phase 3
  stub adapter with the production adapter; the Phase 3
  `graph-expansion` preview capability remains accepted;
- the `RerankerPort` (task 74) and `MetadataFilter` (task 75) are
  consumed by the multi-stage pipeline and by the Phase 5
  orchestrator;
- the `ContextAssemblerPort` (task 76) produces the bounded
  context bundle that the Phase 5 `TaskContextBuilder` consumes;
- the `retrieval-benchmark` (task 77) is the §49 evaluation
  fixture that the Phase 7 quality-gate (task 119) consumes.

Naming and adoption conventions (per
[`openspec/config.yaml`](../../config.yaml) and
[`openspec/README.md`](../../README.md)):

- active change IDs are undated semantic kebab-case
  (`prepare-phase-4-retrieval`);
- delta folders under `specs/` use the future first-acceptance
  date (`2026-10-04-<capability>`);
- `openspec/CURRENT.md` is updated by the future
  `implement-phase-4-retrieval` change when the eight Phase 4
  specs are adopted, not by this change.

## Compatibility / migration impact

This change is a pure planning artifact. It adds:

- one new active change directory at
  `openspec/changes/prepare-phase-4-retrieval/`;
- eight new spec deltas under
  `openspec/changes/prepare-phase-4-retrieval/specs/2026-10-04-*/`;
- one new active change directory at
  `openspec/changes/implement-phase-4-retrieval/`;
- eight mirrored spec deltas under
  `openspec/changes/implement-phase-4-retrieval/specs/2026-10-04-*/`.

It does not:

- modify any accepted Phase 1 capability spec under
  `openspec/specs/2026-10-04-*/`;
- modify any accepted Phase 2 capability spec under
  `openspec/specs/2026-10-04-*/`;
- modify any accepted Phase 3 capability spec under
  `openspec/specs/2026-10-04-*/`;
- modify `openspec/CURRENT.md`, the harness, the license inventory
  or the regression suite;
- introduce any source code, dependency or runtime configuration;
- rename any existing capability, port or adapter;
- alter the `plan-v0-8-platform-architecture` change
  (`tasks.md` still lists tasks 70-78 as `[ ]`).

Language and dependency decisions:

- the Python 3.11 platform source language decision recorded in
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  still holds. No new language dependency is being introduced by
  this change. The future `implement-phase-4-retrieval` change
  MAY add one sentence-transformers Python package (e.g.
  `sentence-transformers` Apache-2.0), one optional
  cross-encoder / ColBERT-style runtime (e.g. a CPU-capable
  `cross-encoder` MIT or `colbert-ai` MIT) and one BM25 reranker
  fallback — but only after each SPDX-tracked license inventory
  entry passes `LicenseGate`. The Python-only default ports in
  `pi_platform/ports/retrieval/` stay language-neutral; the
  embedding / reranker engines are supplied as adapters under
  `pi_platform/adapters/retrieval/`;
- no change to the licence-governance defaults. Any new dependency
  must be SPDX-tracked and pass `LicenseGate` before it lands in
  `distribution/licenses/dependency-inventory.json`. The candidate
  retrieval libraries are documented as review-required paths in
  the [`design.md`](design.md) so the future
  `embedding-model-selection` ADR (ADR 0009) and the optional
  `hybrid-fusion-strategy` ADR (ADR 0010) carry the documented
  rationale.

OpenSpec CLI conventions:

- the change folder uses lowercase kebab-case without a date
  prefix (`prepare-phase-4-retrieval`) per
  [`openspec/config.yaml`](../../config.yaml);
- the eight spec deltas are dated with the future acceptance date
  `2026-10-04` matching the Phase 1 / 2 / 3 archive conventions;
  the archive step for the future `implement-phase-4-retrieval`
  change will produce
  `archive/2026-10-04-implement-phase-4-retrieval/` and rename
  the delta folders to drop the date prefix in the change-root
  view;
- no production code, license inventory entry or harness command
  is touched.

## Related knowledge

- `kb://architecture.platform-overview` — Phase 1/2/3 Wiki node;
  will be updated by the future `implement-phase-4-retrieval`
  change to add the Phase 4 module map
  (`retrieval/`, `ports/retrieval/`, `adapters/retrieval/`).
- `kb://architecture.system-overview` — cross-cutting view; will
  gain a Phase 4 module map row.
- `kb://glossary.platform` — Phase 1 / 2 / 3 platform vocabulary;
  the future change adds `EmbeddingModelPort`,
  `HybridRetrieval`, `MultiStageRetrieval`,
  `GraphExpansion` (production), `RerankerPort`,
  `MetadataFilter`, `ContextAssembler`, `RetrievalBenchmark`.
- `kb://glossary.domain` — cross-links to the platform
  vocabulary.
- `kb://project.implementation-roadmap` — links to Phase 4 entry.
- `kb://project.project-map` — Phase 4 module map placeholder.
- `kb://adr.platform-source-language` — Python 3.11 holds; the
  embedding / reranker engines stay under
  `pi_platform/adapters/retrieval/`.
- `kb://adr.canonical-runtime-separation` — Phase 4 specs respect
  invariants #1-#4 and the canonical / runtime boundary; the
  multi-stage retrieval pipeline does not invent a new runtime
  store but composes the Phase 3 storage layer.
- `kb://adr.license-governance-default` — every Phase 4
  dependency (embedding model, reranker, optional cross-encoder
  runtime, optional BM25 reranker fallback) requires an
  SPDX-tracked inventory entry.
- `kb://adr.embedded-storage-selection` — Phase 3 ADR that
  documents the storage backend Phase 4 composes against.
- future `kb://adr.embedding-model-selection` — embedding model
  selection (the design candidate is multilingual
  sentence-transformers on CPU with Apache-2.0; rejected
  alternatives include non-multilingual BERT variants,
  non-Apache / non-MIT model licenses, GPU-only models).
- future optional `kb://adr.hybrid-fusion-strategy` — RRF vs.
  linear vs. learned fusion (the design candidate is reciprocal
  rank fusion (RRF) for the default; rejected alternatives
  include learned fusion without labelled training data and
  linear weighted sum without per-corpus calibration).
- future `kb://modules.retrieval`, `kb://modules.embeddings`,
  `kb://modules.context-assembler` — Wiki module maps for the
  Phase 4 surface.
- future `kb://interfaces.hybrid-retrieval`,
  `kb://interfaces.reranker` — Wiki interface nodes.
- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §17, §23, §24, §25, §26, §27, §28, §29, §30, §31, §32, §33,
  §49, §52, §56 — every cited section is authoritative for the
  Phase 4 capability contracts.