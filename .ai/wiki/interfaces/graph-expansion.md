---
id: interfaces.graph-expansion
title: GraphExpansionPort interface (Phase 4 preview)
kind: interfaces
status: draft
summary: Phase 4 preview port for bounded graph expansion.
sourceRefs:
  - pi_platform/ports/runtime/graph_expansion.py
  - pi_platform/adapters/runtime/bounded_graph_expansion.py
maintenance:
  mode: authored
---

# GraphExpansionPort (Phase 4 preview)

The `GraphExpansionPort` abstract class documents the Phase 4
graph-expansion preview. Phase 4 task 73 owns the production
implementation; Phase 3 ships the port contract and a stub default
adapter that documents the budget + edge-type rule.

## Operations

- `expand(seeds, *, hops=1, edge_types=None, budget=100)` — return
  a `GraphExpansion` with the seed entities, the expanded entities
  and the expanded relations.
- `stats()` — return an opaque stats dict.

## Budget contract

The port honours the `budget` parameter so a runaway expansion
cannot exceed the documented cap. When the budget is reached the
expansion stops and returns the partial result with a
`budget_exhausted: True` flag.

## Edge-type filter

The port honours the `edge_types` parameter so an expansion can be
restricted to a specific relation family (`IMPLEMENTS`,
`DEPENDS_ON`, `CALLS`, etc.).