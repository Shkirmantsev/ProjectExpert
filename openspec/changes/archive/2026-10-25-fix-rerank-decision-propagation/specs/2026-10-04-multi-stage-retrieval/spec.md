## MODIFIED Requirements

### Requirement: production stage order

The multi-stage retrieval pipeline MUST execute the following stages
in order when the eleven-stage v2 selection contract is wired:

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

A failing reranker MUST NOT fail the retrieval in ANY pipeline path:
the pipeline MUST keep the pre-rerank order and record the failure in
the rerank stage report.

#### Scenario: rerank runs before graph / hierarchy expansion

Given a candidate set that reaches the rerank stage
When the pipeline executes
Then the reranker sees only the DIRECT candidates
And the graph / hierarchy expansion runs after the selection

#### Scenario: a failing reranker does not fail the retrieval

Given a reranker that raises
When the pipeline executes the rerank stage
Then the retrieval still succeeds
And the stage report records the reranker failure
And the pre-rerank order is kept
