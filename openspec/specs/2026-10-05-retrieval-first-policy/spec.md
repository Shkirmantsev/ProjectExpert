# 2026-10-05-retrieval-first-policy Specification

## Purpose
TBD - created by archiving change implement-phase-5-orchestration. Update Purpose after archive.
## Requirements
### Requirement: retrieval-first policy regression test

The platform MUST ship
`tests/test_orchestration_policy.py` with at least the
following regression tests:

- a test asserting the orchestrator runs the §33 escalation
  order (exact → sparse → dense → hybrid → graph → hierarchy
  → rerank → bounded context → LLM → source-file scan) and
  does not skip the retrieval stages;
- a test asserting the orchestrator does not trigger a
  direct source-file scan before retrieval evidence is
  gathered for an implementation question;
- a test asserting the orchestrator's `stats()` records
  `retrieval_first_violations` and the counter is `0` for
  the documented compliant query set;
- a test asserting the orchestrator refuses to escalate to
  L2 (strong external agent) before retrieval evidence is
  gathered;
- a test asserting the orchestrator's `OrchestrationResult.
  explanations` record the chosen level and the retrieval
  evidence the level-selection heuristic used.

#### Scenario: implementation question triggers retrieval first

Given an implementation question
("Implement REQ-471 and adapt integration tests.")
When the orchestrator processes the question
Then the orchestrator's `retrieval` field is populated before
any `llm_completion` or `task_context` is emitted
And `stats()["retrieval_first_violations"] == 0`
And the orchestrator records the chosen level and the
retrieval evidence in the result explanations.

#### Scenario: orchestrator refuses to skip retrieval

Given a query that asks for a source file directly
(e.g. "open the FinishPack protocol file")
When the orchestrator processes the query
Then the orchestrator still runs the retrieval pipeline
first
And only then opens the source file (the §33 step 9
"direct source-file scan only if retrieval evidence is
insufficient").

### Requirement: deterministic policy compliance

The retrieval-first policy test MUST be non-flaky. Two
consecutive test runs MUST return the same compliance
verdict for the same query set. The orchestrator MUST NOT
introduce hidden randomness that would cause the policy
test to fail intermittently.

#### Scenario: repeated policy test is stable

Given a stable project state
When `tests/test_orchestration_policy.py` runs twice
consecutively
Then both runs report `OK`
And the violation counters are identical across runs.

### Requirement: policy test coverage for all levels

The retrieval-first policy test MUST cover the L0, L1 and
L2 escalation paths. For each level, the test MUST assert
the retrieval evidence precedes the level-specific
operation.

#### Scenario: L0 path asserts retrieval first

Given an L0 query
When the orchestrator processes the query
Then the test asserts the retrieval pipeline ran before the
result was returned.

#### Scenario: L1 path asserts retrieval before LLM

Given an L1 query and an available local LLM
When the orchestrator processes the query
Then the test asserts the retrieval pipeline ran before the
LLM completion was requested.

#### Scenario: L2 path asserts retrieval before task context

Given an L2 query
When the orchestrator processes the query
Then the test asserts the retrieval pipeline ran before the
`TaskContextBundle` was emitted.

### Requirement: violation counter is exposed

The orchestrator MUST expose a `retrieval_first_violations`
counter through `stats()`. The counter MUST increment when
the orchestrator detects a policy violation (e.g. a query
that bypasses the retrieval pipeline and triggers a direct
source-file scan). The test asserts the counter is `0` for
the compliant query set.

#### Scenario: violation counter starts at zero

Given a fresh orchestrator
When `stats()` runs
Then `stats()["retrieval_first_violations"] == 0`.

#### Scenario: violation counter increments on policy violation

Given a corrupted orchestrator that bypasses the retrieval
pipeline
When the orchestrator processes a query
Then `stats()["retrieval_first_violations"]` increments
And the test fails with a clear message identifying the
violation.

