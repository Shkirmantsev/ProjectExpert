---
id: interfaces.dense-index
title: DenseIndexPort interface
kind: interfaces
status: active
summary: ANN dense-vector index port.
sourceRefs:
  - pi_platform/ports/runtime/dense_index.py
  - pi_platform/adapters/runtime/flat_dense_index.py
maintenance:
  mode: authored
---

# DenseIndexPort

The `DenseIndexPort` abstract class exposes an ANN index over the
chunk embeddings, behind a port that the Phase 4 `HybridRetrieval`
pipeline composes alongside the `SparseIndex` and `FullTextIndex`.

## Operations

- `index_chunk(chunkId, vector, metadata)` — add or replace the
  chunk's embedding.
- `delete_chunk(chunkId)` — drop the chunk.
- `query(vector, top_k=10)` — return `DenseHit` records ordered by
  descending similarity.
- `stats()` — return `vectors`, `dim`.

## Default adapter

`FlatDenseIndex` (in-process cosine similarity; no extra
dependency). The HNSW adapter is the future opt-in backend gated
on the `hnswlib` dependency.

## ANN graph vs. knowledge graph

The `DenseIndexPort` only operates on the ANN graph (§17 invariant).
The knowledge graph is owned by the `GraphPort`. The two MUST NOT
be confused.