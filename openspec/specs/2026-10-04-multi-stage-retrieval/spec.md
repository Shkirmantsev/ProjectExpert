# 2026-10-04-multi-stage-retrieval Specification

## Purpose
Coordinate candidate generation, fusion, filtering, graph expansion, reranking, and bounded context assembly with observable stage results.
## Requirements
### Requirement: MultiStageRetrievalPort contract

The platform MUST expose a `MultiStageRetrievalPort` abstract class
in `pi_platform/ports/retrieval/multi_stage_retrieval.py` with the
following operation:

- `retrieve(query: RetrievalQuery) -> RetrievalResult` where
  `RetrievalQuery` carries `text`, `top_k`, `contextBudget`,
  `filters`, `purpose`, `projectVersion` and `enableReranking`
  fields, and `RetrievalResult` carries `hits`,
  `contextBundle`, `stageReports`, `evictions`, `conflicts`,
  `uncertainties` and `budgetUsed`.

The pipeline MUST execute the seven documented stages in order:

1. candidate generation (cheap lexical + dense ANN + identifier
   lookup);
2. dense + sparse fusion into a single ranked candidate set;
3. metadata / version / security filter projection;
4. graph expansion;
5. hierarchy expansion;
6. reranking (only when `enableReranking` is true);
7. context assembly with deduplication and citation preservation.

#### Scenario: pipeline runs the seven stages

Given a `MultiStageRetrievalPort` instance configured with the
default budgets
When `retrieve(...)` runs against a query that returns candidates
from every stage
Then `stageReports` lists one entry per executed stage
And the entries appear in the documented order
And `budgetUsed` does NOT exceed the configured `contextBudget`.

#### Scenario: rerank is skipped when disabled

Given `enableReranking=False`
When `retrieve(...)` runs
Then `stageReports` lists six entries (no rerank entry)
And `budgetUsed` records the rerank budget as zero.

### Requirement: explicit budget per stage

The `MultiStageRetrievalPort` MUST expose a per-stage budget
configuration object. The default budgets MUST be documented in the
future `design.md`. The pipeline MUST respect the budget per stage
so a runaway stage does NOT starve the downstream stages.

#### Scenario: budget per stage is respected

Given a configured `candidateGenBudget=20`,
`fusionBudget=50`, `metadataFilterBudget=40`,
`graphExpansionBudget=30`, `hierarchyExpansionBudget=30`,
`rerankBudget=20`, `contextAssembleBudget=contextBudget`
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

The multi-stage pipeline MUST embody the §29 principle
`retrieval = high recall, reranking = high precision`. The
candidate generation, fusion, graph expansion and hierarchy
expansion stages MUST prioritise recall; the reranking and context
assembly stages MUST prioritise precision. The pipeline MUST NOT
sacrifice recall at the candidate generation stage for the sake of
precision.

#### Scenario: recall is preserved before precision

Given a query whose ground-truth hits include candidates only
visible to the graph-expansion stage
When `retrieve(...)` runs with `enableReranking=False`
Then the returned `hits` include those graph-expansion candidates
And the pipeline reports `graphExpansionStage` as the source of
those hits.

### Requirement: stage-by-stage telemetry

The `MultiStageRetrievalPort` MUST report per-stage telemetry:
candidates seen, candidates kept, time spent, budget consumed,
budget exhausted flag and any error. The future evaluation suite
(`retrieval-benchmark`) consumes this telemetry to assert the
documented latency, recall and precision targets.

#### Scenario: stage telemetry reports candidates seen vs kept

Given a configured pipeline
When `retrieve(...)` runs
Then every `stageReports` entry carries `{"in": int, "out": int,
"duration_ms": int, "budget_exhausted": bool}`
And `in >= out` for every stage.

### Requirement: deterministic ordering for the same query

The `MultiStageRetrievalPort` MUST return a deterministic hit
ordering for a fixed `RetrievalQuery` and a fixed project state. Two
consecutive calls with the same input MUST return the same hits in
the same order (with the documented numerical tolerance for the
scores). Non-determinism in the underlying ANN or reranker MUST be
disabled through explicit configuration.

#### Scenario: repeated query returns identical hit ordering

Given a `MultiStageRetrievalPort` instance and a stable project
state
When `retrieve(q1)` and `retrieve(q1)` run sequentially
Then the returned hit lists are identical
And `contextBundle.hits` are in the same order.

