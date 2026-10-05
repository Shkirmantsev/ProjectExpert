---
id: interfaces.hybrid-retrieval
title: HybridRetrievalPort contract
kind: interfaces
status: active
summary: Phase 4 §26/§27/§28 hybrid retrieval port — composition contract over the dense ANN, sparse BM25 and exact-identifier lookup.
sourceRefs:
  - pi_platform/ports/retrieval/hybrid_retrieval.py
  - pi_platform/core/retrieval/hybrid_retrieval.py
  - pi_platform/adapters/retrieval/hybrid_retrieval.py
  - pi_platform/adapters/retrieval/identifier_query_detector.py
  - openspec/specs/2026-10-04-hybrid-retrieval/spec.md
  - openspec/changes/implement-phase-4-retrieval/design.md
maintenance:
  mode: authored
related:
  - interfaces.reranker
  - modules.retrieval
  - adr.0010-hybrid-fusion-strategy
---

# HybridRetrievalPort contract

The §27 hybrid retrieval port composes the Phase 3
`SparseIndexPort`, `DenseIndexPort` and exact-identifier lookup
into a single ranked candidate set that the multi-stage
retrieval pipeline (task 72) consumes. The port is the cheapest
deterministic retrieval mechanism available to the §33 agent
access policy.

## Surface

- `query(text, *, top_k=50, dense_weight=0.5, sparse_weight=0.5,
  filters=None) -> Sequence[RetrievalHit]` — returns a fused
  candidate set of `RetrievalHit` records.
- `exact_id(identifier, *, filters=None) -> Sequence[RetrievalHit]`
  — identifier lookup that bypasses vector similarity and
  returns exact matches in `source="exact"` hits with score
  `1.0`.
- `stats() -> Mapping[str, int]` — operational counters
  including `calls`, `dense_calls`, `sparse_calls`, `exact_calls`
  and the `level` cost hint (always `0` for hybrid retrieval
  per the §33 escalation order).

## RetrievalHit

The `RetrievalHit` value type is the lingua-franca record
exchanged across every Phase 4 stage:

- `chunkId` (str) — the canonical chunk identifier (matches
  the Phase 1 `Chunk.id` field).
- `score` (float) — `0.0`–`1.0`; constructor validates the
  range.
- `source` (`"dense" | "sparse" | "exact" | "hybrid"`) — the
  stage that produced the hit.
- `snippet` (str) — the snippet string the context assembler
  and the MCP server render to the agent.
- `contentHash` (str) — the SHA-256 content address the Phase 1
  content-addressed-processing spec records.
- `metadata` (Metadata) — the Phase 1 `Metadata` record
  including language, validFrom, validTo, gitCommit,
  securityClassification, module, businessDomain,
  requirementId, etc.
- `knowledgeState` (KnowledgeState) — the Phase 1 / Phase 3
  `KnowledgeState` enum value.
- `tokenEstimate` (int) — non-negative token-equivalent budget
  estimate.
- `dropReason` (str) — the documented drop reason from
  `MetadataFilter` if the hit was filtered out.
- `evidenceWeight` (float) — `0.0`–`1.0`; the authoritative-
  evidence preference weight the context assembler consumes.

## Identifier recognition

The port MUST inspect every query for engineering identifiers
(`RpaVaryToteJpaMapper`, `PSB_FINISH_PACK`, `0x84721`,
`ILO-5193`, `GEN_3.0.03`) and route them to the exact-identifier
lookup when the identifier matches the
`IDENTIFIER_PATTERN` regex. The regex lives in
`pi_platform/core/retrieval/hybrid_retrieval.py` and is
exposed as `IDENTIFIER_GRAMMAR` for tests and the
`IdentifierQueryDetector` adapter.

The grammar covers four shapes:

- `0x[0-9A-Fa-f]+` — hex literals (`0x84721`).
- `[A-Z]+(?:_[A-Z0-9]+){1,}` — UPPER_SNAKE_CASE
  (`PSB_FINISH_PACK`, `GEN_3.0.03`).
- `[A-Z][A-Za-z0-9]{2,}-[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*` —
  KEBAB-CASE identifiers prefixed with a short uppercase stem
  (`ILO-5193`).
- `(?:[A-Z][a-z]+){3,}[A-Za-z0-9]*` — PascalCase with at
  least three components (`RpaVaryToteJpaMapper`).

The grammar is intentionally permissive enough to capture
canonical engineering identifiers without leaking into prose
(`FinishPack protocol message` is prose, not an identifier).

## Fusion strategy

The default fusion strategy is **reciprocal rank fusion (RRF)**
with `dense_weight=0.5, sparse_weight=0.5` defaults. The
strategy is replaceable through
`project-context.yaml:retrieval.fusion.strategy`; the
supported strategies are `rrf` (default) and `linear` (linear
weighted sum). The choice is recorded in
[`adr.0010-hybrid-fusion-strategy`](../adr/0010-hybrid-fusion-strategy.md).

## Production adapter

`pi_platform/adapters/retrieval/hybrid_retrieval.py` registers
`HybridRetrievalAdapter` as the production composition adapter
binding the Phase 3 `DenseIndexPort`, `SparseIndexPort` and
identifier-detection callable to the `HybridRetrievalCore`.
