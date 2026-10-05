# graph-expansion Specification delta

Covers architecture section §73 (Graph Expansion in Multi-Stage
Retrieval) and §31 (Graph Expansion). This is a Phase 4 preview: the
capability ships the port contract and a stub default adapter that
documents the budget contract, but the production expansion algorithm
ships under the Phase 4 retrieval change.

The Phase 3 `sharded-graph` capability provides the `GraphPort` that
the expansion walks. The Phase 4 `multi-stage-retrieval` capability
composes the expansion alongside the dense ANN, the sparse index and
the reranker.

## ADDED Requirements

### Requirement: GraphExpansionPort contract

The platform MUST expose a `GraphExpansionPort` abstract class in
`pi_platform/ports/runtime/graph_expansion.py` with the following
operations:

- `expand(seeds: Sequence[str], *, hops: int = 1, edge_types:
  Optional[Sequence[str]] = None, budget: int = 100) ->
  GraphExpansion` where `GraphExpansion` lists
  `expandedEntities: Sequence[Entity]` and
  `expandedRelations: Sequence[Relation]`;
- `stats() -> Mapping[str, int]`.

#### Scenario: default expansion returns the seed entities

Given a `GraphExpansionPort` stub adapter
When `expand(["e-1"])` runs
Then the returned `expandedEntities` list contains `e-1`
And the returned `expandedRelations` list is empty
And the call respects the `budget` cap.

### Requirement: budget cap is enforced

The `GraphExpansionPort.expand` operation MUST honour the `budget`
parameter so a runaway expansion cannot exceed the documented cap.
When the budget is reached the expansion stops and returns the
partial result with a `budget_exhausted: True` flag.

#### Scenario: budget cap stops a runaway expansion

Given a graph with 1000 connected entities reachable from seed `e-1`
in 1 hop
When `expand(["e-1"], hops=1, budget=10)` runs
Then the expansion returns at most 10 entities
And the response carries `budget_exhausted: True`.

### Requirement: edge-type filter is honoured

The `GraphExpansionPort.expand` operation MUST honour the
`edge_types` parameter so an expansion can be restricted to a
specific relation family (`IMPLEMENTS`, `DEPENDS_ON`, `CALLS`, etc.).

#### Scenario: edge-type filter restricts the expansion

Given a graph where `e-1` has both `IMPLEMENTS` and `CALLS` relations
When `expand(["e-1"], edge_types=["IMPLEMENTS"])` runs
Then the returned relations list contains only `IMPLEMENTS` relations
And no `CALLS` relations are returned.

### Requirement: Phase 4 production adapter replacement

The Phase 4 implementation change MUST replace the Phase 3 stub
adapter with a production adapter that walks the canonical `GraphPort`
and applies the documented budget + edge-type filter rules.

#### Scenario: Phase 4 production adapter replaces the stub adapter

Given the Phase 3 port contract
When the Phase 4 implementation change ships
Then the production adapter implements the same port surface
And existing Phase 3 callers continue to work unchanged.

## Phase 3 task coverage

The change lists the Phase 4 preview port and stub adapter
(task 67b in `prepare-phase-3-storage/tasks.md`). Phase 4 task 73
implements the production expansion algorithm.

Out of scope:

- the production expansion algorithm — Phase 4 task 73
  (`GraphExpansion`);
- the dense ANN integration — Phase 4 task 70 (`EmbeddingModelPort`);
- the hybrid retrieval pipeline — Phase 4 task 71
  (`HybridRetrieval`);
- the multi-stage retrieval — Phase 4 task 72
  (`MultiStageRetrieval`);
- the reranker, metadata-driven filters, context assembler and
  retrieval benchmark — Phase 4 tasks 74-77.