---
id: modules.retrieval-trace
title: RetrievalTrace for explainable retrieval
kind: modules
status: active
summary: Persistent, redacted, JSON-serialisable trace of every retrieval — query_features, candidate lists, fusion, reranker, selection, graph_expansion, hierarchy_expansion, budget decisions, and per-stage timings. Attached to RetrievalResult in debug / evaluation mode.
sourceRefs:
  - pi_platform/core/retrieval/retrieval_trace.py
  - pi_platform/core/retrieval/multi_stage_retrieval.py
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/retrieval-trace/spec.md
maintenance:
  mode: authored
related:
  - architecture.retrieval-candidate-selection
  - interfaces.selection
  - interfaces.secret-provider
  - modules.retrieval
---

# RetrievalTrace for explainable retrieval

The v0.8 refinement introduces a `RetrievalTrace` value
object attached to `RetrievalResult` that makes retrieval
failures debuggable. The trace is optional in the normal
API response, always available in debug / evaluation mode,
serialisable to JSON, visible in Control Plane diagnostics,
and safe against leaking secret metadata.

The type lives at
`pi_platform/core/retrieval/retrieval_trace.py`. The
`RetrievalTraceBuilder` accumulates section-by-section data
and the `to_json()` method produces a byte-stable JSON
representation.

## Shape

```python
@dataclass(frozen=True)
class RetrievalTrace:
    query_features: object = None
    active_filters: object = None
    exact_candidates: tuple[str, ...] = ()
    dense_candidates: tuple[str, ...] = ()
    sparse_candidates: tuple[str, ...] = ()
    fusion: object = None
    reranker: object = None
    selection: object = None
    graph_expansion: object = None
    hierarchy_expansion: object = None
    budget_decisions: tuple[str, ...] = ()
    timings: tuple[tuple[str, int], ...] = ()
```

`timings` is a sequence of `(stage_name, ms)` pairs
aggregated from the per-stage `StageReport.durationMs`
values.

## Optionality

`RetrievalConfig.include_trace` (or `RetrievalQuery.include_trace`)
controls attachment. The default is `False`; the v2 multi-
stage pipeline attaches the trace only when
`include_trace is True`. The legacy 7-stage path never
attaches a trace and never constructs a `RetrievalTrace`
(preserving byte-identical behaviour for the Tier-1
benchmark).

## Secret redaction

`to_json()` runs every string value through the existing
`SecretProviderPort.redact(value, *, context=...)` filter
before serialising. The provider is loaded lazily; when the
provider is genuinely unavailable, a `WARNING: secret_provider
unavailable` budget decision is prepended to the trace so
the absence is visible. The contract test
`test_trace_redacts_secret` asserts the secret is absent
from the serialised JSON in both the redaction-available
and the redaction-unavailable paths.

The redaction filter applies recursively to nested dicts
and lists, so secrets in
`query_features.extensions["nested"]["api_key"]` or in
list items are also redacted.

## Control Plane and MCP exposure

- Control Plane diagnostics expose the active query trace
  and the latest N traces for inspection.
- MCP `retrieve_context` tool output includes
  `retrieval_trace_id`.
- A debug-only MCP tool
  `project.get_retrieval_trace(trace_id)` returns the full
  redacted trace.

The platform never exposes raw internal DB access through
the trace.

## JSON serialisation

`to_json()` produces a byte-stable JSON encoding:

- sorted keys at every level
- compact separators `(",", ":")` for byte-stable output
- tuples → lists, dataclasses → dicts, sets → sorted lists
- all string values run through the redaction filter
- any redaction-unavailable state is recorded as a
  `WARNING` budget decision

## v0.8 invariants preserved

- The legacy `RetrievalResult` shape is unchanged when
  `include_trace is False` (no new field appears).
- Secret redaction uses the existing
  `SecretProviderPort.redact(value, *, context=...)` API; no
  new redaction surface is invented.
- The trace is runtime / evaluation state; it is not
  committed to canonical Git knowledge.

## Tests

- `tests/test_retrieval_trace.py` (5+3 tests after
  MAJOR-1 fix) — JSON round-trip, secret redaction
  (provider-aware), secret redaction in nested dict, secret
  redaction in list, omitted by default, present with
  `include_trace=True`, timings present, WARNING
  budget decision when provider unavailable.

[Retrieval candidate selection](../architecture/retrieval-candidate-selection.md) ·
[Selection port](../interfaces/selection.md) ·
[Secret provider](secret-provider.md)
