---
id: adr.0028-usearch-as-default-ann-backend
title: USearch as configuration-driven ANN backend with disposable index lifecycle
kind: adr
status: accepted
date: 2026-10-16
summary: DenseIndexPort supports configuration-driven backend selection (auto, flat, usearch). USearch ANN files are disposable derived artefacts under .project-intelligence-cache/indexes/<embedding_profile_hash>/ and are rebuilt from VectorRecordStorePort without re-embedding when compatibility keys change.
related:
  - adr.0008-embedded-storage-selection
  - adr.0017-phase-8-enterprise-security-boundary
  - adr.0026-embedding-profile-identity-and-vector-namespace
  - interfaces.dense-index
  - interfaces.vector-record-store
  - modules.runtime-store
sourceRefs:
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#17
  - openspec/specs/2026-10-16-embedding-execution-profile/spec.md
  - pi_platform/adapters/runtime/usearch_dense_index.py
  - pi_platform/adapters/runtime/dense_index_backend.py
  - scripts/recall_vs_flat.py
maintenance:
  mode: authored
---

# ADR 0028 — USearch as configuration-driven ANN backend with disposable index lifecycle

## Context

`FlatDenseIndex` provides exact brute-force cosine search in memory, which is ideal for small corpora and deterministic CI tests, but scales linearly with corpus size. Larger repositories need an approximate nearest-neighbour (ANN) index behind the same `DenseIndexPort` contract without turning the ANN file into a primary source of truth or mixing incompatible embedding vector spaces.

## Decision

1. **Configuration-driven backend selection (`dense_index.backend ∈ {auto, flat, usearch}`).** `pi_platform/adapters/runtime/dense_index_backend.py` exposes `select_dense_index(...)`. Both `FlatDenseIndex` and `USearchDenseIndex` implement `DenseIndexPort`. `auto` selects between `FlatDenseIndex` and `USearchDenseIndex` based on corpus size and configured threshold rather than hard-coding a single backend.
2. **Disposable namespace under `.project-intelligence-cache/indexes/<embedding_profile_hash>/`.** Each ANN index is isolated by `embedding_profile_hash` and persists `index_meta.json` (`embedding_profile_hash`, `index_schema_version`, `source_generation`, `vector_count`).
3. **Rebuild without re-embedding.** Deleting the ANN directory or changing `index_schema_version` / `source_generation` rebuilds the index from `VectorRecordStorePort` (`SqliteVectorRecordStore`) BLOB records via `USearchDenseIndex.rebuild_from(...)` without invoking the embedding model.
4. **Recall verification.** `scripts/recall_vs_flat.py` measures ANN top-k recall against the `FlatDenseIndex` baseline.

## Consequences

- `FlatDenseIndex` remains the zero-dependency default for small corpora and Tier-1 tests.
- Incompatible embedding profiles can never share an ANN directory; opening a mismatched profile raises `ANNIndexError`.
- ANN files remain git-ignored derived cache state and can be safely deleted at any time.

[DenseIndexPort](../interfaces/dense-index.md) ·
[VectorRecordStorePort](../interfaces/vector-record-store.md) ·
[ADR 0026](0026-embedding-profile-identity-and-vector-namespace.md)
