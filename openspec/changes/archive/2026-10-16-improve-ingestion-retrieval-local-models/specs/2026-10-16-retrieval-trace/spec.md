# retrieval-trace Specification delta

Covers plan §7, §33.

## Purpose

Define a `RetrievalTrace` typed value object attached to
`RetrievalResult` that makes retrieval failures
debuggable. The trace is optional in the normal API
response, always available in debug / evaluation mode,
serialisable to JSON, visible in Control Plane
diagnostics, and safe against leaking secret metadata.

## ADDED Requirements

### Requirement: RetrievalTrace shape

The platform MUST define `RetrievalTrace` with the
following fields:

- `query_features` — the analysed `QueryFeatures`;
- `active_filters` — the metadata / version /
  security filters actually applied;
- `exact_candidates` — the list of exact-match
  candidates considered;
- `dense_candidates` — the list of dense candidates
  considered;
- `sparse_candidates` — the list of sparse candidates
  considered;
- `fusion` — the RRF or other fusion stage result;
- `reranker` — the rerank stage result with timing
  and the active profile;
- `selection` — the selection stage result with
  per-candidate `CandidateTrace`;
- `graph_expansion` — the graph expansion stage
  result with timing and the seed ids;
- `hierarchy_expansion` — the hierarchy expansion
  stage result with timing;
- `budget_decisions` — the Context Assembler's
  budget decisions;
- `timings` — per-stage timings in milliseconds.

#### Scenario: trace includes all required sections

Given a successful retrieval
When the platform populates the `RetrievalTrace`
Then every required field is populated and serialises
to JSON.

### Requirement: trace serialisation and redaction

The `RetrievalTrace` MUST be serialisable to JSON in a
deterministic shape (sorted keys, stable array
ordering, no volatile data). Before serialisation, the
platform MUST run the trace through the existing
`pi_platform/security/secret_provider.py` redaction
filter; secret-bearing fields MUST be replaced with a
redaction marker.

#### Scenario: trace round-trips through JSON

Given a populated `RetrievalTrace`
When the trace is serialised to JSON and parsed back
Then the parsed trace is structurally equal to the
original (after redaction).

#### Scenario: secret metadata is redacted

Given a trace that includes a chunk whose
`extensions` map contains an `api_key` field
When the platform serialises the trace
Then the `api_key` field is replaced with the
redaction marker.

### Requirement: trace optionality and debug mode

The platform MUST gate normal-response trace attachment on
`RetrievalConfig.include_trace` (or `RetrievalQuery.include_trace`)
and MUST always make the trace available in debug and evaluation
modes.

#### Scenario: trace is omitted in the normal API response

Given `RetrievalConfig.include_trace = false`
When the platform returns the `RetrievalResult`
Then the `RetrievalTrace` is not attached.

#### Scenario: trace is always available in debug mode

Given `RetrievalConfig.include_trace = true` or
`debug_mode = true`
When the platform returns the `RetrievalResult`
Then the `RetrievalTrace` is attached.

### Requirement: Control Plane and MCP exposure

The platform MUST expose the trace through:

- the Control Plane diagnostics
  (`pi_platform/control/diagnostics/...`) — the
  active query trace and the latest N traces for
  inspection;
- the MCP `retrieve_context` tool output, which
  includes `retrieval_trace_id`;
- a debug-only MCP tool
  `project.get_retrieval_trace(trace_id)` that
  returns the full trace.

The platform MUST NOT expose raw internal DB access
through the trace.

#### Scenario: trace appears in Control Plane diagnostics

Given a successful retrieval with `trace_id = T-42`
When an operator opens Control Plane diagnostics
Then the latest traces list shows `T-42` and its
`query_features` summary.

#### Scenario: MCP tool returns the full trace

Given a debug MCP client
When the client calls
`project.get_retrieval_trace("T-42")`
Then the client receives the full redacted
`RetrievalTrace` for that id.

## MODIFIED Requirements

None. The existing multi-stage-retrieval and
capability-discovery `Requirements` are extended
additively; their bodies are not rewritten.
