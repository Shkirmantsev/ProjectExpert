---
id: modules.orchestrator
title: Phase 5 query orchestrator module map
kind: modules
status: active
summary: Phase 5 §34 Query Orchestrator port, core and adapter for the three-level L0/L1/L2 escalation that composes the Phase 4 multi-stage retrieval pipeline.
sourceRefs:
  - pi_platform/ports/orchestration/query_orchestrator.py
  - pi_platform/core/orchestration/query_orchestrator.py
  - pi_platform/adapters/orchestration/query_orchestrator.py
  - openspec/specs/2026-10-05-query-orchestrator/spec.md
  - openspec/changes/implement-phase-5-orchestration/proposal.md
maintenance:
  mode: authored
related:
  - modules.llm-port
  - modules.task-context
  - interfaces.capability-discovery
  - modules.retrieval
---

# Phase 5 query orchestrator modules

The §34 query orchestrator is the deterministic component
that selects between three escalation levels (L0 direct
retrieval, L1 retrieval + small local LLM, L2 strong
external agent) for an agent request. The orchestrator
composes the Phase 4 `MultiStageRetrievalPort` /
`ContextAssemblerPort` and the Phase 5 `LocalLLMPort` /
`TaskContextBuilderPort`. The §33 retrieval-first
escalation policy is the orchestration contract.

The orchestrator ships as a port-and-adapter pair: the
`QueryOrchestratorPort` under
`pi_platform/ports/orchestration/query_orchestrator.py`,
the `DefaultQueryOrchestrator` core under
`pi_platform/core/orchestration/`, and the
`DefaultQueryOrchestratorAdapter` under
`pi_platform/adapters/orchestration/`.

## Port (`pi_platform/ports/orchestration/query_orchestrator.py`)

- `QueryOrchestratorPort` — abstract base with the
  `orchestrate`, `escalate` and `stats` operations.
- `OrchestrationLevel` — the three-level enum (L0, L1, L2).
- `OrchestrationResult` — the orchestrator's per-query
  output carrying `level`, `query`, `retrieval`,
  `llm_completion`, `task_context`, `budgetUsed`,
  `explanations` and `retrieval_first_violation`.
- `QueryOrchestratorError` / `EscalationCapError` —
  raised when the orchestrator cannot satisfy a request
  or when the caller asks to escalate past L2.

## Core (`pi_platform/core/orchestration/query_orchestrator.py`)

- `DefaultQueryOrchestrator` — deterministic L0-default
  orchestrator. The `orchestrate` operation always runs
  the retrieval pipeline first; the LLM completion is
  requested only at L1; the `TaskContextBuilder` is
  invoked only at L2. The `escalate` operation bumps the
  level (L0 → L1 → L2) and reuses the original retrieval
  bundle. The `stats()` response records
  `level0_calls`, `level1_calls`, `level2_calls`,
  `escalations` and `retrieval_first_violations`.

## Adapter (`pi_platform/adapters/orchestration/query_orchestrator.py`)

- `DefaultQueryOrchestratorAdapter` — registry-friendly
  wrapper around `DefaultQueryOrchestrator`. The default
  adapter selected by `orchestrator-status`; satisfies
  the §34 default-adapter scenario.

## Level-selection heuristic

The level-selection heuristic is intentionally simple and
remains config-driven through
`project-context.yaml:orchestrator.level_selection`. The
default heuristic:

- L0 — direct retrieval, no LLM completion. The
  orchestrator returns the `MultiStageRetrievalResult`
  as the bundle.
- L1 — retrieval + small local LLM. The orchestrator
  calls the `LocalLLMPort.complete` operation on a
  bounded prompt derived from the top-5 retrieval
  snippets. When the LLM is unavailable, the
  orchestrator escalates to L2.
- L2 — strong external agent. The orchestrator calls the
  `TaskContextBuilder.build` operation with the retrieval
  result and the documented §52 budget. The
  `TaskContextBundle` is the L2 transport artifact the
  external agent consumes.

The `retrieval-first-violation` counter increments when an
L2 bundle is emitted without prior retrieval evidence;
the §33 retrieval-first policy regression test
(`tests/test_orchestration_policy.py`) asserts the counter
is `0` for the documented compliant query set.

## CLI surface

- `python -m pi_platform.cli orchestrator-status` —
  reports the active backend, the per-level call
  counters, the local LLM availability and the §52
  builder configuration.