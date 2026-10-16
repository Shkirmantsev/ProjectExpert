# 2026-10-04-hybrid-retrieval Specification delta

Covers plan §4.1.

## ADDED Requirements

### Requirement: QueryFeatures and routing

The platform MUST define a `QueryFeatures` value
object with `identifiers`, `quoted_phrases`,
`has_free_text`, `target_document`, `target_symbol`,
and `filters`. The `HybridRetrievalPort` MUST consume
`QueryFeatures` and route the query as follows:

- pure identifier (no free text) → exact-only fast
  path (no dense / sparse calls);
- identifier + meaningful prose → exact candidates
  marked `PROTECTED` AND dense candidates AND sparse
  candidates, then RRF / selection;
- free text only → dense + sparse + (if applicable)
  quoted-phrase `PROTECTED` candidates.

#### Scenario: pure identifier fast path

Given a query `"ILO-5193"` with `QueryFeatures` that
flags `has_free_text = false`
When the platform calls
`HybridRetrievalPort.query(...)`
Then no dense or sparse call is made
And the only candidates are exact-match candidates
with `source = "exact"`.

#### Scenario: mixed identifier + free text

Given a query
`"Where is ILO-5193 implemented?"` with `QueryFeatures`
that flags identifiers and `has_free_text = true`
When the platform calls `HybridRetrievalPort.query(...)`
Then exact-match candidates for `ILO-5193` are
marked `PROTECTED`
And dense and sparse calls also run
And the exact candidate survives the rerank in
`SelectionState.PRIMARY` or
`SelectionState.PROTECTED`.

## MODIFIED Requirements

None. The existing hybrid-retrieval `Requirements`
(`HybridRetrievalPort` contract, dense + sparse
fusion, exact identifier lookup bypass) are
preserved. The new `QueryFeatures` input is an
additive optional parameter; legacy callers continue
to work unchanged.
