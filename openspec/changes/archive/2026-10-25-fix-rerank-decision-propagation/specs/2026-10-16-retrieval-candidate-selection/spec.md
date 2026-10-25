## MODIFIED Requirements

### Requirement: candidate selection states

The platform MUST define a `SelectionState` enum
(`PRIMARY`, `RESERVE`, `PROTECTED`, `SUPPORT`,
`DROPPED_DUPLICATE`). The selection is performed after
rerank, before graph / hierarchy expansion. The selection
state is a runtime value, persisted as part of the
retrieval trace; it MUST NOT be committed to canonical
Git knowledge.

The selection MUST order the candidates by the rerank decision: a
candidate that was reranked MUST be ordered by its rerank rank, and a
candidate that was never reranked MUST keep the retrieval-score order
and follow the reranked group.

#### Scenario: rerank output is non-destructive

Given 100 direct candidates that survive the rerank
When the platform runs the selection
Then at least 8 candidates are tagged `PRIMARY`
And at least 24 are retained as `RESERVE`
And no candidate is silently lost unless it is
`DROPPED_DUPLICATE`.

#### Scenario: the selection honours the rerank decision

Given two candidates where the reranker ranked the second one first
When the platform runs the selection
Then the candidate the reranker ranked first is selected first
And the selection does not re-sort the candidates by their retrieval score

#### Scenario: the rerank decision is traceable

Given a candidate that was reranked
When the platform records the per-candidate trace
Then the trace records the rerank score and the rerank rank of that
candidate
