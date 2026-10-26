# 2026-10-04-multi-stage-retrieval Specification delta (MODIFIED)

Covers plan §28, §86 (PR 7 of §79).

## Purpose

Reconcile the accepted seven-stage multi-stage retrieval contract
(`openspec/specs/2026-10-04-multi-stage-retrieval/spec.md`) with the
production stage order required by the unified production retrieval
composition: graph and hierarchy support evidence MUST be attached
after rerank and selection, not before rerank, so the reranker
budget is spent only on direct candidates and stale-branch support
nodes cannot displace fresh direct answers.

This delta is **MODIFIED** (not ADDED); the port signature and the
`RetrievalResult` shape are preserved. Only the internal stage order
and the per-stage evidence attachment are redefined.

## MODIFIED Requirements

### Requirement: production stage order

The multi-stage retrieval pipeline MUST execute the following stages
in order:

1. query analysis (`QueryFeatures`);
2. exact / dense / sparse candidate generation;
3. metadata / version / security filter projection;
4. RRF fusion;
5. pre-rerank direct candidate pool (cap = `pre_rerank_pool`,
   default 48);
6. cross-encoder / fallback rerank of DIRECT candidates only;
7. selection (`PRIMARY / RESERVE / PROTECTED`);
8. graph / hierarchy / figure / table expansion from selected
   primary / protected seeds;
9. mark expanded nodes `SUPPORT`;
10. context assembly with deduplication and citation preservation;
11. reserve escalation if needed.

The reranker MUST NOT be invoked on support nodes. The
`RetrievalResult.hits` shape is unchanged; support items are added
by the Context Assembler with their own `evidence_kind` and
`source` discriminator.

#### Scenario: rerank runs before graph / hierarchy expansion

Given a query that returns 60 direct candidates and 25 support
nodes that would be added by graph expansion
When `retrieve(...)` runs
Then the reranker receives 60 direct candidates
And the support nodes are attached only after the selection stage
And the reranker never sees the support nodes
And `stageReports` lists the eleven stages in the documented order.

#### Scenario: rerank is skipped when disabled

Given `enableReranking=False`
When `retrieve(...)` runs
Then `stageReports` lists ten entries (no rerank entry)
And `budgetUsed` records the rerank budget as zero.

#### Scenario: a failing reranker does not fail the retrieval

Given a reranker that raises
When the pipeline executes the rerank stage
Then the retrieval still succeeds
And the stage report records the reranker failure
And the pre-rerank order is kept

### Requirement: explicit budget per stage

The previous per-stage budget contract from
`openspec/specs/2026-10-04-multi-stage-retrieval/spec.md`
("explicit budget per stage") MUST be preserved without change.
Graph and hierarchy expansion budgets MUST still be respected; the
change is that those budgets are now spent on the post-selection
candidate set, not the pre-rerank candidate set.

#### Scenario: budget per stage is respected

Given the same configured per-stage budgets as in the accepted
spec
When `retrieve(...)` runs against a query that returns candidates
from every stage
Then `stageReports` reports the per-stage budget consumption
And no stage exceeds its configured budget
And the total consumed budget does NOT exceed `contextBudget`.

#### Scenario: budget exhaustion is reported

Given a configuration where candidate generation would yield
`10_000` candidates
When `retrieve(...)` runs with `candidateGenBudget=20`
Then the candidate stage is bounded to `20` candidates
And `stageReports[candidate].budget_exhausted == True`.

### Requirement: high recall + high precision principle

The principle "retrieval = high recall, reranking = high
precision" MUST be preserved. Reranking MUST continue to operate
on the direct candidate pool; the change is that the direct
candidate pool is the pre-rerank pool, not the
post-graph-expansion pool.

#### Scenario: recall is preserved before precision

Given a query whose ground-truth hits include candidates only
visible to the graph-expansion stage
When `retrieve(...)` runs with `enableReranking=False`
Then the returned `hits` include those graph-expansion candidates
And the pipeline reports `graphExpansionStage` as the source of
those hits.

### Requirement: stage-by-stage telemetry

The per-stage telemetry contract from the accepted spec MUST be
preserved without change. The expanded stage list MUST add
entries for `preRerankPool` and the post-selection graph /
hierarchy / figure / table expansion stages.

#### Scenario: stage telemetry reports candidates seen vs kept

Given the expanded stage list documented above
When the retrieval pipeline finishes
Then `stageReports` records one entry per stage in the documented
order
And every stage carries its configured budget consumption
And the new `preRerankPool` entry is visible alongside the
preserved per-stage entries

## REMOVED Requirements

None. The seven-stage order requirement is replaced (not removed)
by the production stage order above; all other requirements are
preserved.
