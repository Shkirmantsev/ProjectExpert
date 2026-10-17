# 2026-10-04-multi-stage-retrieval Specification delta

Covers plan §4.2, §5, §7.

## ADDED Requirements

### Requirement: rerank direct candidates before graph / hierarchy expansion

The multi-stage retrieval pipeline MUST execute the
following stages in order:

1. query analysis (`QueryFeatures`);
2. exact / dense / sparse candidate generation;
3. metadata / version / security constraints;
4. RRF fusion;
5. pre-rerank direct candidate pool (cap =
   `pre_rerank_pool`, default 48);
6. cross-encoder / fallback rerank of DIRECT
   candidates only;
7. selection (`PRIMARY / RESERVE / PROTECTED`);
8. graph expansion from selected primary /
   protected seeds;
9. hierarchy / adjacent / figure / table expansion;
10. mark expanded nodes `SUPPORT`;
11. Context Assembly;
12. reserve escalation if needed.

The reranker MUST NOT be invoked on support nodes.
`RetrievalHit.source` remains
`dense | sparse | exact | hybrid`; support items are
added by the Context Assembler with their own
`evidence_kind`.

#### Scenario: rerank runs before graph expansion

Given a query with 60 direct candidates and 25
support nodes added by graph expansion
When the platform runs the pipeline
Then the reranker receives 60 candidates
And the support nodes are added only after the
selection stage
And the reranker never sees the support nodes.

### Requirement: RetrievalTrace attached to RetrievalResult

`RetrievalResult` MUST carry an optional
`RetrievalTrace` value object. The trace MUST be
populated by the pipeline, MUST be serialisable to
JSON, and MUST be redacted of secret metadata before
serialisation.

#### Scenario: trace is attached in debug mode

Given `RetrievalConfig.include_trace = true`
When the platform returns `RetrievalResult`
Then the result carries a populated
`RetrievalTrace`
And the trace includes the active `query_features`,
`active_filters`, the three candidate lists, the
fusion / rerank / selection / graph_expansion /
hierarchy_expansion / budget_decisions sections, and
the per-stage timings.

## MODIFIED Requirements

### Requirement: MultiStageRetrievalPort contract

The previous seven-stage contract is replaced by the
twelve-stage contract above. The
`MultiStageRetrievalPort.retrieve(...)` operation
preserves its existing signature; the change is in
the internal stage order. The `RetrievalResult`
gains an additive optional `trace` field.

This modification is an additive clarification of
internal stage semantics, not a change to the
external contract surface.
