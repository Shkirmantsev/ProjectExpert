# 2026-10-04-retrieval-benchmark Specification delta

Covers plan §28, §28.1, §28.2, §28.3, §28.4, §29.

## ADDED Requirements

### Requirement: three evaluation tiers

The platform MUST support three evaluation tiers:

- **Tier 1** — deterministic synthetic CI benchmark
  (existing), no downloaded models, runs on every PR;
- **Tier 2** — local model integration tier
  (`@pytest.mark.local_model`,
  `@pytest.mark.pdf`, `@pytest.mark.slow`),
  exercising the real tokenizer, embedding model,
  reranker, FTS, ANN, and PDF fixtures; opt-in;
- **Tier 3** — `project-intelligence eval retrieval`
  command with `evals/corpus/{synthetic,
  generated-pdf, multilingual, java, requirements}/`
  and `evals/corpus/golden_queries.yaml`.

#### Scenario: Tier 1 remains dependency-light

Given a fresh CI runner with no optional
dependencies
When the platform runs `make eval-baseline`
Then Tier 1 passes
And no embedding model or reranker is downloaded.

#### Scenario: Tier 2 runs on a developer machine

Given a developer machine with
`semantic-embeddings` and `ann` optional
dependencies installed
When the developer runs
`pytest -m local_model`
Then the Tier 2 tests pass
And a real embedding model produces real vectors.

### Requirement: evaluation metrics and chunk-size sweep

The `project-intelligence eval retrieval` command
MUST output at least the following metrics
(plan §28.3): `Recall@5`, `Recall@10`, `MRR`,
`NDCG`, `protected-hit retention`, `context
evidence coverage`, `average context tokens`,
`p50 / p95 latency`, `peak RAM`, `embedding
throughput`, `reranker throughput`, `cache reuse`,
`branch-switch hydration time`.

The platform MUST also support a chunk-size sweep
over `512 / 768 / 900 / 1200` token budgets on
multilingual, requirements, English protocol, Java,
mixed code / business, and tables sub-corpora
(plan §28.4). The selected default MUST be recorded
in `evals/reports/chunk_size_sweep.md` and
cross-referenced from the embedding ADR.

#### Scenario: chunk-size sweep picks the best budget

Given a multilingual sub-corpus
When the platform runs the chunk-size sweep
Then the report shows Recall@10 for each of
`512 / 768 / 900 / 1200` token budgets
And the report records the selected default
And the report is cross-referenced from the
embedding ADR.

### Requirement: corpus layout

The platform MUST support the corpus layout
`evals/corpus/{synthetic, generated-pdf,
multilingual, java, requirements}/` and a
`golden_queries.yaml` per profile. Confidential
internal corpora MUST be supported under the
git-ignored `tmp/local/evals/` path with the same
evaluator.

#### Scenario: confidential corpus is git-ignored

Given a developer populating
`tmp/local/evals/`
When the developer runs the evaluator
Then the same `project-intelligence eval
retrieval` command runs against the
confidential corpus
And the path is not committed to Git.

## MODIFIED Requirements

None. The existing retrieval-benchmark
`Requirements` are extended additively; their
bodies are not rewritten.
