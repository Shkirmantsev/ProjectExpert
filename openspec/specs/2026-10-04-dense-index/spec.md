# 2026-10-04-dense-index Specification

## Purpose
TBD - created by archiving change implement-phase-3-storage. Update Purpose after archive.
## Requirements
### Requirement: DenseIndexPort contract

The platform MUST expose a `DenseIndexPort` abstract class in
`pi_platform/ports/runtime/dense_index.py` with the following
operations:

- `index_chunk(chunkId: str, vector: Sequence[float], metadata:
  Mapping[str, object]) -> None`;
- `delete_chunk(chunkId: str) -> None`;
- `query(vector: Sequence[float], top_k: int = 10) ->
  Sequence[DenseHit]` where `DenseHit = (chunkId, score)`;
- `stats() -> Mapping[str, int]`.

#### Scenario: index round-trips a chunk embedding

Given a chunk with a 384-dimensional embedding
When the index stores the embedding and queries with the same vector
Then the index returns the chunk as the top-ranked hit with score
`1.0` (within numerical noise).

### Requirement: ANN graph vs. knowledge graph separation

The `DenseIndexPort` MUST operate only on the ANN graph (§17
invariant); the knowledge graph is owned by the `GraphPort`. The two
graphs MUST NOT be confused: the dense index has no notion of
`Entity` or `Relation` families; the graph has no notion of vector
similarity.

#### Scenario: knowledge graph entities are not visible from the dense index

Given an `Entity` whose `id` is `e-1`
When the dense index is queried with the entity's vector
Then the dense index does not return the entity as a hit
And the graph is queried separately to inspect the entity's relations.

### Requirement: backend selection through the port

The `DenseIndexPort` MUST be implementable by an HNSW default
adapter and a flat-search fallback adapter without leaking backend-
specific details into the port surface. The backend MUST be replaced
through the `project-context.yaml:storage.denseIndex.backend`
configuration value or the absence of the optional dependency.

#### Scenario: HNSW backend selection wires the HnswDenseIndex adapter

Given `project-context.yaml:storage.denseIndex.backend == "hnsw"`
and the HNSW dependency present
When the dense index is initialised
Then the index uses the `HnswDenseIndex` adapter.

#### Scenario: flat fallback activates when the HNSW dependency is absent

Given `project-context.yaml:storage.denseIndex.backend == "hnsw"`
and the HNSW dependency absent
When the dense index is initialised
Then the index uses the `FlatDenseIndex` fallback adapter
And `runtime-status` reports the active backend as `flat`.

### Requirement: idempotent indexing

The `DenseIndexPort.index_chunk` operation MUST be idempotent: a
second call with the same `chunkId` MUST replace the previous
embedding without producing duplicate hits.

#### Scenario: re-indexing a chunk does not duplicate hits

Given a chunk indexed once with vector `v1`
When the same chunk is re-indexed with vector `v2`
Then the index returns one hit for the chunk when queried with
`v2`
And the index returns zero hits when queried with `v1`.

### Requirement: delete propagates

The `DenseIndexPort.delete_chunk` operation MUST remove the chunk
from the index so subsequent queries do not return the deleted chunk
as a hit.

#### Scenario: deleting a chunk removes it from query results

Given a chunk indexed and visible to queries
When `delete_chunk(chunkId)` runs
Then the chunk is removed from the index
And subsequent queries do not return the chunk as a hit.

