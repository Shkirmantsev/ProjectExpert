# 2026-10-07-mcp-server Specification delta (MODIFIED)

Covers plan §17, §28, §86 (PR 7, PR 8, PR 11 of §79).

## Purpose

Reconcile the accepted MCP server contract with the production
requirements that:

- the MCP retrieval tools fail closed with a structured
  refreshing or not-ready result while a branch reconciliation
  is in progress;
- the MCP retrieval tools and the web UI surface share the same
  `build_production_retrieval_runtime` composition;
- the MCP server does not expose a model switch capability to
  ordinary coding agents; only an administrator capability may
  switch the active embedding model.

This delta is **MODIFIED** (not ADDED); the existing tool
signatures and the JSON-RPC surface are preserved. New error
codes and a new authorisation gate are defined.

## MODIFIED Requirements

### Requirement: MCP retrieval tools fail closed during refresh

The MCP retrieval tools (`kb_search`, `kb_query`,
`task_context_build` and any future retrieval tool) MUST return
a structured `refreshing` or `not_ready` result while a
reconciliation is in progress. The tools MUST NOT serve the
previous branch evidence as if it were the current branch.

#### Scenario: kb_search returns refreshing during reconciliation

Given a reconciliation for the active project is in progress
When the MCP client calls `kb_search`
Then the response carries a structured `refreshing` result
And the previous branch evidence is not returned
And the response identifies the active refresh job identifier.

### Requirement: MCP retrieval uses the unified production composition

The MCP retrieval tools MUST be backed by the same
`build_production_retrieval_runtime` composition used by the
web UI. Two tool implementations with materially different
search semantics for the same query MUST NOT coexist.

#### Scenario: MCP and UI return identical results

Given the same query and the same runtime configuration
When the query is executed through `kb_search` and through the
web UI
Then both responses contain the same ranked candidates
And both responses carry equivalent retrieval metadata.

### Requirement: model switch is administrator-only

The MCP server MUST refuse a model switch request from a
client that does not carry the documented administrator
capability. The refusal MUST be a structured authorisation
error, not an opaque failure.

#### Scenario: ordinary agent cannot switch models

Given a client capability that is not the administrator
capability
When the client calls the model switch tool
Then the tool returns a structured authorisation error
And the active embedding profile is unchanged.
