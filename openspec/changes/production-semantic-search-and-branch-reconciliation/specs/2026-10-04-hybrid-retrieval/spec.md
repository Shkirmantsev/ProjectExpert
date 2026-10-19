# 2026-10-04-hybrid-retrieval Specification delta (MODIFIED)

Covers plan §28, §27 (PR 7 of §79).

## Purpose

Reconcile the accepted hybrid retrieval contract with the
production composition requirement that the dense, sparse and
exact channels MUST be queried against the same persistent
runtime state and fused through RRF before the rerank stage runs.
The hash-scan dense fallback used in the legacy UI composition
MUST be removed from any production retrieval path.

This delta is **MODIFIED** (not ADDED); the existing port
signature and result types are preserved. Only the dense
candidate generation and the UI composition contract are
redefined.

## MODIFIED Requirements

### Requirement: dense channel goes through the persistent semantic index

The hybrid retrieval port MUST source dense candidates from the
persistent semantic index and the active dense backend, not from
a per-request hash of the corpus. The port MUST accept an
injected `DenseIndexPort` and MUST refuse to operate if the
injected backend reports a stub status.

#### Scenario: legacy hash-scan dense path is removed

Given a production composition built by
`build_production_retrieval_runtime`
When the hybrid retrieval port runs
Then the dense channel queries the active persistent dense
backend
And the port does NOT hash any corpus item at query time.

#### Scenario: stub dense backend is rejected (replaces previous "flat fallback allowed" behavior)

Given a dense backend whose `stats()["backend"]` ends with
`"-stub"`
When the hybrid retrieval port is constructed
Then construction fails with a structured configuration error
And no production retrieval request is served.

### Requirement: UI and MCP share one composition

The hybrid retrieval port MUST be reachable through exactly one
composition function (`build_production_retrieval_runtime`) used
by the web UI, the MCP server, the CLI and the evaluation
harness. Two consumers MUST NOT maintain materially different
dense / sparse / exact configurations for the same project
version.

#### Scenario: UI and MCP return identical results (replaces previous "UI uses flat composition" behavior)

Given the same query text and the same runtime configuration
When the query is executed through the web UI and through the
MCP server
Then both responses contain the same ranked dense candidates
And the dense backend is the same persistent semantic index in
both responses.
