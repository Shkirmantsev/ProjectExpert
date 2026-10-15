---
id: interfaces.selection
title: SelectionPort contract
kind: interfaces
status: active
summary: Non-destructive candidate selection port (PRIMARY / RESERVE / PROTECTED / SUPPORT / DROPPED_DUPLICATE) introduced by the v0.8 refinement.
sourceRefs:
  - pi_platform/ports/retrieval/selection.py
  - pi_platform/core/retrieval/selection.py
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/retrieval-candidate-selection/spec.md
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/2026-10-04-multi-stage-retrieval/spec.md
  - adr.0025-rerank-direct-before-graph-expansion
maintenance:
  mode: authored
related:
  - interfaces.hybrid-retrieval
  - interfaces.reranker
  - interfaces.context-assembler
  - modules.retrieval
---

# SelectionPort contract

The v0.8 refinement reranks the direct candidate pool and then
hands the result to a `SelectionPort`. The selection layer is
the explicit, non-destructive counterpart to the reranker's
`top_k`: it produces `PRIMARY`, `RESERVE`, `PROTECTED`,
`SUPPORT` and `DROPPED_DUPLICATE` groups with a per-candidate
`CandidateTrace` so that no exact hit, no engineering identifier,
and no quoted phrase is ever silently lost.

The selection layer lives at
`pi_platform/ports/retrieval/selection.py` (port) and
`pi_platform/core/retrieval/selection.py` (core). The
`SelectionCore` implementation is stdlib-only.

## Surface

- `select(candidates, *, query_features, budget) -> SelectionResult` —
  consumes a sequence of `RetrievalHit` records, the
  `QueryFeatures` from A1, and an integer `budget`. Returns a
  `SelectionResult(primary, reserve, protected, support,
  dropped_duplicate, traces)`.

## SelectionState

```python
class SelectionState(str, Enum):
    PRIMARY = "PRIMARY"
    RESERVE = "RESERVE"
    PROTECTED = "PROTECTED"
    SUPPORT = "SUPPORT"
    DROPPED_DUPLICATE = "DROPPED_DUPLICATE"
```

`SelectionState` is a runtime value. It is persisted as part of
the retrieval trace (see `kb://modules/retrieval-trace`) and is
NEVER committed to canonical Git knowledge.

## CandidateTrace

A `CandidateTrace(chunk_id, dense_rank, sparse_rank, exact_match,
rrf_rank, rrf_score, rerank_rank, rerank_score, selection_state,
protected_reason, duplicate_of, source_document_id,
trace_reasons)` is emitted for every input candidate, including
the ones dropped as duplicates, so a failed retrieval is fully
replayable.

## Default budgets

```python
DEFAULT_PRIMARY_TOP_K = 8
DEFAULT_RESERVE_TOP_K = 24
DEFAULT_MAX_PRIMARY_PER_SOURCE = 3
```

The diversity cap is applied only to `PRIMARY`; the reserve pool
is uncapped. The cap is bypassed when `query_features.target_document`
is set (the user explicitly targets a specific document).

## Protected reasons

A candidate is `PROTECTED` when it matches any of:

- exact engineering identifier from `QueryFeatures.identifiers`
- quoted phrase from `QueryFeatures.quoted_phrases`
- target document id from `QueryFeatures.target_document`
- target symbol from `QueryFeatures.target_symbol`
- an upstream `RetrievalHit.selection_state == "PROTECTED"`
  (set by the hybrid core on the mixed identifier + free-text
  path; see `kb://interfaces/hybrid-retrieval`)

Protected candidates survive the reranker unless a hard policy
filter excludes them (wrong Git version, security denied, source
explicitly excluded, invalid / stale runtime record).

## v0.8 invariants preserved

- `RetrievalHit.source` enum is unchanged: `("dense", "sparse",
  "exact", "hybrid")`. Support items flow through the v2
  pipeline as `SupportEvidence` (see
  `adr.0025-rerank-direct-before-graph-expansion`).
- The selection layer is runtime / evaluation state. It is not
  committed to Git.
- The legacy 7-stage multi-stage path runs byte-identically
  when no `selection` port is wired.

## Tests

- `tests/test_selection.py` (5 tests) — protected survival,
  reserve pool survival, source diversity primary-only,
  targeted document bypass, dedup provenance.
- `tests/test_v2_production_wiring.py` — composition and CLI
  wiring smoke tests.

[Retrieval candidate selection](../architecture/retrieval-candidate-selection.md) ·
[Hybrid retrieval](hybrid-retrieval.md) ·
[Retrieval trace](../modules/retrieval-trace.md) ·
[ADR 0025](../adr/0025-rerank-direct-before-graph-expansion.md)
