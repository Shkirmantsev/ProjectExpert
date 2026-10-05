# Proposal — Implement Phase 5 Orchestration Subsystem (tasks 79-84)

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the orchestration layer as the fifth implementation
phase. The Phase 5 capability specs authored by
[`openspec/changes/prepare-phase-5-orchestration/`](../../prepare-phase-5-orchestration/)
give the orchestration subsystem its authoritative
behavioural contract:

- `query-orchestrator` (§34, §33) — the deterministic
  three-level (L0 / L1 / L2) query orchestrator;
- `local-llm-port` (§35, §5.4) — the optional local LLM
  port with a deterministic stub default;
- `task-context-builder` (§52) — the bounded task context
  bundle builder;
- `capability-discovery` (§47) — the deterministic §47
  capability descriptor;
- `retrieval-first-policy` (§33, §49) — the §33 retrieval-
  first policy regression contract.

The Phase 4 retrieval subsystem
(`openspec/changes/archive/2026-10-05-implement-phase-4-retrieval/`)
supplies the `MultiStageRetrievalPort` and the
`ContextAssemblerPort` that the Phase 5 orchestrator
composes. Without Phase 5 implementation, the platform cannot
answer agent requests through the §34 three-level
escalation, the §47 capability descriptor is not exposed,
the §52 task context bundle is not emitted and the §33 / §49
retrieval-first policy has no regression test.

This change ships the production code, the per-capability
regression suite and the §33 retrieval-first policy
regression test. It depends on the five Phase 5 capability
specs being accepted into `openspec/specs/2026-10-05-*/`.

## Goal

Implement the Phase 5 orchestration subsystem so that:

- `pi_platform.ports.orchestration.query_orchestrator.QueryOrchestratorPort`
  exposes a deterministic `orchestrate` operation that
  selects L0 / L1 / L2 per the §33 escalation policy;
- `pi_platform.ports.orchestration.local_llm.LocalLLMPort`
  exposes a stable LLM surface with a deterministic stub
  default that ships in the default container;
- `pi_platform.ports.orchestration.task_context.TaskContextBuilderPort`
  produces the bounded §52 task context bundle with
  priority-based budget truncation;
- `pi_platform.ports.orchestration.capability_discovery.CapabilityDiscoveryPort`
  returns the deterministic §47 capability descriptor;
- `tests.test_orchestration_phase5` records the per-
  capability regression suite;
- `tests.test_orchestration_policy` records the §33
  retrieval-first policy regression test.

What this change does:

- implements the ports, cores and adapters listed above;
- registers the stub `LocalLLMPort` as the default; opt-in
  LLM runtimes land as adapters without changing the
  default container behaviour;
- ships the `tests/test_orchestration_phase5.py` per-
  capability regression suite and the
  `tests/test_orchestration_policy.py` §33 retrieval-first
  policy regression test;
- updates the Wiki, the glossary and the architecture
  overview with the Phase 5 module map;
- updates `openspec/CURRENT.md` to add the five Phase 5
  capabilities;
- flips `plan-v0-8-platform-architecture/tasks.md` rows
  79-84 from `[ ]` to `[x]`;
- archives this change under
  `openspec/changes/archive/2026-10-05-implement-phase-5-orchestration/`
  and the preparation change under
  `openspec/changes/archive/2026-10-05-prepare-phase-5-orchestration/`.