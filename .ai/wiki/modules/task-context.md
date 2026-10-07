---
id: modules.task-context
title: Phase 5 task context builder module map
kind: modules
status: active
summary: Phase 5 §52 TaskContextBuilder — bounded ephemeral task context bundle the L2 orchestrator emits and the Phase 6 MCP server forwards to external strong agents.
sourceRefs:
  - pi_platform/ports/orchestration/task_context.py
  - pi_platform/core/orchestration/task_context.py
  - pi_platform/adapters/orchestration/task_context.py
  - openspec/specs/2026-10-05-task-context-builder/spec.md
maintenance:
  mode: authored
related:
  - modules.orchestrator
  - interfaces.capability-discovery
---

# Phase 5 task context builder modules

The §52 task context bundle is the bounded ephemeral
transport artifact the Phase 5 `QueryOrchestrator`
emits at L2 and the Phase 6 MCP server forwards to
external strong agents. The bundle aggregates the
requirement, the relevant OpenSpec, the Wiki sections,
the source code, the interfaces, the dependencies, the
architecture constraints, the graph neighbourhood, the
tests and the Git diff for the bounded context the
agent receives.

The bundle is an ephemeral transport artifact, NOT
canonical knowledge. The builder ships as a port-
and-adapter pair: the `TaskContextBuilderPort` plus
the slot value types under
`pi_platform/ports/orchestration/task_context.py`,
the `DefaultTaskContextBuilder` core under
`pi_platform/core/orchestration/`, and the
`DefaultTaskContextBuilderAdapter` under
`pi_platform/adapters/orchestration/`.

## Port (`pi_platform/ports/orchestration/task_context.py`)

- `TaskContextBuilderPort` — abstract base with the
  `build`, `validate` and `stats` operations.
- `TaskContextBundle` — the bundle value type
  carrying `taskId`, `goal`, `budgetTokens`, the slot
  collections and the `droppedSlots` / `explanations`
  fields.
- Slot value types — `RequirementSlot`, `OpenSpecSlot`,
  `WikiSlot`, `CodeSlot`, `InterfaceSlot`,
  `DependencySlot`, `ArchitectureSlot`, `EntitySlot`,
  `TestSlot`, `DiffSlot`.
- `BUNDLE_SLOT_PRIORITY` — the documented §52 priority
  ordering (requirement > openSpec > tests > source
  code > interfaces > dependencies > architecture >
  graph > wiki > diff) the budget truncation honours.
- `TaskContextBuilderError` — raised when the builder
  cannot build a bundle.

## Core (`pi_platform/core/orchestration/task_context.py`)

- `DefaultTaskContextBuilder` — default implementation.
  The `build` operation extracts the requirement
  identifier (via the `REQUIREMENT_PATTERN` regex), the
  OpenSpec references (via the `OPENSPEC_PATTERN` regex)
  and the graph-neighbourhood / test / source / interface
  / dependency / architecture / wiki slots from the
  optional `MultiStageRetrievalResult`. The budget
  truncation drops the lowest-priority slots first
  (per `BUNDLE_SLOT_PRIORITY`) and records the dropped
  slots under `bundle.droppedSlots`.

## Adapter (`pi_platform/adapters/orchestration/task_context.py`)

- `DefaultTaskContextBuilderAdapter` — registry-friendly
  wrapper around `DefaultTaskContextBuilder`. The default
  adapter; satisfies the §52 default-adapter scenario.

## Determinism

The bundle's `taskId` is a stable Blake2b digest of the
`goal` and `budget_tokens` arguments, so two consecutive
`build` calls with the same input return byte-identical
bundles within the documented numerical tolerance. The
deterministic ordering is the source of truth the §49
evaluation-gate reproducibility requirement relies on.