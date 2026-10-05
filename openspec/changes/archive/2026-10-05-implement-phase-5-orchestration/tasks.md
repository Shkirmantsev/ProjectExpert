# Tasks — implement-phase-5-orchestration

This tasks file mirrors
[`openspec/changes/prepare-phase-5-orchestration/tasks.md`](../../prepare-phase-5-orchestration/tasks.md).
The Phase 5 tasks 79-84 are owned by this implementation
change. The five Phase 5 capability specs under
[`openspec/changes/prepare-phase-5-orchestration/specs/`](../../prepare-phase-5-orchestration/specs/)
(and mirrored under [`specs/`](specs)) are the authoritative
behaviour contract.

The Phase 4 retrieval surface is the prerequisite. This
change does NOT modify the Phase 4 surface beyond composing
it through the documented ports.

## Phase 5 — Orchestration (tasks 79-84)

### 5.1 — QueryOrchestratorPort (task 79)

- [ ] 79. Implement
  `platform.orchestrator.QueryOrchestrator` with three
  escalation levels and the retrieval-first escalation
  order from §33. See
  [`prepare-phase-5-orchestration/tasks.md`](../../prepare-phase-5-orchestration/tasks.md#51--queryorchestratorport-task-79)
  for the file map.

### 5.2 — LocalLLMPort (task 80)

- [ ] 80. Implement
  `platform.llm.LocalLLMPort` behind a stable interface;
  do not bind any specific model in the default container.

### 5.3 — TaskContextBuilder (task 81)

- [ ] 81. Implement
  `platform.task.TaskContextBuilder` producing the bounded
  TaskContext bundle shape from §52.

### 5.4 — CapabilityDiscovery (task 82)

- [ ] 82. Implement
  `platform.orchestrator.CapabilityDiscovery` returning
  the structured capability descriptor from §47.

### 5.5 — Retrieval-first policy test (task 83)

- [ ] 83. Add focused regression tests including a
  retrieval-first policy test asserting that an
  implementation question does not trigger broad source
  scanning before MCP retrieval.

### 5.6 — Wiki maintenance and archive (task 84)

- [ ] 84. Update Wiki (new `modules/orchestrator`,
  `modules/llm-port`, `modules/task-context`,
  `interfaces/capability-discovery`), archive this change
  under
  `archive/2026-10-05-implement-phase-5-orchestration/`,
  archive the preparation change under
  `archive/2026-10-05-prepare-phase-5-orchestration/`,
  update `openspec/CURRENT.md`, flip
  `plan-v0-8-platform-architecture/tasks.md` rows 79-84
  to `[x]`.

Verification for the slice (tasks 83-84):

- `python harness.py wiki-validate` MUST pass;
- `python harness.py openspec-check` MUST pass;
- `python harness.py check` MUST pass;
- `openspec validate implement-phase-5-orchestration
  --type change --strict` MUST return `valid`;
- the Phase 1-4 regression suites MUST remain green.

## Out-of-scope tasks (this change)

- Phase 6: MCP server (task 85);
- Phase 7+: control plane, security, distribution, A2A
  (tasks 86-123).