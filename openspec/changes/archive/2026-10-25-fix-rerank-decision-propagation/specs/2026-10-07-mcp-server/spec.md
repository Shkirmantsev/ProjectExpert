## ADDED Requirements

### Requirement: the caller may control reranking per query

The MCP retrieval tools MUST let the caller override the operator
reranking policy for a single query. The override MUST NOT change the
configured policy for any other query.

#### Scenario: the caller enables reranking for one query

Given a deployment whose policy disables reranking
When the caller asks the MCP retrieval tool for reranking
Then the query is executed with reranking enabled
And the configured policy is unchanged

#### Scenario: the caller disables reranking for one query

Given a deployment whose policy enables reranking
When the caller asks the MCP retrieval tool not to rerank
Then the query is executed without reranking
And the configured policy is unchanged
