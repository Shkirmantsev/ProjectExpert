# 2026-10-12-integration-quality-gates Specification delta

Covers plan §28.3, §37.

## ADDED Requirements

### Requirement: retrieval-quality gate metrics

The integration quality gates MUST include the
following retrieval-quality metrics
(plan §28.3, §37):

- `Recall@5`, `Recall@10`;
- `MRR`, `NDCG`;
- `protected-hit retention`;
- `context evidence coverage`;
- `average context tokens`;
- `p50 / p95 query latency`;
- `peak RAM`;
- `embedding throughput`;
- `reranker throughput`;
- `cache reuse`;
- `branch-switch hydration time`.

The thresholds MUST be recorded in
`evals/quality_gates.yaml` and MUST be enforced by
the harness gate.

#### Scenario: harness gate enforces retrieval-quality thresholds

Given a retrieval quality regression
When the platform runs `python harness.py check`
Then the gate fails with a clear report
And the report names the regressed metric and the
configured threshold.

### Requirement: portable, offline, and CPU fallback quality gates

The integration quality gates MUST verify that the
platform:

- functions with no outbound network (offline);
- functions on CPU without GPU / accelerator;
- produces byte-identical rerank output for the
  `minimal` profile so the Tier 1 synthetic
  benchmark stays green;
- never silently mixes vector spaces from
  incompatible embedding profiles;
- never persists large float vectors as JSON;
- never stores large binary document assets in Git
  by default (CAS is the default);
- never lets the local LLM overwrite
  authoritative metadata.

#### Scenario: offline operation is tested

Given a network-disabled environment
When the platform runs the integration quality
gates
Then every gate passes without outbound network
And the model weights are loaded from local
storage only.

## MODIFIED Requirements

None. The existing integration-quality-gates
`Requirements` are extended additively; their
bodies are not rewritten.
