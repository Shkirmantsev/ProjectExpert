---
id: architecture.retrieval-candidate-selection
title: Non-destructive candidate selection (PRIMARY / RESERVE / PROTECTED / SUPPORT)
kind: architecture
status: active
summary: Reranking is no longer a destructive top_k. The v0.8 refinement introduces a selection layer that keeps exact engineering identifiers, quoted phrases, target documents and target symbols alive across the reranker, and keeps a reserve pool that the Context Assembler can escalate from.
sourceRefs:
  - pi_platform/ports/retrieval/selection.py
  - pi_platform/core/retrieval/selection.py
  - pi_platform/ports/retrieval/multi_stage_retrieval.py
  - pi_platform/core/retrieval/multi_stage_retrieval.py
  - pi_platform/ports/retrieval/context_assembler.py
  - pi_platform/core/retrieval/context_assembler.py
  - openspec/specs/2026-10-16-retrieval-candidate-selection/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-hybrid-retrieval/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-multi-stage-retrieval/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-context-assembler/spec.md
  - adr.0025-rerank-direct-before-graph-expansion
maintenance:
  mode: authored
related:
  - modules.retrieval
  - modules.retrieval-trace
  - interfaces.selection
  - interfaces.hybrid-retrieval
  - interfaces.context-assembler
  - interfaces.reranker
---

# Non-destructive candidate selection

The v0.8 multi-stage pipeline ran
`direct → metadata → graph → hierarchy → merge → rerank → context`
in a single linear order. The reranker's `top_k` was
destructive: anything it undervalued was silently dropped,
including exact engineering identifiers (e.g. `ILO-5193`)
that the metadata-filter stage had decided to keep. Cross-
encoder rerankers also spent their budget on hundreds of
expansion nodes that did not have the same text shape as
direct chunks.

The v0.8 refinement replaces this with a three-stage
**rerank → select → support-expand** flow:

1. **Rerank** direct candidates only (no expansion nodes).
2. **Select** PRIMARY, RESERVE, PROTECTED with a per-
   candidate `CandidateTrace`.
3. **Expand** graph / hierarchy from the SELECTED primary /
   protected seeds; mark expanded nodes `SUPPORT`; never
   rerank them.

## Why it matters

Two concrete failure modes were closed:

- A parent section, figure caption, or implementation
  relation can no longer displace a verified direct passage.
- A protected exact hit (`ILO-5193`, `"FinishPack"`,
  `GEN_3.0.03`) survives the reranker unless a hard policy
  filter excludes it (wrong Git version, security denied,
  source explicitly excluded, invalid / stale runtime
  record).

## Stage order

The v2 twelve-stage order is the new contract:

```
1. query_analysis          (QueryFeatures)
2. candidate_generation    (hybrid retrieval)
3. metadata_filter         (version / security / Git / source)
4. fusion                  (RRF bookkeeping)
5. pre_rerank_pool         (cap to 48 direct candidates)
6. rerank_direct           (cross-encoder or BM25-light, direct only)
7. selection               (PRIMARY / RESERVE / PROTECTED)
8. graph_expansion         (from selected seeds; SupportEvidence)
9. hierarchy_expansion     (hops=2, edge_types=PART_OF; SupportEvidence)
10. support_marking        (bookkeeping)
11. context_assembly       (PRIMARY > PROTECTED > SUPPORT > RESERVE)
12. reserve_escalation     (bookkeeping; escalation inside the assembler)
```

The legacy 7-stage order remains available when no
`selection` port is wired and no `query_features` are
passed; the Tier-1 deterministic benchmark
(`tests/test_retrieval_benchmark`) continues to pass
byte-identically.

## Selection state machine

| State | Meaning | Survivor of rerank? | Source diversity cap? |
| --- | --- | --- | --- |
| `PRIMARY` | top direct answer | yes | yes (default 3 per source) |
| `RESERVE` | next-best direct answer | yes | no |
| `PROTECTED` | engineering identifier / quoted phrase / target document / target symbol | yes (unless hard policy filter) | no |
| `SUPPORT` | graph / hierarchy / table / figure / caption | n/a — added after selection | n/a |
| `DROPPED_DUPLICATE` | content-hash or chunk-id duplicate | yes (with `duplicate_of` link) | n/a |

`DROPPED_DUPLICATE` is not a silent loss: the
`duplicate_of` link in the `CandidateTrace` preserves the
provenance, and the Context Assembler's near-duplicate
collapse records `collapsed_into:` in `explanations`.

## Context Assembler evidence order

1. Protected direct evidence.
2. Authoritative PRIMARY evidence.
3. Other PRIMARY evidence.
4. Mandatory SUPPORT nodes.
5. Conflict-support evidence.
6. Reserve escalation for uncovered subtopics.
7. Optional additional SUPPORT.
8. Stop at the context budget.

## Mixed identifier + free-text queries

For `"Where is ILO-5193 implemented?"`:

- `QueryFeatures` extracts the identifier and flags
  `has_free_text = True`.
- The hybrid core runs dense + sparse + exact; the exact
  hit is marked `PROTECTED` on the way out of the hybrid
  port.
- The selection layer keeps the exact hit in the
  `PROTECTED` pool; the reranker cannot drop it.
- The Context Assembler places the protected hit before any
  `SUPPORT` node in the context bundle.

For pure `"ILO-5193"`:

- `QueryFeatures` extracts the identifier and flags
  `has_free_text = False`.
- The hybrid core takes the exact-only fast path; no
  dense / sparse calls.

## Tests

- `tests/test_selection.py` (5) — protected survival,
  reserve pool, source diversity, targeted document
  bypass, dedup provenance.
- `tests/test_pure_identifier_fast_path.py` (4) — dense /
  sparse call counts = 0 on the pure-ID path.
- `tests/test_mixed_identifier_hybrid_path.py` (5) — all
  four plan §4.1 cases.
- `tests/test_multi_stage_order.py` (6) — rerank not called
  on support, 12-stage order, legacy byte-identical, no
  `source="graph"` hits, `SupportEvidence` validation.
- `tests/test_context_assembler_selection.py` (4) —
  protected before support, legacy identical, dedup
  provenance, support hits populated.
- `tests/test_reserve_escalation.py` (2) — subtopic
  escalation, no escalation when budget exhausted.
- `tests/test_v2_production_wiring.py` — composition and
  CLI smoke tests.

[Retrieval trace](../modules/retrieval-trace.md) ·
[Selection port](../interfaces/selection.md) ·
[Hybrid retrieval](../interfaces/hybrid-retrieval.md) ·
[ADR 0025](../adr/0025-rerank-direct-before-graph-expansion.md)
