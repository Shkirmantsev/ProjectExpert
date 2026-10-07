# 2026-10-04-reranker-port Specification

## Purpose
Provide a replaceable reranking interface to score and reorder retrieval candidates while reporting model and license identity.
## Requirements
### Requirement: RerankerPort contract

The platform MUST expose a `RerankerPort` abstract class in
`pi_platform/ports/retrieval/reranker.py` with the following
operations:

- `rerank(query: str, candidates: Sequence[RetrievalHit], *,
  top_k: int = 10) -> Sequence[RetrievalHit]` — return the same
  `RetrievalHit` records reordered and truncated so the top `top_k`
  hits are the highest-scoring per the reranker;
- `score(query: str, candidate: RetrievalHit) -> float` — return a
  reranker score for a single candidate;
- `model_version() -> str` — return the opaque reranker-version
  string the platform records for capability discovery;
- `license_id() -> str` — return the SPDX identifier of the
  reranker model and runtime (see §5.4 model-license inventory);
- `stats() -> Mapping[str, int]` — return operational counters.

#### Scenario: rerank reorders and truncates

Given a candidate set of 50 `RetrievalHit` records
When `rerank(query, candidates, top_k=10)` runs
Then the returned list has exactly `10` records
And the records are a subsequence of the input candidates
And the order is the reranker order (not the input order).

#### Scenario: rerank score is bounded

Given any `RetrievalHit` record
When `score(query, candidate)` runs
Then the returned score is a finite float
And the score is monotonically increasing with the reranker's
internal confidence.

### Requirement: bounded candidate set invariant

The `RerankerPort` MUST be designed to operate on bounded
candidate sets only. The multi-stage pipeline MUST enforce a
`rerankBudget` cap so a runaway candidate set never reaches the
reranker; the reranker MUST NOT be required to scale to the entire
corpus.

#### Scenario: rerankBudget is enforced by the pipeline

Given a `MultiStageRetrievalPort` instance configured with
`rerankBudget=20`
When the pipeline produces `100` candidates before the rerank stage
Then the reranker receives at most `20` candidates
And the remaining candidates are dropped with `budget_exhausted=True`
on the rerank stage entry.

### Requirement: pluggable reranker families

The `RerankerPort` MUST support one or more reranker families
through the same port surface. Supported families MAY include
cross-encoders, ColBERT-style late interaction, multi-vector
retrieval and lighter-weight rerankers. The active family MUST be
selected through `project-context.yaml:retrieval.reranker.family`
configuration.

#### Scenario: cross-encoder adapter registers

Given a `CrossEncoderReranker` adapter that implements the
`RerankerPort` surface
When `project-context.yaml:retrieval.reranker.family` is set to
`"cross-encoder"`
Then the pipeline binds the cross-encoder adapter
And `stats()` records the active family.

#### Scenario: lighter-weight reranker fallback

Given the cross-encoder adapter is unavailable (model not present,
GPU absent, or dependency missing)
When the pipeline initialises
Then the platform falls back to a lighter-weight reranker
(`"bm25-light"` or `"dense-only"` family)
And `stats()` records the active fallback family.

### Requirement: commercially-usable license

The `RerankerPort` adapter MUST use a reranker model and runtime
whose license satisfies the §5.1 preferred license policy OR the
§5.5 `LicenseGate` approval process for review-required licenses.
The model and runtime license SPDX identifiers MUST appear in
`distribution/licenses/dependency-inventory.json` before the
adapter is registered.

#### Scenario: LicenseGate blocks a non-commercial reranker

Given a proposed reranker adapter whose `license_id()` returns a
license containing `Non-Commercial` or `Research Only`
When `LicenseGate` runs
Then the gate fails with a clear message
And the adapter is NOT registered.

#### Scenario: preferred-license reranker is registered

Given a proposed reranker adapter whose `license_id()` returns
`Apache-2.0` or `MIT`
When `LicenseGate` runs
Then the gate passes
And the adapter is registered as the active reranker.

### Requirement: reranker does not run when disabled

The `RerankerPort` MUST be optional in the pipeline. The
`RetrievalQuery.enableReranking=False` path MUST bypass the rerank
stage entirely and the pipeline MUST NOT allocate a reranker
instance.

#### Scenario: reranker is bypassed when disabled

Given `enableReranking=False`
When the pipeline runs
Then no `RerankerPort.rerank(...)` call occurs
And `stageReports` does NOT list a `rerank` entry.

