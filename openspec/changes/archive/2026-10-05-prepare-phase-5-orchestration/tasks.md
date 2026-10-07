# Tasks — prepare-phase-5-orchestration

This tasks file mirrors the Phase 5 tasks 79-84 from the
canonical
[`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md).
The tasks below are the future implementation work; they
will be executed by the future
`implement-phase-5-orchestration` change. This change ships
zero production code.

The five Phase 5 capability specs under [`specs/`](specs) are
the authoritative behavioural contract for the implementation
work. The future change depends on the five specs being
accepted into `openspec/specs/2026-10-05-*/` before tasks
79-84 can be marked `[x]`; until then they stay `[ ]` in
both the plan change and the future implementation change.

Verification commands referenced below:

- `python -m unittest tests.<module> -v` — focused
  regression tests;
- `openspec validate implement-phase-5-orchestration
  --type change --strict` (future change), `openspec
  validate --all --strict` (canonical harness check);
- `python harness.py check` — full harness core gate
  (license-gate, openspec-check, wiki-validate,
  artifact-manifest).

## Phase 5 — Orchestration (preparation only)

### 5.1 — QueryOrchestratorPort (task 79)

- [ ] 79. Implement
  `platform.orchestrator.QueryOrchestrator` with three
  escalation levels (L0 direct retrieval, L1 retrieval +
  small local LLM, L2 strong external agent) and the
  retrieval-first escalation order from §33.
  → `pi_platform/ports/orchestration/query_orchestrator.py`
  (new port),
  `pi_platform/core/orchestration/query_orchestrator.py`
  (new core),
  `pi_platform/adapters/orchestration/query_orchestrator.py`
  (new default adapter).
  Verification:
  - `python -m unittest
    tests.test_orchestration_phase5.QueryOrchestratorTests -v`;
  - the `tests/test_orchestration_policy.py` regression
    test MUST report `OK` for the documented compliant
    query set;
  - `python -m pi_platform.cli orchestrator-status` MUST
    exit zero and report the per-level call counters.

### 5.2 — LocalLLMPort (task 80)

- [ ] 80. Implement
  `platform.llm.LocalLLMPort` behind a stable interface; do
  not bind any specific model in the default container;
  declare the local-LLM capability as optional in
  capability discovery.
  → `pi_platform/ports/orchestration/local_llm.py` (new
  port),
  `pi_platform/core/orchestration/local_llm.py` (new
  core),
  `pi_platform/adapters/orchestration/stub_local_llm.py`
  (new default stub adapter).
  Verification:
  - `python -m unittest
    tests.test_orchestration_phase5.LocalLLMTests -v`;
  - `python -m pi_platform.cli llm-status` MUST report
    `is_available: false` in the default container;
  - the `CapabilityDescriptor.features.localLlm` MUST be
    `false` until an opt-in LLM runtime is registered.

### 5.3 — TaskContextBuilder (task 81)

- [ ] 81. Implement
  `platform.task.TaskContextBuilder` producing the bounded
  TaskContext bundle shape from §52.
  → `pi_platform/ports/orchestration/task_context.py` (new
  port),
  `pi_platform/core/orchestration/task_context.py` (new
  core),
  `pi_platform/adapters/orchestration/task_context.py`
  (new default adapter).
  Verification:
  - `python -m unittest
    tests.test_orchestration_phase5.TaskContextBuilderTests -v`;
  - the bundle MUST be JSON-serialisable;
  - the budget truncation MUST respect the §52 priority
    ordering.

### 5.4 — CapabilityDiscovery (task 82)

- [ ] 82. Implement
  `platform.orchestrator.CapabilityDiscovery` returning
  the structured capability descriptor from §47.
  → `pi_platform/ports/orchestration/capability_discovery.py`
  (new port),
  `pi_platform/core/orchestration/capability_discovery.py`
  (new core),
  `pi_platform/adapters/orchestration/capability_discovery.py`
  (new default adapter).
  Verification:
  - `python -m unittest
    tests.test_orchestration_phase5.CapabilityDiscoveryTests -v`;
  - `python -m pi_platform.cli capabilities` MUST exit
    zero and emit the §47 JSON descriptor;
  - the descriptor MUST match the §47 example shape
    (serverVersion, mcpApiVersion, knowledgeSchemaVersion,
    features.{hybridRetrieval, graphExpansion, okf,
    materialization, a2a, localLlm}).

### 5.5 — Retrieval-first policy test (task 83)

- [ ] 83. Add focused regression tests including a
  retrieval-first policy test asserting that an
  implementation question does not trigger broad source
  scanning before MCP retrieval.
  → `tests/test_orchestration_policy.py` (new).
  Verification:
  - `python -m unittest
    tests.test_orchestration_policy -v` MUST report `OK`;
  - the test MUST assert
    `stats()["retrieval_first_violations"] == 0` for the
    documented compliant query set;
  - the test MUST be non-flaky (two consecutive runs
    report the same outcome).

### 5.6 — Wiki maintenance and archive (task 84)

- [ ] 84. Update Wiki (new
  `modules/orchestrator`, `modules/llm-port`,
  `modules/task-context`,
  `interfaces/capability-discovery`), archive this change
  under
  `archive/2026-10-05-prepare-phase-5-orchestration/`,
  archive the implementation change under
  `archive/2026-10-05-implement-phase-5-orchestration/`,
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