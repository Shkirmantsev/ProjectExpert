# Context impact — prepare-phase-5-orchestration

## Knowledge to create

The Wiki nodes below are NOT created by this change; they are
listed as future work the `implement-phase-5-orchestration`
change must perform when it ships the production code.

- `.ai/wiki/modules/orchestrator.md` — the Phase 5
  orchestrator module map
  (`pi_platform/core/orchestration/`,
  `pi_platform/ports/orchestration/`,
  `pi_platform/adapters/orchestration/`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/modules/llm-port.md` — the Phase 5 local LLM
  port module map
  (`pi_platform/ports/orchestration/local_llm.py`,
  `pi_platform/core/orchestration/local_llm.py`,
  `pi_platform/adapters/orchestration/stub_local_llm.py`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/modules/task-context.md` — the Phase 5
  task-context builder module map
  (`pi_platform/ports/orchestration/task_context.py`,
  `pi_platform/core/orchestration/task_context.py`).
  `kind: modules`, `status: draft`.
- `.ai/wiki/interfaces/capability-discovery.md` — the
  `CapabilityDiscoveryPort` port contract, the §47
  descriptor shape and the `features` map.
  `kind: interfaces`, `status: draft`.

## Knowledge to update

The Wiki updates below are NOT performed by this change;
they are listed as future work the
`implement-phase-5-orchestration` change must perform
alongside the production code.

- `.ai/wiki/architecture/platform-overview.md` — extend
  the Phase 1-4 module map with the Phase 5 module map
  (`orchestration/`, `ports/orchestration`,
  `adapters/orchestration`). Reference the new
  `modules/orchestrator.md`, `modules/llm-port.md` and
  `modules/task-context.md` nodes.
- `.ai/wiki/architecture/system-overview.md` — extend
  the "Principal components" section with the Phase 5
  orchestrator reference and links to the new module /
  interface nodes.
- `.ai/wiki/glossary/platform.md` — add Phase 5
  vocabulary entries: `QueryOrchestrator`, `LocalLLMPort`,
  `TaskContextBuilder`, `CapabilityDiscovery`,
  `CapabilityDescriptor`, `CapabilityFeatures`,
  `OrchestrationResult`, `OrchestrationLevel`,
  `TaskContextBundle`. Status flips from `draft` to
  `active` once the implementation lands.
- `.ai/wiki/glossary/domain.md` — cross-link to the
  platform vocabulary for the new entries.
- `.ai/wiki/project/project-map.md` — add the new
  module folders under "Main source areas" with status
  `planned` until the implementation change lands; flip
  to `active` once the code is on disk.
- `.ai/wiki/project/implementation-roadmap.md` — add the
  Phase 5 row to the phase table.
- `.ai/wiki/INDEX.md` — add the new Wiki modules,
  interfaces and ADRs once they exist on disk; the future
  implementation change is responsible for the index
  update.
- `openspec/CURRENT.md` — add the five Phase 5
  capabilities once the future
  `implement-phase-5-orchestration` change is archived;
  this change does NOT modify `openspec/CURRENT.md`.

## Knowledge to review for staleness

- `.ai/wiki/architecture/platform-overview.md` — review
  the Phase 1-4 module map and ensure the Phase 5
  extensions remain additive; the existing Phase 1-4
  boundaries MUST stay unchanged.
- `.ai/wiki/glossary/platform.md` — review the Phase 1-4
  vocabulary; Phase 5 adds new entries
  (`QueryOrchestrator`, `LocalLLMPort`,
  `TaskContextBuilder`, `CapabilityDiscovery`). The
  existing `EmbeddingModelPort`, `HybridRetrieval`,
  `MultiStageRetrieval`, `RerankerPort`, `MetadataFilter`,
  `ContextAssembler` entries remain unchanged.
- `.ai/wiki/adr/0005-platform-source-language.md` —
  review the Python 3.11 decision and confirm the Phase 5
  LLM runtimes land as adapters under
  `pi_platform/adapters/orchestration/` rather than as
  new platform-level language dependencies. The ADR is
  unchanged in this change; the future implementation
  change adds the optional LLM backends without modifying
  the ADR text.
- `.ai/wiki/adr/0002-canonical-runtime-separation.md` —
  review the canonical / runtime separation invariants;
  the Phase 5 task context bundle is an ephemeral
  transport artifact and is NOT canonical knowledge per
  the §52 spec.
- `.ai/wiki/adr/0003-license-governance-default.md` —
  review the licence-governance default; every Phase 5
  LLM dependency (runtime + model weights) requires an
  SPDX-tracked inventory entry.

## Related knowledge

- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §33, §34, §35, §47, §49, §52 — every cited section is
  authoritative for the Phase 5 capability contracts.