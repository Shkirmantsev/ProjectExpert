# 2026-10-04-hybrid-retrieval Specification

## Purpose
Combine sparse, dense, and exact identifier retrieval into ranked evidence with metadata filtering.
## Requirements
### Requirement: HybridRetrievalPort contract

The platform MUST expose a `HybridRetrievalPort` abstract class in
`pi_platform/ports/retrieval/hybrid_retrieval.py` with the
following operations:

- `query(text: str, *, top_k: int = 50, dense_weight: float = 0.5,
  sparse_weight: float = 0.5, filters: Optional[MetadataFilter] =
  None) -> Sequence[RetrievalHit]` where `RetrievalHit = (chunkId,
  score, source: Literal["dense", "sparse", "exact", "hybrid"],
  snippet)`;
- `exact_id(identifier, *, filters: Optional[MetadataFilter] =
  None) -> Sequence[RetrievalHit]` — identifier lookup that bypasses
  vector similarity and returns exact matches in `source="exact"`
  hits with score `1.0`;
- `stats() -> Mapping[str, int]` — return operational counters.

#### Scenario: hybrid query returns a fused candidate set

Given a chunk indexed by both the dense index and the sparse index
When `query("FinishPack protocol", top_k=10)` runs
Then the returned list contains the chunk exactly once
And the `source` field is `"hybrid"`
And the score is bounded between `0.0` and `1.0`.

#### Scenario: exact identifier lookup bypasses vector similarity

Given a chunk with identifier `GEN_3.0.03`
When `exact_id("GEN_3.0.03")` runs
Then the returned hits all have `source="exact"` and `score=1.0`
And no vector similarity comparison runs against the dense index.

### Requirement: dense + sparse fusion through one candidate set

The `HybridRetrievalPort.query` operation MUST compose the dense
ANN candidate generation, the BM25 sparse candidate generation and
the exact-identifier fallback into a single ranked candidate set.
The fusion algorithm MUST be replaceable through
`project-context.yaml:retrieval.fusion.strategy` and the default
strategy MUST be documented in the future `design.md`.

#### Scenario: fused ranking respects dense and sparse weights

Given a candidate set with one dense-only hit, one sparse-only hit
and one hybrid hit
When `query(...)` runs with `dense_weight=1.0, sparse_weight=0.0`
Then the ranking favours the dense-only hit and the hybrid hit over
the sparse-only hit
And when `dense_weight=0.0, sparse_weight=1.0` the order flips.

#### Scenario: fusion strategy is swappable through configuration

Given a `HybridRetrievalPort` implementation
When `project-context.yaml:retrieval.fusion.strategy` is set to a
strategy the implementation supports
Then the implementation uses the declared strategy for subsequent
queries
And `stats()` records the active strategy name.

### Requirement: identifier recognition before vector search

The `HybridRetrievalPort` MUST inspect every query for engineering
identifiers (`RpaVaryToteJpaMapper`, `PSB_FINISH_PACK`,
`0x84721`, `ILO-5193`, `GEN_3.0.03`) and route them to the
exact-identifier lookup when the identifier matches the
identifier-pattern grammar. Identifier queries MUST NOT silently fall
through to the dense path.

#### Scenario: engineering identifier routes to exact lookup

Given a query string that matches the identifier grammar
When `query(...)` runs
Then `stats()` records one `exact` lookup
And the returned hits all carry `source="exact"`.

#### Scenario: prose query uses dense + sparse fusion

Given a query string that does NOT match the identifier grammar
When `query(...)` runs
Then `stats()` records no `exact` lookup
And the returned hits carry `source="dense"`, `"sparse"` or
`"hybrid"` values only.

### Requirement: ANN candidate generation stays behind the dense port

The dense candidate generation stage MUST call the Phase 3
`DenseIndexPort`; the hybrid-retrieval port MUST NOT access the
ANN graph directly. The ANN backend (HNSW / flat / IVF) remains
configurable per §28 and the choice does NOT leak into the
`HybridRetrievalPort` surface.

#### Scenario: dense candidates come from the DenseIndexPort

Given a `HybridRetrievalPort` implementation
When `query(...)` runs
Then every `source="dense"` or `source="hybrid"` hit was retrieved
through `DenseIndexPort.query(...)`
And the hybrid port does NOT import the ANN backend package directly.

### Requirement: retrieval-first escalation before strong agent

The `HybridRetrievalPort` MUST be the cheapest deterministic
retrieval mechanism available to the agent access policy (§33
steps 1-4). The hybrid port MUST expose a `level: int` cost hint so
the future orchestrator (Phase 5) can prefer it over reranking,
graph expansion and LLM scanning.

#### Scenario: hybrid port reports its cost hint

Given a `HybridRetrievalPort` instance
When `stats()` runs
Then the response includes a `level` field whose value is documented
to be `0` (cheapest deterministic retrieval) and never below
`stats()["calls"]`.

