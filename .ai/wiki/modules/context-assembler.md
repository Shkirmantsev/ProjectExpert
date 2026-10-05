---
id: modules.context-assembler
title: Phase 4 context-assembler module map
kind: modules
status: active
summary: Phase 4 §32 ContextAssembler — port, core and adapter layer for the bounded-context bundle builder.
sourceRefs:
  - pi_platform/ports/retrieval/context_assembler.py
  - pi_platform/core/retrieval/context_assembler.py
  - pi_platform/adapters/retrieval/context_assembler_adapter.py
  - openspec/specs/2026-10-04-context-assembler/spec.md
maintenance:
  mode: authored
related:
  - modules.retrieval
---

# Phase 4 context-assembler modules

The §32 context assembler is a first-class component. It combines
chunks, parent sections, code symbols, requirements, OpenSpec
references, ADRs, graph neighbours, versions, sources, provenance
and confidence into a bounded context bundle that the Phase 5
orchestrator and the Phase 6 MCP server consume.

The assembler must deduplicate overlapping evidence, enforce the
context budget, preserve citations, prefer authoritative
evidence, detect conflicting hits and surface uncertainty. The
context-assembler layer ships as a port-and-adapter pair: the
`ContextAssemblerPort` plus the `ContextBudget`, `Citation` and
`ContextBundle` value types under
`pi_platform/ports/retrieval/context_assembler.py`, the
`ContextAssemblerCore` under `pi_platform/core/retrieval/`, and
the `ContextAssemblerAdapter` under
`pi_platform/adapters/retrieval/`.

## Port (`pi_platform/ports/retrieval/context_assembler.py`)

- `ContextAssemblerPort` — abstract base with the `assemble`
  operation and the `stats` accessor.
- `ContextBudget` — immutable budget: `tokenLimit` (mandatory,
  positive) plus an optional `maxHits` secondary cap. The
  assembler enforces the budget per the §32 spec.
- `Citation` — immutable per-hit citation: `chunkId`,
  `contentHash`, `sourceReference`, `projectVersion` and
  `evidenceWeight` (`0.0`–`1.0`).
- `ContextBundle` — the bounded context bundle shape with
  `hits`, `dedupedEntities`, `citations`, `authoritativeHits`,
  `conflictingHits`, `uncertainHits`, `budgetUsed`, `droppedHits`,
  `dropReasons` and `explanations` fields.
- `ContextAssemblerError` — raised when the assembler cannot
  build a bundle.

## Core (`pi_platform/core/retrieval/context_assembler.py`)

- `ContextAssemblerCore` — default implementation. The
  deduplication pass keeps the first instance of each
  `chunkId` and records the duplicates under `droppedHits`
  with reason `deduplicated`. The authoritative-preference
  pass splits the deduplicated hits before the budget pass so
  authoritative evidence wins the budget, and inferred /
  assumption hits are dropped with the documented
  `authoritative_preference` reason. The budget pass truncates
  the lowest-ranked hits and records `budget_exhausted`
  drops. The conflict-detection pass surfaces hits whose
  `validTo` disagrees on the same chunk. The uncertainty pass
  flags hits with `KnowledgeState` in
  {`inferred`, `assumption`, `stale`, `unknown`,
  `conflicting`}.

## Adapter (`pi_platform/adapters/retrieval/context_assembler_adapter.py`)

- `ContextAssemblerAdapter` — registry-friendly wrapper around
  `ContextAssemblerCore`. The default adapter selected by
  `retrieval-status`; satisfies the §32 default-adapter
  scenario.

## Bundle ordering

The bundle hit order is deterministic for a fixed input. Two
consecutive calls with the same input return the same bundle
shape (hits, citations, droppedHits, explanations) within the
documented numerical tolerance. The deterministic ordering
guarantees the §32 "repeated assemble is deterministic"
scenario and supports the §49 evaluation-gate reproducibility
requirement.
