# 2026-10-16-retrieval-candidate-selection Specification

Covers plan §4.1, §4.2, §5, §5.1, §5.2, §5.3, §5.4, §6.

## Purpose

Define a non-destructive candidate selection layer that
stops treating reranking as a destructive `top_k`. The
selection layer is runtime / evaluation state; it is not
canonical Git knowledge. It introduces the
`SelectionState` enum
(`PRIMARY | RESERVE | PROTECTED | SUPPORT |
DROPPED_DUPLICATE`), the `CandidateTrace` value object,
the `SelectionPort`, the `DirectCandidate` /
`SupportEvidence` split, and the `PRIMARY > PROTECTED >
SUPPORT > RESERVE` evidence order in the Context
Assembler.

## Requirements

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

### Requirement: protected candidates

A candidate MUST be marked `PROTECTED` when it matches
any of the following: an exact engineering identifier,
a quoted phrase, an exact code symbol, an explicit
document ID, an explicit requirement ID, an explicit
heading, or a direct source request. A protected
candidate MUST survive reranking unless excluded by a
hard policy filter: wrong Git version, security denied,
source explicitly excluded, or invalid / stale runtime
record. Relevance ranking MUST NOT override
authorization / version correctness.

#### Scenario: protected exact hit survives rerank

Given a mixed query "Where is ILO-5193 implemented?"
with a `PROTECTED` exact hit and several semantic
candidates
When the platform runs hybrid retrieval and rerank
Then the `PROTECTED` exact hit appears in the assembled
context
Even if the reranker rates it below the soft source-
diversity threshold.

#### Scenario: policy filter overrides protected

Given a `PROTECTED` candidate whose Git revision does
not match the active project version
When the platform runs the selection
Then the candidate is excluded by the hard policy
filter and a clear reason is recorded in
`CandidateTrace.trace_reasons`.

### Requirement: reserve pool and escalation

The platform MUST retain the reserve pool after reranking. It is
escalated to the Context Assembler when any of the
following holds: the primary chunks are near-duplicates;
the answer has multiple subquestions; a needed source
type is absent; conflict verification requires more
evidence; the Context Assembler still has useful
budget; or an answer verifier requests more evidence.
The reserve pool MUST retain provenance and all ranking
scores.

#### Scenario: reserve escalates for multi-subquestion answer

Given a primary set of 8 candidates that cover only
one of three subquestions
When the Context Assembler runs
Then it pulls `RESERVE` candidates until all three
subquestions have at least one evidence link or the
context budget is exhausted.

### Requirement: source diversity (PRIMARY only)

The platform MUST apply a soft source diversity limit
only to `PRIMARY` candidates. The default
`max_primary_chunks_per_source` is 3. The limit MUST
NOT be applied when the user explicitly targets a
specific document. The limit MUST NOT be applied to
`RESERVE` candidates.

#### Scenario: source diversity limits primary but not reserve

Given a primary set where 5 chunks come from the same
source
When the platform runs the selection
Then at most 3 chunks from that source are `PRIMARY`
And the remaining 2 remain available as `RESERVE`.

#### Scenario: targeted document bypasses diversity

Given a user query that explicitly targets a specific
document
When the platform runs the selection
Then the `max_primary_chunks_per_source` limit is
not applied.

### Requirement: DirectCandidate and SupportEvidence split

The platform MUST distinguish `DirectCandidate` from
`SupportEvidence`. Rerankers MUST NOT see support
nodes; reranking is applied only to direct candidates.
`RetrievalHit.source` remains
`dense | sparse | exact | hybrid`; support items are
added by the Context Assembler with their own
`evidence_kind`.

#### Scenario: reranker is not invoked on support nodes

Given a query with 60 direct candidates and 25
support nodes added by graph expansion
When the platform runs the pipeline
Then the reranker receives 60 candidates, not 85.

### Requirement: Context Assembler evidence order

The Context Assembler MUST consume candidates in the
following order and stop at the context budget:

1. protected direct evidence;
2. authoritative `PRIMARY` evidence;
3. other `PRIMARY` evidence;
4. mandatory `SUPPORT` nodes;
5. conflict-support evidence;
6. reserve escalation for uncovered subtopics;
7. optional additional `SUPPORT`.

The Context Assembler MUST collapse near-duplicates by
normalised content hash / similarity while preserving
links to the collapsed equivalents; duplicate
provenance MUST NOT be discarded.

#### Scenario: protected evidence appears before support

Given a context budget of 1024 tokens
When the Context Assembler builds the context
Then protected direct evidence appears before any
`SUPPORT` node
And `RESERVE` candidates are only added if there is
remaining budget.
