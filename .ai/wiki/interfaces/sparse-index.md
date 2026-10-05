---
id: interfaces.sparse-index
title: SparseIndexPort interface
kind: interfaces
status: active
summary: BM25 sparse index port.
sourceRefs:
  - pi_platform/ports/runtime/sparse_index.py
  - pi_platform/adapters/runtime/bm25_sparse_index.py
maintenance:
  mode: authored
---

# SparseIndexPort

The `SparseIndexPort` abstract class exposes BM25-style ranking
over the chunks and entities, behind a port that the Phase 4
`HybridRetrieval` pipeline composes alongside the `DenseIndex` and
`FullTextIndex`.

## Operations

- `index_document(family, documentId, text, metadata)` — add or
  replace the document's BM25 contribution.
- `delete_document(documentId)` — drop the document.
- `query(text, top_k=10, metadata=None)` — return `SparseHit`
  records ordered by descending score.
- `stats()` — return `documents`, `terms`, `bytes`.

## Default adapter

`Bm25SparseIndex` (in-process BM25; no extra dependency). The
adapter applies metadata-aware scoring per the
`sparse-index` spec.

## Identifier-friendly retrieval

The port reliably retrieves engineering identifiers
(`GEN_3.0.03`, `ILO-5193`, `RpaVaryToteJpaMapper`,
`PSB_FINISH_PACK`, `0x84721`) through the BM25 ranking without
treating them as stopwords.