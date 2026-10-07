# graph-expansion-production Specification delta

Covers architecture section §31 (Graph Expansion) and the §29
multi-stage pipeline stage that consumes the expansion. This
capability closes the Phase 3 `graph-expansion` preview port with a
production implementation: bounded hops, edge-type filter, budget
enforcement and a clear separation from the §17 ANN graph.

The Phase 3 `sharded-graph` capability provides the canonical graph
index. The Phase 3 `graph-expansion` capability provides the
preview port contract (`expand(seeds, hops, edge_types, budget)`).
The Phase 4 `multi-stage-retrieval` capability composes the
production expansion into the pipeline.

## ADDED Requirements

### Requirement: production GraphExpansion adapter

The platform MUST register a production `GraphExpansionPort`
adapter in `pi_platform/adapters/runtime/graph_expansion.py` that
replaces the Phase 3 stub adapter. The production adapter MUST walk
the Phase 3 `GraphPort` (NOT the ANN graph) and apply the
documented `hops`, `edge_types` and `budget` parameters.

#### Scenario: production adapter replaces the Phase 3 stub

Given the Phase 3 stub adapter bound to a 50-entity canonical graph
When the production adapter replaces the stub adapter at startup
Then the production adapter is registered with the same
`GraphExpansionPort` surface
And `expand(seeds=["chunk-7.4.2"], hops=2, edge_types=["DESCRIBES",
"IMPLEMENTED_BY"], budget=10)` returns at most `10` expanded
entities
And the response carries `expandedEntities` and
`expandedRelations` lists.

### Requirement: bounded hops with depth-first budget enforcement

The production adapter MUST honour the `hops` parameter by limiting
the expansion to the documented depth. The `budget` parameter MUST
be enforced across the entire expansion so the adapter never
returns more entities than the budget allows.

#### Scenario: hops=0 returns only the seeds

Given a 50-entity canonical graph
When `expand(["e-1"], hops=0, budget=10)` runs
Then the returned `expandedEntities` list contains only `e-1`
And the returned `expandedRelations` list is empty.

#### Scenario: budget exhaustion is reported

Given a canonical graph where 100 entities are reachable from `e-1`
in 1 hop
When `expand(["e-1"], hops=1, budget=10)` runs
Then the adapter returns at most `10` expanded entities
And the response carries `budget_exhausted=True`.

### Requirement: edge-type filter is mandatory

The production adapter MUST honour the `edge_types` parameter so
the multi-stage pipeline can restrict the expansion to specific
relation families (`IMPLEMENTS`, `DEPENDS_ON`, `CALLS`, `DESCRIBES`,
`PART_OF`, `TESTED_BY`, etc.). When `edge_types` is `None` the
adapter MUST document the default edge-type set in the future
`design.md` and MUST NOT silently follow every edge type.

#### Scenario: edge-type filter restricts the expansion

Given a graph where `e-1` has `IMPLEMENTS` and `CALLS` outgoing
relations
When `expand(["e-1"], hops=2, edge_types=["IMPLEMENTS"],
budget=50)` runs
Then the returned relations list contains only `IMPLEMENTS`
relations
And no `CALLS` relations appear in the result.

#### Scenario: default edge-type set is applied when omitted

Given `edge_types=None`
When `expand(["e-1"], hops=1, budget=10)` runs
Then the adapter uses the documented default edge-type set
And `stats()` records the active edge-type set.

### Requirement: ANN graph vs knowledge graph separation

The production adapter MUST operate ONLY on the Phase 3 knowledge
graph. The adapter MUST NOT consult the ANN graph; the §17
invariant that ANN topology is not project semantics MUST hold.

#### Scenario: ANN graph queries do not leak into expansion

Given a `GraphExpansionPort` instance
When `expand(["e-1"], hops=1, edge_types=["DESCRIBES"], budget=10)`
runs
Then the call only reads from the `GraphPort`
And the adapter does NOT import the ANN backend package.

### Requirement: expansion follows the §31 DESCRIBES example

The production adapter MUST support the documented §31 expansion
example so the multi-stage pipeline can re-create the canonical
`Chunk → DESCRIBES → FinishPack → PART_OF → PackingProtocol →
IMPLEMENTED_BY → PackingService → DEFINED_BY → GEN_3.0.03 →
TESTED_BY → FinishPackIT` walk.

#### Scenario: §31 example walk returns the expected entities

Given a canonical graph that contains the §31 example entities and
relations
When
`expand(["chunk-7.4.2"], hops=3, edge_types=["DESCRIBES",
"PART_OF", "IMPLEMENTED_BY", "DEFINED_BY", "TESTED_BY"],
budget=10)`
runs
Then the expanded entities include `FinishPack`, `PackingProtocol`,
`PackingService`, `GEN_3.0.03` and `FinishPackIT`
And the expansion respects the budget
And the expanded relations include only the documented relation
families.

### Requirement: hierarchy expansion reuses the expansion port

The multi-stage pipeline's "hierarchy expansion" stage (§29 step 5) MUST reuse the same `GraphExpansionPort` with `edge_types=["PART_OF"]` so the parent-document, parent-section and parent-chunk relationships are reachable without a second expansion implementation.

#### Scenario: hierarchy expansion reuses the same port

Given a chunk `c-1` whose parent section is `s-1` whose parent
document is `d-1`
When the multi-stage pipeline runs the hierarchy-expansion stage
with the same `GraphExpansionPort`
Then the expanded entities include `s-1` and `d-1`
And the expansion respects the configured
`hierarchyExpansionBudget`.

## Phase 4 task coverage

The change covers Phase 4 task 73 (Graph expansion + hierarchy
expansion production implementation). The Phase 3 `graph-expansion`
preview port remains a separate capability that this delta
consumes; this delta retires only the Phase 3 stub adapter, not the
preview port contract.

Out of scope:

- the embedding model and dense ANN integration — Phase 4 task 70
  (`embedding-model`);
- the hybrid retrieval pipeline — Phase 4 task 71
  (`hybrid-retrieval`);
- the multi-stage pipeline composition — Phase 4 task 72
  (`multi-stage-retrieval`);
- the reranker, metadata-driven filters and context assembler —
  Phase 4 tasks 74-76;
- the retrieval benchmark — Phase 4 task 77
  (`retrieval-benchmark`);
- the query orchestrator, local LLM, task context and capability
  discovery — Phase 5 tasks 79-83.