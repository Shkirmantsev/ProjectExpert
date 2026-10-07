---
id: interfaces.full-text-index
title: FullTextIndexPort interface
kind: interfaces
status: active
summary: Secondary full-text index port.
sourceRefs:
  - pi_platform/ports/runtime/full_text_index.py
  - pi_platform/adapters/runtime/sqlite_fts_full_text_index.py
maintenance:
  mode: authored
---

# FullTextIndexPort

The `FullTextIndexPort` abstract class exposes a secondary
full-text index (FTS5 / LIKE-style ranking) over the chunks and
entities, behind a port that the Phase 4 `HybridRetrieval` pipeline
composes alongside the `SparseIndex` and `DenseIndex`.

## Operations

- `index_document(family, documentId, text, metadata)`.
- `delete_document(documentId)`.
- `query(text, top_k=10)` — return `FullTextHit` records.
- `stats()`.

## Default adapter

`SqliteFtsFullTextIndex` (SQLite FTS5; reuses the SQLite backend
from the `RuntimeStore`). No extra dependency.

## Separation from SparseIndex

The full-text index is intentionally distinct from the sparse index:
the sparse index exposes BM25-style ranking with chunk metadata
awareness; the full-text index exposes substring / FTS5-style
ranking. The two ports can be composed by the Phase 4
`HybridRetrieval` pipeline.