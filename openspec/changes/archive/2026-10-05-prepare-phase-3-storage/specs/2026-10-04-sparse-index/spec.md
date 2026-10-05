# sparse-index Specification delta

Covers architecture section §63 (Durable Knowledge Save / Commit
Flow — durable metadata index) and §26 (Sparse and Exact Retrieval).
The `SparseIndex` exposes BM25-style ranking over the chunks and
entities, behind a `SparseIndexPort` that the Phase 4
`HybridRetrieval` pipeline composes alongside the `DenseIndex` and
`FullTextIndex`.

The Phase 1 `canonical-knowledge-schema` capability provides the
SHA-256 content address that the sparse index uses as the document
primary key. The Phase 2 `semantic-structural-chunking` and
`context-enrichment` capabilities provide the chunks and entities
that the index is built from.

## ADDED Requirements

### Requirement: SparseIndexPort contract

The platform MUST expose a `SparseIndexPort` abstract class in
`pi_platform/ports/runtime/sparse_index.py` with the following
operations:

- `index_document(family: str, documentId: str, text: str,
  metadata: Mapping[str, object]) -> None` — add or replace the
  document's BM25 contribution;
- `delete_document(documentId: str) -> None` — drop the document
  from the index;
- `query(text: str, top_k: int = 10) -> Sequence[SparseHit]`
  where `SparseHit = (documentId, score, snippet)`;
- `stats() -> Mapping[str, int]` — returns
  `{"documents": ..., "terms": ..., "bytes": ...}`.

#### Scenario: warming up the index returns BM25-ranked hits

Given an index over three documents with distinct vocabulary
When the index receives a query that matches two of the documents
Then the index returns the higher-scoring document first
And the returned scores are positive and ordered descending.

### Requirement: metadata-aware scoring

The `SparseIndexPort` MUST apply metadata-aware scoring so that
document metadata (`family`, `businessDomain`, `language`,
`module`, `className`) acts as a queryable signal without breaking
the BM25 ranking.

#### Scenario: metadata-mismatched document ranks below matched document

Given two documents with identical BM25 scores for a query but
different `family` metadata (`markdown` vs. `pdf`)
When the index receives a query that prefers `markdown`
Then the `markdown` document ranks above the `pdf` document.

### Requirement: identifier-friendly retrieval

The `SparseIndexPort` MUST reliably retrieve engineering identifiers
(§26 — `GEN_3.0.03`, `ILO-5193`, `RpaVaryToteJpaMapper`,
`PSB_FINISH_PACK`, `0x84721`) through the BM25 ranking without
treating them as stopwords.

#### Scenario: identifier lookup returns the matching chunk

Given a chunk whose `rawText` contains `RpaVaryToteJpaMapper`
When the index receives a query that contains the same identifier
Then the index returns the chunk as the top-ranked hit.

### Requirement: deterministic stats

The `SparseIndexPort.stats()` operation MUST return deterministic
results for a given index state so the `runtime-status` CLI report is
stable across calls.

#### Scenario: stats are stable across calls

Given an index over a fixed corpus
When the caller invokes `stats()` twice
Then the two responses contain identical numbers for `documents`,
`terms` and `bytes`.

## Phase 3 task coverage

The change lists Phase 3 tasks 63 (`SparseIndex` implementation) and
69 (Wiki maintenance) that this capability exercises.

Out of scope:

- the dense ANN integration — Phase 4 task 70 (`EmbeddingModelPort`);
- the hybrid retrieval pipeline — Phase 4 task 71
  (`HybridRetrieval`);
- the multi-stage retrieval — Phase 4 task 72
  (`MultiStageRetrieval`);
- the reranker, metadata-driven filters, context assembler and
  retrieval benchmark — Phase 4 tasks 74-77.