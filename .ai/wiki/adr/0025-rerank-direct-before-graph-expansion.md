---
id: adr.0025-rerank-direct-before-graph-expansion
title: Rerank direct evidence before graph / hierarchy expansion
kind: adr
status: accepted
date: 2026-10-14
summary: Reorder the multi-stage retrieval pipeline so the cross-encoder / BM25-light reranker runs on direct candidates only, before graph and hierarchy expansion. Direct candidates are reranked into PRIMARY / RESERVE / PROTECTED; expanded nodes are tagged SUPPORT and never compete for the reranker's CPU.
related:
  - adr.0004-ports-and-adapters-extension-style
  - adr.0010-hybrid-fusion-strategy
  - interfaces.hybrid-retrieval
  - interfaces.reranker
  - modules.retrieval
  - architecture.system-overview
sourceRefs:
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#4.2
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#41
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/2026-10-04-multi-stage-retrieval/spec.md
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/retrieval-candidate-selection/spec.md
  - pi_platform/ports/retrieval/multi_stage_retrieval.py
  - pi_platform/core/retrieval/multi_stage_retrieval.py
  - pi_platform/ports/retrieval/selection.py
  - pi_platform/core/retrieval/selection.py
maintenance:
  mode: authored
---

# ADR 0025 — Rerank direct evidence before graph / hierarchy expansion

## Context

The v0.8 multi-stage retrieval pipeline ran the seven stages
(`candidate_generation → fusion → metadata_filter → graph_expansion →
hierarchy_expansion → rerank → context_assembly`) in a single linear
order. The reranker therefore received direct candidates, graph
expansion nodes, and hierarchy expansion nodes mixed together, and
its top-`k` was destructive: anything it undervalued was silently
dropped, including exact engineering identifiers (e.g. `ILO-5193`)
that the metadata-filter stage had decided to keep.

Two concrete failure modes followed from this:

1. A figure caption, parent section, or implementation relation was
   frequently the reranker's top pick even when the best direct
   passage was a verified canonical requirement. The direct passage
   was displaced.
2. Cross-encoder rerankers (when bound) spent their budget on
   hundreds of expansion nodes that did not have the same text shape
   as direct chunks, distorting the score distribution and wasting
   CPU.

A second design issue compounded the first: `RetrievalHit.source`
allowed only `("dense", "sparse", "exact", "hybrid")`, while the
graph / hierarchy expansion code constructed hits with
`source="graph"` or `source="hierarchy"`, which the
`__post_init__` validation rejected. The v0.8 code masked this by
swallowing the resulting `ValueError` inside a try/except, leaving a
hidden contract violation.

## Decision

Reorder the multi-stage pipeline to the v0.8-refinement twelve-stage
order defined in `openspec/.../specs/2026-10-04-multi-stage-retrieval/spec.md`:

1. `query_analysis` — extract `QueryFeatures` (identifiers, quoted
   phrases, target document, target symbol, filters).
2. `candidate_generation` — hybrid retrieval.
3. `metadata_filter` — version / security / Git / source policy
   projection.
4. `fusion` — bookkeeping; the actual RRF fusion happened in step 2.
5. `pre_rerank_pool` — cap direct candidates to `pre_rerank_pool`
   (default 48) by score.
6. `rerank_direct` — cross-encoder or BM25-light rerank on DIRECT
   candidates only. On timeout or error, fall back to the RRF
   ordering.
7. `selection` — apply `SelectionCore` to produce `PRIMARY`,
   `RESERVE`, `PROTECTED` (and `DROPPED_DUPLICATE`) plus per-
   candidate `CandidateTrace`.
8. `graph_expansion` — expand the SELECTED primary / protected
   seeds only; wrap the resulting entities in the new
   `SupportEvidence` type, **not** in `RetrievalHit` with
   `source="graph"`.
9. `hierarchy_expansion` — same, with `hops=2` and
   `edge_types=["PART_OF"]`.
10. `support_marking` — bookkeeping.
11. `context_assembly` — feed `SelectionResult` and
    `SupportEvidence` into the selection-aware Context Assembler
    (see ADR 0024 and the `retrieval-candidate-selection` spec).
12. `reserve_escalation` — bookkeeping; the actual reserve
    escalation happens inside the Context Assembler when the budget
    is not exhausted.

The legacy 7-stage order remains available as the default when no
`selection` port is wired and no `query_features` are passed; the
v2 twelve-stage path activates only when the new ports are
configured. This preserves byte-identical behaviour for the
existing Tier-1 deterministic benchmark
(`tests/test_retrieval_benchmark`).

`RetrievalHit.source` remains the four-value enum
`("dense", "sparse", "exact", "hybrid")`. Support items are
represented by the new `SupportEvidence` dataclass (frozen;
`chunk_id`, `snippet`, `evidence_kind ∈ {graph, hierarchy, table,
figure}`, `score`, `source_document_id`, `page`, `element_id`),
which lives in the v2 multi-stage core and is passed to the
Context Assembler as a separate parameter.

## Consequences

Positive:

- Direct passages are no longer displaced by their own parent
  sections or neighbouring figure captions.
- Reranker CPU is spent on the candidates that actually answer
  the question.
- Protected exact candidates (engineering identifier, quoted
  phrase, target document, target symbol) survive reranking
  unless a hard policy filter excludes them; the selection layer
  keeps them in a separate `PROTECTED` pool.
- Reserve pool (up to 24 candidates) survives selection and can
  be escalated by the Context Assembler when the primary pool
  is exhausted or near-duplicate.
- `RetrievalHit.source` contract is no longer violated by
  graph / hierarchy expansion; `SupportEvidence` is the only
  path for support items.
- Retrieval failures are now debuggable: a persistent
  `RetrievalTrace` is attached to `RetrievalResult` (see the
  `retrieval-trace` spec).

Negative:

- The v2 pipeline is more complex. It is gated behind the
  `selection is not None` branch, so the legacy 7-stage path
  remains the fallback; the complexity is paid only when the
  new ports are wired.
- The Context Assembler must now consume a
  `SelectionResult` and a `SupportEvidence` list. This is
  additive — the existing `ContextAssemblerPort.assemble`
  signature gained two optional kwargs (`support_evidence=()`
  and `selection_result=None`) and the legacy path is
  byte-identical when both are not set.
- Operators must wire a `SelectionCore` in their composition
  layer (e.g. `pi_platform/adapters/ui/composition.py`,
  `pi_platform/cli/main.py`) for the v2 path to activate.

## Rollback

Disable the v2 path by removing the `selection=` argument from
the `MultiStageRetrievalCore` constructor calls in the
composition layer. The legacy 7-stage pipeline runs
byte-identically. No data migration is required.
