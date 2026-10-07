# Proposal — Prepare the v0.8 Phase 5 Orchestration Capability Specs

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the orchestration layer as the fifth implementation
phase: five behavioural capabilities (`query-orchestrator`,
`local-llm-port`, `task-context-builder`, `capability-discovery`,
`retrieval-first-policy`) that turn the Phase 4 retrieval
subsystem and the §33 retrieval-first escalation policy into
the §34 three-level query orchestrator, the §35 optional
local LLM, the §52 bounded task context bundle, the §47
deterministic capability discovery and the §33 / §49
retrieval-first policy regression contract.

The Phase 1 foundation
(`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`),
Phase 2 ingestion
(`openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`),
Phase 3 storage
(`openspec/changes/archive/2026-10-05-implement-phase-3-storage/`)
and Phase 4 retrieval
(`openspec/changes/archive/2026-10-05-implement-phase-4-retrieval/`)
are prerequisites. Phase 1 supplies the canonical
`TaskContext` value type, the SHA-256 content address, the
Git-version-aware runtime, the bidirectional sync and the
license gate; Phase 2 supplies the `PipelineDriver`, the
`SourceAdapter` family, the `Chunker`, the `ContextEnricher`
and the nine Phase 2 capability specs that emit the canonical
chunks and entity / relation records; Phase 3 supplies the
`RuntimeStore`, the three indexes, the canonical sharded
`GraphPort`, the `GraphExpansionPort` production adapter, the
`ProvenancePort` / `KnowledgeState` and the `FreshnessTracker`;
Phase 4 supplies the `MultiStageRetrievalPort` and the
`ContextAssemblerPort` that the Phase 5 orchestrator composes
for L0 / L1 / L2 escalation.

Without Phase 5 specs there is no authoritative behavioural
contract for the three-level query orchestrator, the optional
local LLM, the §52 task context bundle, the §47 capability
discovery or the §33 / §49 retrieval-first policy regression
test. Phase 6's MCP server has no orchestrator to expose;
Phase 7's control plane has no capability descriptor to
publish; Phase 10's A2A delegation has no task context bundle
to forward.

This change resolves the gap by authoring the five Phase 5
capability specs, the supporting design, context-impact and
tasks, while shipping zero production code. The implementation
work ships under a future `implement-phase-5-orchestration`
change that depends on the five Phase 5 specs being accepted
into `openspec/specs/2026-10-05-*/`. The
`openspec/changes/implement-phase-5-orchestration/` change
folder is created by this preparation change as a documented
plan that carries the same five delta specs verbatim so the
future archive step promotes the same delta set into the
canonical specs directory.

## Goal

Author the Phase 5 capability specs and change artifacts so
that a later `implement-phase-5-orchestration` change can:

- fill in the Phase 5 placeholder `QueryOrchestratorPort`
  with a deterministic three-level (L0 direct retrieval,
  L1 retrieval + small local LLM, L2 strong external agent)
  orchestrator that composes the Phase 4
  `MultiStageRetrievalPort` per the §33 retrieval-first
  escalation policy. The design candidate is a
  level-selection heuristic that defaults to L0 and
  escalates to L1 / L2 only on demand, but the heuristic
  remains config-driven through
  `project-context.yaml:orchestrator.level_selection`.
- implement the `LocalLLMPort` behind a stable interface
  with a deterministic stub default that ships in the
  default container. The active LLM family is
  configurable through
  `project-context.yaml:orchestrator.local_llm.family`;
  the documented opt-in families are `stub` (default),
  `llama-cpp`, `transformers` and `external-llm`. The
  default container ships with the stub only; the LLM
  capability is reported as `localLlm: false` in the §47
  capability descriptor.
- implement the `TaskContextBuilderPort` that produces the
  bounded §52 task context bundle (requirement, openSpec,
  wikiSections, sourceCode, interfaces, dependencies,
  architectureConstraints, graphNeighbourhood, tests,
  gitDiff) with priority-based budget truncation.
- implement the `CapabilityDiscoveryPort` that returns the
  deterministic §47 capability descriptor (serverVersion,
  mcpApiVersion, knowledgeSchemaVersion, okfVersions,
  features.{hybridRetrieval, graphExpansion, okf,
  materialization, a2a, localLlm}). The descriptor is the
  source of truth the Phase 6 MCP `describe_capabilities`
  tool exposes.
- ship the `tests/test_orchestration_policy.py` regression
  test that asserts the §33 retrieval-first policy
  compliance: implementation questions do not trigger
  broad source scanning before retrieval; the
  `retrieval_first_violations` counter is `0` for the
  documented compliant query set; L0 / L1 / L2 paths all
  run retrieval first.

What this change does:

- proposes the five Phase 5 capability specs under
  `openspec/changes/prepare-phase-5-orchestration/specs/`;
- documents the technical design covering the
  `QueryOrchestratorPort`, `LocalLLMPort`,
  `TaskContextBuilderPort`, `CapabilityDiscoveryPort` and the
  retrieval-first policy test;
- creates the `implement-phase-5-orchestration` change folder
  under `openspec/changes/implement-phase-5-orchestration/`
  and mirrors the five delta specs verbatim so the future
  implementation archive carries the same delta set;
- lists the Wiki, ADR and context-impact nodes the future
  `implement-phase-5-orchestration` change will need to
  create or update;
- enumerates Phase 5 tasks 79-84 (mirroring
  [`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md))
  with concrete verification commands.

Out of scope for this change:

- any production code under
  `pi_platform/ports/orchestration/`,
  `pi_platform/core/orchestration/`,
  `pi_platform/adapters/orchestration/` or any related
  Phase 5 module;
- any addition to the runtime dependency inventory (the
  default stub `LocalLLMPort` ships under Apache-2.0 with
  no new runtime dependency; only opt-in LLM backends —
  `llama-cpp`, `transformers`, `external-llm` — need SPDX
  entries, and those land in the future
  `implement-phase-5-orchestration` change after each
  SPDX-tracked license inventory entry passes `LicenseGate`);
- the query orchestrator's L0 / L1 / L2 implementation —
  Phase 5 task 79 (`query-orchestrator`);
- the local LLM runtime binding — Phase 5 task 80
  (`local-llm-port`);
- the task context bundle builder — Phase 5 task 81
  (`task-context-builder`);
- the §47 capability discovery — Phase 5 task 82
  (`capability-discovery`);
- the §33 / §49 retrieval-first policy regression test —
  Phase 5 task 83 (`retrieval-first-policy`);
- the Wiki materialisation, control plane, security,
  distribution, A2A — Phase 7+ tasks 96-123;
- archiving this change. The change stays active
  (proposal-only) until the future
  `implement-phase-5-orchestration` change uses it as
  prerequisite.

## Affected capabilities

This change introduces the following additive capability
specs. None of the five accepted Phase 1 specs, the nine
accepted Phase 2 specs, the nine accepted Phase 3 specs or
the eight accepted Phase 4 specs is modified or retired.
Phase 5 specs depend on the Phase 1 specs (canonical schema,
Git-version-aware runtime, repository layout, license
governance), the Phase 2 specs (content-addressed
processing, semantic-structural chunking, context
enrichment), the Phase 3 specs (runtime store, sparse / dense
/ full-text indexes, sharded graph, provenance /
`KnowledgeState`, freshness tracking) and the Phase 4 specs
(multi-stage retrieval, context assembler, embedding model)
but do not alter their normative content.

| New capability | Architecture sections | Phase 5 task(s) | Spec delta path |
|---|---|---|---|
| `query-orchestrator` | §34, §33 | 79, 84 | [`specs/2026-10-05-query-orchestrator/spec.md`](specs/2026-10-05-query-orchestrator/spec.md) |
| `local-llm-port` | §35, §5.4 | 80, 84 | [`specs/2026-10-05-local-llm-port/spec.md`](specs/2026-10-05-local-llm-port/spec.md) |
| `task-context-builder` | §52 | 81, 84 | [`specs/2026-10-05-task-context-builder/spec.md`](specs/2026-10-05-task-context-builder/spec.md) |
| `capability-discovery` | §47 | 82, 84 | [`specs/2026-10-05-capability-discovery/spec.md`](specs/2026-10-05-capability-discovery/spec.md) |
| `retrieval-first-policy` | §33, §49 | 83, 84 | [`specs/2026-10-05-retrieval-first-policy/spec.md`](specs/2026-10-05-retrieval-first-policy/spec.md) |

Note on count: this change produces five capability specs
that cover tasks 79-83. Task 84 (Wiki maintenance) is the
`implement-phase-5-orchestration` close-out task and does
not require its own capability spec; its wiki and ADR
outputs are documented in
[`context-impact.md`](context-impact.md) so the future
archive step can flip the plan row from `[ ]` to `[x]`.

The five specs cover Phase 5 tasks 79-83 from
[`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md).
Tasks 79-84 remain `[ ]` in the plan change after this
change is archived; they will be flipped to `[x]` by the
future `implement-phase-5-orchestration` change when it
lands.

Cross-phase task responsibility:

- the query orchestrator (task 79) is owned by Phase 5 and
  composes the Phase 4 `MultiStageRetrievalPort` /
  `ContextAssemblerPort`; the Phase 6 MCP server (task 85)
  exposes the orchestrator as the `project.search` /
  `project.retrieve_context` tools;
- the `LocalLLMPort` (task 80) is the optional L1
  contextualisation step; the orchestrator gracefully
  degrades to L0 / L2 when the LLM is unavailable;
- the `TaskContextBuilder` (task 81) is the L2 bundle
  emitter; the Phase 10 A2A delegation (task 122) forwards
  the bundle to external strong agents;
- the `CapabilityDiscovery` (task 82) reports the §47
  descriptor; the Phase 6 MCP `describe_capabilities` tool
  (task 85) and the Phase 7 control plane (task 96) consume
  the descriptor;
- the `retrieval-first-policy` regression test (task 83) is
  the §49 compliance contract; the future Phase 7 quality
  gate (task 119) consumes the test outcome.

Naming and adoption conventions (per
[`openspec/config.yaml`](../../config.yaml) and
[`openspec/README.md`](../../README.md)):

- active change IDs are undated semantic kebab-case
  (`prepare-phase-5-orchestration`);
- delta folders under `specs/` use the future
  first-acceptance date (`2026-10-05-<capability>`);
- `openspec/CURRENT.md` is updated by the future
  `implement-phase-5-orchestration` change when the five
  Phase 5 specs are adopted, not by this change.

## Compatibility / migration impact

This change is a pure planning artifact. It adds:

- one new active change directory at
  `openspec/changes/prepare-phase-5-orchestration/`;
- five new spec deltas under
  `openspec/changes/prepare-phase-5-orchestration/specs/2026-10-05-*/`;
- one new active change directory at
  `openspec/changes/implement-phase-5-orchestration/`;
- five mirrored spec deltas under
  `openspec/changes/implement-phase-5-orchestration/specs/2026-10-05-*/`.

It does not:

- modify any accepted Phase 1 / Phase 2 / Phase 3 / Phase 4
  capability spec under `openspec/specs/`;
- modify `openspec/CURRENT.md`, the harness, the license
  inventory or the regression suite;
- introduce any source code, dependency or runtime
  configuration;
- rename any existing capability, port or adapter;
- alter the `plan-v0-8-platform-architecture` change
  (`tasks.md` still lists tasks 79-84 as `[ ]`).

Language and dependency decisions:

- the Python 3.11 platform source language decision recorded
  in
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  still holds. No new language dependency is being
  introduced by this change. The future
  `implement-phase-5-orchestration` change MAY add one
  optional LLM runtime — `llama-cpp` or `transformers` —
  but only after each SPDX-tracked license inventory
  entry passes `LicenseGate`. The default stub
  `LocalLLMPort` ships under Apache-2.0 with no new
  runtime dependency.
- no change to the licence-governance defaults. Any new
  dependency must be SPDX-tracked and pass `LicenseGate`
  before it lands in
  `distribution/licenses/dependency-inventory.json`. The
  candidate LLM runtimes are documented as review-required
  paths in the [`design.md`](design.md) so the future
  `local-llm-binding` ADR (if needed) carries the documented
  rationale.

OpenSpec CLI conventions:

- the change folder uses lowercase kebab-case without a
  date prefix (`prepare-phase-5-orchestration`) per
  [`openspec/config.yaml`](../../config.yaml);
- the five spec deltas are dated with the future
  acceptance date `2026-10-05` matching the Phase 1-4
  archive conventions; the archive step for the future
  `implement-phase-5-orchestration` change will produce
  `archive/2026-10-05-implement-phase-5-orchestration/`
  and rename the delta folders to drop the date prefix in
  the change-root view;
- no production code, license inventory entry or harness
  command is touched.

## Related knowledge

- `kb://architecture.platform-overview` — Phase 1-4 Wiki
  node; will be updated by the future
  `implement-phase-5-orchestration` change to add the
  Phase 5 module map (`orchestration/`,
  `ports/orchestration/`, `adapters/orchestration/`).
- `kb://architecture.system-overview` — cross-cutting
  view; will gain a Phase 5 module map row.
- `kb://glossary.platform` — Phase 1-4 platform
  vocabulary; the future change adds `QueryOrchestrator`,
  `LocalLLMPort`, `TaskContextBuilder`, `CapabilityDiscovery`,
  `CapabilityDescriptor`, `OrchestrationResult`,
  `TaskContextBundle`, `OrchestrationLevel`.
- `kb://glossary.domain` — cross-links to the platform
  vocabulary for the new entries.
- `kb://project.implementation-roadmap` — links to
  Phase 5 entry.
- `kb://project.project-map` — Phase 5 module map
  placeholder.
- `kb://adr.platform-source-language` — Python 3.11
  holds; the LLM runtimes stay under
  `pi_platform/adapters/orchestration/`.
- `kb://adr.canonical-runtime-separation` — Phase 5
  specs respect invariants #1-#4 and the canonical /
  runtime boundary; the orchestrator does not invent a
  new runtime store but composes the Phase 4 retrieval
  surface and emits ephemeral task context bundles.
- `kb://adr.license-governance-default` — every Phase 5
  dependency (LLM runtime, LLM model weights) requires an
  SPDX-tracked inventory entry.
- `kb://adr.embedded-storage-selection` — Phase 3 ADR
  that documents the storage backend Phase 5 reads
  through.
- future `kb://modules.orchestrator`,
  `kb://modules.llm-port`, `kb://modules.task-context` —
  Wiki module maps for the Phase 5 surface.
- future `kb://interfaces.capability-discovery` — Wiki
  interface node.
- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §33, §34, §35, §47, §49, §52 — every cited section is
  authoritative for the Phase 5 capability contracts.