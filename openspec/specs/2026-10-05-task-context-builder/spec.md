# 2026-10-05-task-context-builder Specification

## Purpose
Build and validate bounded, version-aware context bundles for agent tasks from retrieval evidence.
## Requirements
### Requirement: TaskContextBuilderPort contract

The platform MUST expose a `TaskContextBuilderPort` abstract
class in
`pi_platform/ports/orchestration/task_context.py` with the
following operations:

- `build(goal: str, *, budget_tokens: int = 4000,
  project_version: Optional[ProjectVersion] = None,
  retrieval: Optional[MultiStageRetrievalResult] = None) ->
  TaskContextBundle` — assemble the bounded context bundle
  for an agent task. The `goal` carries the human-readable
  task description; the `budget_tokens` is the upper bound
  on the cumulative token estimate of the assembled bundle.
- `validate(bundle: TaskContextBundle) -> Sequence[str]` —
  return the list of validation issues (empty list when
  well-formed).

`TaskContextBundle` carries:

- `taskId` (str) — opaque task identifier;
- `goal` (str) — the human-readable task description;
- `budgetTokens` (int) — the budget the bundle is bounded to;
- `requirement` (Optional[RequirementSlot]) — the canonical
  requirement reference;
- `openSpec` (Sequence[OpenSpecSlot]) — the relevant
  OpenSpec references;
- `wikiSections` (Sequence[WikiSlot]) — the relevant Wiki
  sections;
- `sourceCode` (Sequence[CodeSlot]) — the relevant source-
  code references;
- `interfaces` (Sequence[InterfaceSlot]) — the relevant
  interface references;
- `dependencies` (Sequence[DependencySlot]) — the relevant
  dependency references;
- `architectureConstraints` (Sequence[ArchitectureSlot]) —
  the relevant architecture constraints;
- `graphNeighbourhood` (Sequence[EntitySlot]) — the relevant
  knowledge-graph neighbourhood;
- `tests` (Sequence[TestSlot]) — the relevant test
  references;
- `gitDiff` (Sequence[DiffSlot]) — the bounded Git diff.

#### Scenario: build produces a bounded bundle

Given a `goal` and `budget_tokens=4000`
When `build(goal)` runs
Then the returned bundle has a non-empty `taskId`
And `bundle.budgetTokens == 4000`
And the cumulative token estimate of the bundle slots does
not exceed `budget_tokens`
And the bundle is serialisable to JSON.

### Requirement: bundle is ephemeral

The `TaskContextBuilderPort.build` operation MUST return a
fresh `TaskContextBundle` instance on every call. The bundle
MUST NOT be persisted as canonical knowledge; the
`TaskContext` value type from `pi_platform/core/canonical/
value_types.py` is the canonical shape, but the bundle
extends it with the §52 slot vocabulary.

#### Scenario: ephemeral bundle is not persisted

Given two consecutive `build(goal)` calls
When both calls run
Then the two `TaskContextBundle` instances are distinct
And neither is written to the runtime store, the canonical
tree, or the runtime cache.

### Requirement: budget enforcement

The `TaskContextBuilderPort.build` operation MUST enforce the
`budget_tokens` constraint. When the assembled slots would
exceed the budget, the builder MUST drop the lowest-priority
slots (per the §52 priority: requirement > openSpec > tests >
source code > interfaces > dependencies > architecture >
graph neighbourhood > wiki > git diff) and record the dropped
slots under `bundle.dropped_slots`.

#### Scenario: budget truncation drops lowest-priority slots

Given a `budget_tokens=2000` and a `retrieval` result with
50 hits each costing 100 tokens
When `build(goal, budget_tokens=2000)` runs
Then the bundle's cumulative token estimate is `<= 2000`
And `bundle.dropped_slots` records the truncated slots
And the dropped-slot ordering matches the §52 priority.

### Requirement: requirement and OpenSpec slots

The bundle MUST include the `requirement` slot when the
goal references a documented requirement identifier (e.g.
`REQ-471`, `GEN_3.0.03`). The bundle MUST include the
`openSpec` slot when the goal references an OpenSpec change
or capability identifier.

#### Scenario: requirement slot is included

Given a goal containing `REQ-471`
When `build(goal)` runs
Then `bundle.requirement` is populated
And `bundle.requirement.identifier == "REQ-471"`.

#### Scenario: OpenSpec slot is included

Given a goal containing the capability identifier
`embedding-model`
When `build(goal)` runs
Then at least one `bundle.openSpec` slot is populated
And the slot references `2026-10-04-embedding-model`.

### Requirement: graph neighbourhood slot

The bundle MUST include the `graphNeighbourhood` slot when
the `retrieval` argument is provided. The slot consumes the
Phase 4 `GraphExpansionResult` and records the expanded
entities and relations.

#### Scenario: graphNeighbourhood slot consumes graph expansion

Given a `MultiStageRetrievalResult` whose `graphExpansion`
field carries expanded entities
When `build(goal, retrieval=result)` runs
Then `bundle.graphNeighbourhood` is populated
And the slot references the expanded entities.

### Requirement: deterministic bundle ordering

The platform MUST return a deterministic `TaskContextBundle`
for a fixed `goal`, `budget_tokens`, `project_version` and
`retrieval` input. The slot ordering and `taskId` MUST be
stable across repeated invocations.

#### Scenario: repeated build is deterministic

Given a builder instance and fixed inputs
When `build(goal, ...)` runs twice
Then both bundles have the same `taskId`
And the slot ordering is byte-identical
And `bundle.budgetTokens` is the same value.

