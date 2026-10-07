# 2026-10-05-query-orchestrator Specification

## Purpose
Select the cheapest sufficient query processing level and coordinate retrieval, context assembly, and optional language-model escalation.
## Requirements
### Requirement: QueryOrchestratorPort contract

The platform MUST expose a `QueryOrchestratorPort` abstract
class in `pi_platform/ports/orchestration/query_orchestrator.py`
with the following operations:

- `orchestrate(query: str, *, level: Optional[int] = None,
  task_context: Optional[TaskContext] = None) ->
  OrchestrationResult` — return the orchestration result for a
  user query. When `level` is `None`, the orchestrator selects
  the cheapest sufficient level per the §33 escalation policy;
- `escalate(orchestration: OrchestrationResult, *, reason: str)
  -> OrchestrationResult` — bump the orchestration to the next
  escalation level when the current level is insufficient;
- `stats() -> Mapping[str, int]` — operational counters
  including `level0_calls`, `level1_calls`, `level2_calls`,
  `escalations`, `retrieval_first_violations`.

`OrchestrationResult` carries `level`, `query`, `retrieval`
(a `MultiStageRetrievalResult`), `llm_completion` (an optional
LLM response when level=1), `task_context` (an optional
`TaskContextBundle` when level=2), `budget_used` and
`explanations`.

#### Scenario: orchestrator selects L0 for direct retrieval

Given a query that maps to a deterministic identifier lookup
(e.g. "Where is OrderStatus declared?")
When `orchestrate(query)` runs
Then `result.level == 0`
And `result.llm_completion is None`
And `result.task_context is None`
And `stats()["level0_calls"]` increments.

#### Scenario: orchestrator selects L1 for explanation

Given a query that requires explanation over a bounded context
(e.g. "Explain the FinishPack protocol message.")
When `orchestrate(query)` runs
Then `result.level == 1`
And `result.llm_completion is not None` (when the local LLM
is available)
And `result.task_context is None`
And `stats()["level1_calls"]` increments.

#### Scenario: orchestrator selects L2 for implementation work

Given a query that requires implementation work
(e.g. "Implement REQ-471 and adapt integration tests.")
When `orchestrate(query)` runs
Then `result.level == 2`
And `result.task_context is not None`
And `result.task_context` is a `TaskContextBundle` with
`goal == query`, the relevant `requirement` / `openSpec` /
`tests` slots populated, and the `git_diff` slot empty
(delegation contract).

### Requirement: explicit level override

The orchestrator MUST honour an explicit `level` argument when
supplied. An explicit `level=0` MUST bypass the local LLM
even when the local LLM is registered; an explicit `level=2`
MUST bypass the L0 / L1 path and emit a `TaskContextBundle`
directly.

#### Scenario: explicit level override

Given the local LLM is registered
When `orchestrate(query, level=0)` runs
Then `result.level == 0`
And the local LLM is NOT invoked
And `result.llm_completion is None`.

### Requirement: retrieval-first escalation order

The orchestrator MUST encode the §33 retrieval-first escalation
order: exact symbol / metadata lookup → sparse search → dense
semantic search → hybrid fusion → graph + hierarchy expansion →
reranking → bounded Context Assembly → strong LLM reasoning →
direct source-file scan. The orchestrator MUST NOT trigger a
direct source-file scan before retrieval evidence is gathered;
the `retrieval-first-policy` capability documents the regression
test contract.

#### Scenario: orchestrator follows retrieval-first order

Given any query
When `orchestrate(query)` runs
Then `stats()["retrieval_first_violations"]` is not incremented
And `result.retrieval` carries the multi-stage pipeline output
And the result explanations record the chosen level.

### Requirement: deterministic level selection

The platform MUST return the same `OrchestrationResult.level`
for a fixed query and a fixed project state across repeated
invocations. The level-selection heuristic MUST be documented
in the future `design.md` and MUST NOT depend on hidden LLM
randomness.

#### Scenario: repeated query returns same level

Given an orchestrator instance and a fixed project state
When `orchestrate(query)` runs twice consecutively
Then both `OrchestrationResult.level` values are equal
And the retrieval bundle is byte-identical within the
documented numerical tolerance.

### Requirement: escalation bumps the level

The `escalate(orchestration, *, reason)` operation MUST bump
the orchestration to the next level (L0 → L1 → L2). The
original retrieval bundle MUST be preserved so the escalated
result reuses the L0 evidence.

#### Scenario: escalate from L0 to L1

Given an L0 `OrchestrationResult`
When `escalate(result, reason="needs-explanation")` runs
Then `escalated.level == 1`
And `escalated.retrieval is result.retrieval`
And `escalated.llm_completion is not None` (when LLM is
available).

#### Scenario: escalation caps at L2

Given an L2 `OrchestrationResult`
When `escalate(result, reason="...")` runs
Then the orchestrator raises `EscalationCapError`
OR returns the L2 result unchanged (the documented
"no-further-escalation" scenario).

