# context-assembler Specification delta

Covers architecture section §32 (Context Assembler). The
`ContextAssembler` port builds a bounded-context bundle from the
multi-stage retrieval pipeline output. The bundle deduplicates
overlapping evidence, enforces a context budget, preserves
citations, prefers authoritative evidence, surfaces conflicts and
exposes uncertainty.

The Phase 4 `multi-stage-retrieval` capability supplies the input
candidate set. The Phase 3 `provenance-state-model` capability
provides the `KnowledgeState` field used for authoritative-evidence
preference and uncertainty surfacing.

## ADDED Requirements

### Requirement: ContextAssemblerPort contract

The platform MUST expose a `ContextAssemblerPort` abstract class in
`pi_platform/ports/retrieval/context_assembler.py` with the
following operation:

- `assemble(hits: Sequence[RetrievalHit], *, contextBudget:
  ContextBudget, query: RetrievalQuery) -> ContextBundle` where
  `ContextBundle` carries `hits`, `dedupedEntities`,
  `citations`, `authoritativeHits`, `conflictingHits`,
  `uncertainHits`, `budgetUsed`, `droppedHits`, `dropReasons`,
  `explanations`.

#### Scenario: assembler returns a ContextBundle

Given a multi-stage pipeline result whose hits include one
authoritative, one conflicting, one uncertain and one duplicate
hit
When `assemble(hits, contextBudget=ContextBudget(...), query=...)`
runs
Then the returned `ContextBundle` lists the deduplicated hits
And the bundle separates authoritative, conflicting and uncertain
hits
And `budgetUsed` records the consumed token-equivalent budget.

### Requirement: deduplication

The `ContextAssemblerPort.assemble` operation MUST deduplicate hits
whose canonical chunk identifier, content hash or parent-chunk
identifier is shared. The deduplicated bundle MUST keep the
highest-ranked instance of each duplicate group and MUST record
the dropped duplicates under `droppedHits` with reason
`deduplicated`.

#### Scenario: duplicate hits are merged

Given a candidate set with three hits whose chunk identifier is
the same `c-1`
When `assemble(...)` runs
Then the returned bundle contains `c-1` once
And `droppedHits` lists the two duplicates with reason
`deduplicated`.

### Requirement: context budget enforcement

The `ContextAssemblerPort.assemble` operation MUST enforce the
`contextBudget` constraint. The bundle MUST never exceed the budget
and MUST surface the consumed budget under `budgetUsed`. The
budget unit MUST be the documented `token_estimate` field of each
hit and MUST be expressed in tokens or chunk-equivalents per the
future `design.md`.

#### Scenario: budget truncation drops the lowest-ranked hits

Given a candidate set of 100 hits and a `contextBudget` of
`token_estimate=2000`
When `assemble(...)` runs
Then the bundle keeps the highest-ranked hits whose cumulative
`token_estimate` does not exceed `2000`
And the dropped hits are recorded under `droppedHits` with reason
`budget_exhausted`.

### Requirement: citation preservation

The `ContextAssemblerPort.assemble` operation MUST preserve a
citation for every hit that survives deduplication and budget
enforcement. The citation MUST include the chunk identifier, the
content hash, the source document path, the project version and the
authoritative-evidence preference weight. Citations MUST be the
immutable shape that downstream MCP/A2A responses serialize to
agents.

#### Scenario: every surviving hit carries a citation

Given a candidate set of 10 hits
When `assemble(...)` runs
Then `len(citations) == len(bundle.hits)`
And every citation carries `chunkId`, `contentHash`,
`sourceReference`, `projectVersion` and `evidenceWeight`.

### Requirement: authoritative-evidence preference

The `ContextAssemblerPort.assemble` operation MUST prefer
authoritative evidence over inferred or assumed evidence when the
budget is binding. The preference MUST be based on the Phase 3
`KnowledgeState` field. Authoritative hits are those with
`KnowledgeState == "verified"` and provenance pointing at
human-authored or source-derived facts; inferred or assumed hits
are demoted but kept when no authoritative hit is available.

#### Scenario: authoritative hits win over inferred hits

Given a candidate set where one authoritative hit and one inferred
hit would together exceed the budget but only the authoritative
hit fits alone
When `assemble(...)` runs
Then the bundle keeps the authoritative hit
And the inferred hit is dropped with reason `authoritative_preference`.

### Requirement: conflict detection

The `ContextAssemblerPort.assemble` operation MUST detect conflicting
hits: two hits whose `chunkId` or `contentHash` differs but whose
textual content disagrees on a documented fact. The conflicting
pairs MUST appear under `conflictingHits` so the multi-stage
pipeline can surface them to the caller.

#### Scenario: conflicting hits are surfaced

Given a candidate set with two hits that disagree on a documented
fact (e.g. `validTo` differs)
When `assemble(...)` runs
Then `conflictingHits` lists both hits
And the bundle carries an explanation per conflicting pair
under `explanations`.

### Requirement: uncertainty surfacing

The `ContextAssemblerPort.assemble` operation MUST surface hits
whose `KnowledgeState` is `inferred`, `assumption`, `stale` or
`unknown` under `uncertainHits` so the multi-stage pipeline can
flag them to the agent. The uncertainty tags MUST be preserved
through the bundle to the caller.

#### Scenario: uncertain hits are flagged

Given a candidate set with one hit whose `KnowledgeState` is
`inferred`
When `assemble(...)` runs
Then `uncertainHits` includes that hit
And the hit's tag is preserved in the bundle.

### Requirement: deterministic bundle ordering

The `ContextAssemblerPort.assemble` operation MUST return a bundle
whose hit ordering is deterministic for a fixed input. Two
consecutive calls with the same input MUST return the same bundle
shape (hits, citations, droppedHits, explanations) within the
documented numerical tolerance.

#### Scenario: repeated assemble is deterministic

Given a `ContextAssemblerPort` instance and a stable input
When `assemble(input)` runs twice
Then both returned bundles list the same hits in the same order
And the consumed budget is identical.

## Phase 4 task coverage

The change covers Phase 4 task 76 (Context Assembler with dedup,
budget, citations, authoritative-evidence preference, conflict
detection, uncertainty surfacing). Task 72 (multi-stage retrieval)
composes the assembler as the final pipeline stage.

Out of scope:

- the embedding model — Phase 4 task 70 (`embedding-model`);
- the hybrid retrieval pipeline — Phase 4 task 71
  (`hybrid-retrieval`);
- the multi-stage pipeline composition — Phase 4 task 72
  (`multi-stage-retrieval`);
- the graph-expansion production implementation — Phase 4 task 73
  (`graph-expansion-production`);
- the reranker — Phase 4 task 74 (`reranker-port`);
- the metadata-driven filters — Phase 4 task 75
  (`metadata-filters`);
- the retrieval benchmark — Phase 4 task 77
  (`retrieval-benchmark`);
- the query orchestrator, local LLM, task context and capability
  discovery — Phase 5 tasks 79-83.