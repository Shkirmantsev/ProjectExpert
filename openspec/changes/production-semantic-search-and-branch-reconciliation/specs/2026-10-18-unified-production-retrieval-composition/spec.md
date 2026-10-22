# unified-production-retrieval-composition Specification delta

Covers plan §27, §28 (PR 7 of §79).

## Purpose

Define the single production retrieval composition shared by the web
UI, the MCP server, the CLI and evaluation. One query is embedded once,
retrieved through exact, sparse and dense channels, fused, filtered,
reranked, selected, optionally expanded with graph support and
assembled into context. Two surfaces MUST NOT have materially different
search semantics for the same query and configuration.

## ADDED Requirements

### Requirement: one composition for all consumers

The platform MUST build the production retrieval stack through exactly
one composition used by the web UI, the MCP server, the CLI and
evaluation. Each consumer MUST receive the same retrieval services for
the same runtime configuration.

#### Scenario: single composition is used everywhere (verifies: one composition for all consumers)

Given the web UI, MCP server, CLI and evaluation harness
When each builds its retrieval stack
Then all four stacks are produced by the same composition entry point

### Requirement: same query same semantics

For the same query text and the same runtime configuration, the web UI
and the MCP server MUST return the same ranked retrieval results. The
platform MUST NOT maintain a separate UI-only search path with
different semantics.

#### Scenario: UI and MCP return identical results (verifies: same query same semantics)

Given the production runtime is ready and shared configuration
When the same query is executed through the web UI and through the MCP server
Then both responses contain the same ranked results
And both responses carry equivalent retrieval metadata

### Requirement: no hash-scan dense path

The platform MUST NOT compute dense similarity by hashing corpus items
at query time in any production retrieval path. Dense retrieval MUST
go through the persistent semantic index and the dense backend.

#### Scenario: UI no longer hashes the corpus (verifies: no hash-scan dense path)

Given a query executed through the web UI
When dense retrieval runs
Then the query is embedded once
And dense candidates come from the persistent semantic index

### Requirement: standard retrieval stage order

The platform MUST execute retrieval as: embed the query once, query
the dense, sparse and exact channels, fuse their candidates, apply
metadata filters, rerank, select candidates, attach graph support
evidence after reranking, and assemble context. Exact-match
candidates for identifier queries MAY keep the accepted protected
fast-path behaviour.

#### Scenario: stage order is stable (verifies: standard retrieval stage order)

Given a mixed free-text and identifier query
When retrieval executes
Then exact, sparse and dense candidates are fused before reranking
And graph support evidence is attached after reranking
And context assembly runs last

### Requirement: consistent readiness behaviour

All consumers MUST observe the same readiness contract: while the
runtime is not ready or a refresh is in progress, retrieval requests
MUST fail closed with a structured refreshing or not-ready result
instead of returning stale or partial data.

#### Scenario: consumers fail closed during refresh (verifies: consistent readiness behaviour)

Given a branch refresh is in progress
When the web UI and the MCP server receive retrieval requests
Then both fail closed with a refreshing or not-ready result
And neither serves stale branch data
