# retrieval-benchmark Specification delta

Covers architecture section §49 (Integration Quality Gates and
Evals). The `retrieval-benchmark` capability defines the evaluation
contract that the future `implement-phase-4-retrieval` change
implements in `tests/test_retrieval_benchmark.py`. The benchmark
records recall/precision, reranker quality, latency, cache reuse,
branch-switch hydration time, stale-knowledge detection and plugin
setup success rate against a fixed evaluation fixture. This change
ships the contract only; the future implementation change ships the
test code.

The Phase 4 `hybrid-retrieval`, `multi-stage-retrieval`,
`graph-expansion-production`, `reranker-port`,
`metadata-filters` and `context-assembler` capabilities supply the
pipeline stages that the benchmark exercises.

## ADDED Requirements

### Requirement: RetrievalBenchmark fixture contract

The platform MUST ship an evaluation fixture that the future
`implement-phase-4-retrieval` change materialises as
`tests/test_retrieval_benchmark.py`. The fixture MUST define:

- a fixed canonical corpus with at least `1_000` chunks and at
  least `100` knowledge-graph entities;
- a labelled query set with at least `100` queries, each with
  ground-truth hits, identifier queries and expectation tags
  (`identifier`, `semantic`, `graph_expansion`,
  `reranker_sensitive`, `conflict`, `stale`);
- per-query metrics for recall, precision, mean-reciprocal-rank
  and latency;
- cross-branch reuse scenarios that assert the same query on a
  branched fixture returns the same hits without rebuilding the
  index from scratch;
- a branch-switch hydration time assertion;
- a stale-knowledge detection assertion that flips one source and
  asserts the freshness tracker marks the affected hits stale;
- a plugin setup success rate assertion that records the success
  rate of the configured reranker / embedding / sparse adapter
  registrations.

#### Scenario: benchmark runs the labelled query set

Given the benchmark fixture and a stable runtime
When the benchmark executes the labelled query set
Then for every query the benchmark records `recall`, `precision`,
`mrr`, `latency_ms`, `cache_hit`, `branch_hydration_ms`,
`stale_detected` and `plugin_setup_ok`
And the benchmark reports the aggregate metrics under
`tests/test_retrieval_benchmark.py::test_aggregate_metrics`.

#### Scenario: identifier query uses the budget on cheap exact lookup

Given a query labelled `identifier`
When the benchmark executes it
Then the benchmark records `dense_calls=0`, `sparse_calls=0`,
`exact_calls=1` and `latency_ms <= cheap_lookup_budget`
And `recall == 1.0` (the identifier is always retrieved exactly).

#### Scenario: reranker-sensitive query uses the reranker stage

Given a query labelled `reranker_sensitive`
When the benchmark executes it with `enableReranking=True`
Then the benchmark records a `rerank_stage` entry under the
per-stage telemetry
And `precision_with_reranker >= precision_without_reranker`.

### Requirement: recall and precision targets

The benchmark MUST report aggregate recall and precision metrics
for the labelled query set. The future `design.md` records the
documented targets; the benchmark is the source of truth for
whether the pipeline meets them.

#### Scenario: aggregate recall and precision are reported

Given the benchmark fixture and a stable runtime
When the benchmark executes
Then the aggregate report lists `aggregate_recall`,
`aggregate_precision`, `aggregate_mrr`, `aggregate_latency_p50`,
`aggregate_latency_p95`, `aggregate_cache_hit_rate`
And the report is machine-readable (JSON or YAML).

### Requirement: cache reuse and branch-switch hydration

The benchmark MUST exercise the cross-branch reuse invariant
(§13 Content-Addressed Processing) and the branch-switch
hydration flow (§62 Startup / Branch-Switch Synchronization). The
benchmark MUST assert that switching the runtime to a branched
fixture reuses cached embeddings and indexes without rebuilding
from scratch.

#### Scenario: branch-switch hydration time is bounded

Given the benchmark fixture and a branched fixture
When the benchmark switches the runtime from the primary fixture
to the branched fixture
Then `branch_hydration_ms` is below the documented target
And the runtime reports cache hits for unchanged chunks.

### Requirement: stale-knowledge detection

The benchmark MUST flip a source artefact on the branched fixture
and assert that the freshness tracker marks the affected hits
stale. The benchmark MUST NOT require re-materialisation to detect
staleness; the runtime freshness tracker MUST surface the staleness
during the retrieval call.

#### Scenario: stale-knowledge detection surfaces staleness

Given a branched fixture with one flipped source artefact
When the benchmark runs the labelled query set on the branched
fixture
Then the per-query report records `stale_detected=True` for queries
that touch the flipped artefact
And the affected hits carry `KnowledgeState == "stale"`.

### Requirement: plugin setup success rate

The benchmark MUST record the success rate of the configured
embedding, sparse, dense, reranker, metadata filter and graph
expansion adapter registrations. The success rate is the ratio of
successful registrations over the total attempted registrations
across the benchmark fixture.

#### Scenario: plugin setup success rate is reported

Given the benchmark fixture and a configured runtime
When the benchmark initialises the runtime
Then the report records
`plugin_setup_total`, `plugin_setup_ok`, `plugin_setup_failed`
And `plugin_setup_ok / plugin_setup_total >= 0.95` (the documented
target).

### Requirement: benchmark is non-flaky

The benchmark MUST tolerate the documented numerical noise of the
embedding model, the BM25 scorer and the dense ANN index. The
benchmark MUST NOT fail spuriously due to floating-point ordering
or BM25 tie-breaking.

#### Scenario: repeated benchmark run is stable

Given the benchmark fixture and a stable runtime
When the benchmark runs twice consecutively
Then the aggregate `recall`, `precision`, `mrr` and `latency`
metrics are within the documented numerical tolerance
And no individual query case flips between pass and fail.

## Phase 4 task coverage

The change covers Phase 4 task 77 (Retrieval benchmark / evaluation
fixture). The fixture contract ships with this preparation change;
the production test code ships with the future
`implement-phase-4-retrieval` change.

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
- the context assembler — Phase 4 task 76 (`context-assembler`);
- the query orchestrator, local LLM, task context and capability
  discovery — Phase 5 tasks 79-83.