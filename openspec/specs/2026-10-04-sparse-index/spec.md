# 2026-10-04-sparse-index Specification

## Purpose
TBD - created by archiving change implement-phase-3-storage. Update Purpose after archive.
## Requirements
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

