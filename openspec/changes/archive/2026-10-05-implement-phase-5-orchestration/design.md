# Design — implement-phase-5-orchestration

The technical design lives in
[`openspec/changes/prepare-phase-5-orchestration/design.md`](../../prepare-phase-5-orchestration/design.md).
This file is a thin reference so the implementation change
carries its own design section.

## Phase 5 module map

- `pi_platform/core/orchestration/` — new core subpackage;
- `pi_platform/ports/orchestration/` — new ports subpackage;
- `pi_platform/adapters/orchestration/` — new default
  adapters.

## Port surfaces (summary)

- `QueryOrchestratorPort` — `orchestrate`, `escalate`,
  `stats`;
- `LocalLLMPort` — `complete`, `is_available`,
  `model_version`, `license_id`, `family`, `stats`;
- `TaskContextBuilderPort` — `build`, `validate`, `stats`;
- `CapabilityDiscoveryPort` — `describe`, `refresh`,
  `stats`.

## Default adapters (summary)

- `DefaultQueryOrchestrator` — deterministic L0-default
  orchestrator that composes the Phase 4
  `MultiStageRetrievalPort`;
- `StubLocalLLMAdapter` — default stub `LocalLLMPort` that
  ships in the default container with
  `is_available() == False`;
- `DefaultTaskContextBuilder` — bounded §52 bundle builder;
- `DefaultCapabilityDiscovery` — deterministic §47
  descriptor.

## Per-stage budgets (orchestrator)

| Level | Default budget |
|---|---|
| L0 direct retrieval | 2 000 tokens (the `contextBudget` arg) |
| L1 retrieval + LLM | 2 000 tokens + 256 max_tokens LLM |
| L2 strong external agent | 4 000 tokens (the §52 default) |

## Risks and mitigations

See
[`openspec/changes/prepare-phase-5-orchestration/design.md`](../../prepare-phase-5-orchestration/design.md#risks-and-mitigations)
for the full risk matrix.