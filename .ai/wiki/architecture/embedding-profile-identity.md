---
id: architecture.embedding-profile-identity
title: EmbeddingProfile identity and vector namespace lifecycle
kind: architecture
status: active
summary: Every embedded vector is namespaced by sha256(canonical(EmbeddingProfile)). Vector records are persisted as SQLite BLOBs in VectorRecordStorePort, while USearch/Flat ANN indexes are disposable per-profile caches.
sourceRefs:
  - pi_platform/ports/retrieval/embedding_profile.py
  - pi_platform/ports/runtime/vector_record_store.py
  - pi_platform/adapters/runtime/sqlite_vector_record_store.py
  - pi_platform/adapters/runtime/usearch_dense_index.py
  - openspec/specs/2026-10-16-embedding-execution-profile/spec.md
  - adr.0026-embedding-profile-identity-and-vector-namespace
  - adr.0028-usearch-as-default-ann-backend
maintenance:
  mode: authored
related:
  - adr.0026-embedding-profile-identity-and-vector-namespace
  - adr.0028-usearch-as-default-ann-backend
  - interfaces.embedding-profile
  - interfaces.vector-record-store
  - interfaces.dense-index
  - modules.embeddings
---

# EmbeddingProfile identity and vector namespace lifecycle

`EmbeddingProfile` (`pi_platform/ports/retrieval/embedding_profile.py`) defines the nine-field canonical identity for every embedding vector space (`provider`, `model_id`, `model_revision`, `modality`, `output_dimension`, `normalization`, `instruction_profile`, `tokenizer_id`, `strategy_version`).

## Built-in profiles

- `HASHING_DEFAULT` (`hashing`) — 384-dim L2-normalised deterministic hashing profile used by the `minimal` deployment profile and Tier-1 CI tests.
- `EMBEDDINGGEMMA2_512` (`embeddinggemma2`) — 512-dim L2-normalised local semantic profile.
- `QWEN3_EMBEDDING_0_6B_1024` (`qwen3-embedding-0.6b`) — 1024-dim L2-normalised evaluation profile.
- `MULTIMODAL_FIGURE_512` (`multimodal`) — 512-dim multimodal figure profile behind the `multimodal.figures` feature flag.

## Rebuild matrix

- **Unchanged `retrieval_text_hash` + same `embedding_profile_hash`** → reuse `VectorRecord` BLOB without model inference.
- **ANN cache missing or `index_schema_version` changed** → rebuild ANN from `SqliteVectorRecordStore` without re-embedding.
- **Active `EmbeddingProfile` changed** → open/populate the new `<embedding_profile_hash>` namespace; refuse mismatched namespaces with a redacted error.

[EmbeddingProfile contract](../interfaces/embedding-profile.md) ·
[VectorRecordStorePort](../interfaces/vector-record-store.md) ·
[ADR 0026](../adr/0026-embedding-profile-identity-and-vector-namespace.md)
