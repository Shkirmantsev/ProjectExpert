## MODIFIED Requirements

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

A reranker MUST express its decision on the returned records: each
returned hit MUST carry the reranker's own score and its 1-based rank
in the reranker's ordering. The retrieval score of a hit MUST remain
unchanged so it stays available for fallback and diagnostics. A
reranker that does not attach its own scores MUST still have its
ordering recorded, because the order is itself the decision.

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

#### Scenario: the rerank decision is carried on the returned record

Given a candidate set of 50 `RetrievalHit` records
When `rerank(query, candidates, top_k=10)` runs
Then every returned record carries the reranker's own score
And every returned record carries its 1-based rank in the reranker order
And the retrieval score of every returned record is unchanged

### Requirement: reranker does not run when disabled

The `RerankerPort` MUST be optional in the pipeline. A query that
explicitly disables reranking, and a policy that disables reranking,
MUST bypass the rerank stage entirely and the pipeline MUST NOT
allocate a reranker instance.

The decision to rerank MUST be resolved from the operator policy and MAY
be overridden per query.

The policy MUST expose whether reranking is enabled, which family runs
it, how many candidates it may reorder, its timeout and what happens
when it fails. The platform MUST ship a BM25-light family that is
enabled by default.

A failing reranker MUST NOT fail the retrieval: the platform MUST keep
the pre-rerank order and record the failure, unless the operator
selected the mode that propagates the failure.

#### Scenario: reranker is bypassed when disabled

Given `enableReranking=False`
When the pipeline runs
Then no `RerankerPort.rerank(...)` call occurs
And `stageReports` does NOT list a `rerank` entry.

#### Scenario: reranking is active by default

Given a production deployment with the default policy
When a retrieval query runs
Then the reranker is invoked
And the reranked candidates keep the reranker's order in the result

#### Scenario: reranking can be switched off

Given a production deployment whose policy disables reranking
When a retrieval query runs
Then the reranker is not invoked
And the result keeps the fusion order

#### Scenario: a query may override the policy

Given a production deployment whose policy disables reranking
When a query explicitly requests reranking
Then the reranker is invoked for that query

#### Scenario: a failing reranker degrades to the pre-rerank order

Given a production deployment whose reranker fails
When a retrieval query runs
Then the retrieval succeeds
And the result keeps the pre-rerank order
And the failure is recorded in the stage report

#### Scenario: a text-only reranker does not demote a media candidate

Given a candidate that was embedded together with an image, a recording
or a clip
When the text reranker runs
Then that candidate is not scored by the text reranker
And it keeps its retrieval order relative to the other media candidates

## ADDED Requirements

### Requirement: reranking is controllable by the operator

The platform MUST let the operator control reranking through the
retrieval settings and the runtime configuration: whether it is
enabled, which family runs it, how many candidates it may reorder, its
timeout and its fallback behaviour.

The platform MUST NOT offer a neural reranker family as a production
option. The shipped production family is the cheap text family, because
the operator requires speed and the retrieval quality of the fusion
stage is not to be traded for a slow reranker.

#### Scenario: the operator switches reranking off

Given a deployment whose retrieval settings disable reranking
When the runtime configuration is resolved
Then the resolved configuration reports that reranking is disabled
And the retrieval pipeline does not invoke the reranker

#### Scenario: the configured family is the cheap text family

Given a deployment with the default retrieval settings
When the resolved reranking policy is inspected
Then the family is the BM25-light family
