# full-text-index Specification delta

Covers architecture section §65 (License-Aware Configuration Example
— durable secondary text index) and §26 (Sparse and Exact Retrieval
— exact identifier lookup). The `FullTextIndex` exposes a secondary
text index (FTS5 / LIKE-style ranking) over the chunks and entities,
behind a `FullTextIndexPort` that the Phase 4 `HybridRetrieval`
pipeline composes alongside the `SparseIndex` and `DenseIndex`.

The Phase 1 `canonical-knowledge-schema` capability provides the
SHA-256 content address that the full-text index uses as the
document primary key. The Phase 2 `semantic-structural-chunking` and
`context-enrichment` capabilities provide the chunks and entities
that the index is built from.

## ADDED Requirements

### Requirement: FullTextIndexPort contract

The platform MUST expose a `FullTextIndexPort` abstract class in
`pi_platform/ports/runtime/full_text_index.py` with the following
operations:

- `index_document(family: str, documentId: str, text: str,
  metadata: Mapping[str, object]) -> None`;
- `delete_document(documentId: str) -> None`;
- `query(text: str, top_k: int = 10) -> Sequence[FullTextHit]`
  where `FullTextHit = (documentId, score, snippet)`;
- `stats() -> Mapping[str, int]`.

#### Scenario: full-text index returns substring hits

Given an index over three documents with distinct vocabulary
When the index receives a query that contains a substring present
in only one document
Then the index returns that document as the top-ranked hit with a
non-empty snippet.

### Requirement: separation from the sparse index

The `FullTextIndexPort` MUST be distinct from the `SparseIndexPort`
so the two ranking algorithms can be composed by the
`HybridRetrieval` pipeline without coupling:

- the `SparseIndex` exposes BM25-style ranking with chunk metadata
  awareness;
- the `FullTextIndex` exposes substring / FTS5-style ranking that is
  closer to a database `LIKE` query.

#### Scenario: sparse and full-text indexes coexist on the same chunks

Given two adapters — `SparseIndex` and `FullTextIndex` — pointed at
the same set of chunks
When a query is issued against each adapter
Then each adapter returns its own ranking without interfering with
the other adapter's hits
And the two result sets can be merged by the Phase 4
`HybridRetrieval` pipeline.

### Requirement: backend selection through the SQLite FTS5 module

The default `FullTextIndex` adapter MUST use the SQLite FTS5 module
that ships with the `SqliteRuntimeStore` backend. The full-text
index MUST NOT introduce a separate runtime dependency beyond the
SQLite engine itself.

#### Scenario: full-text index works under the SQLite backend

Given the `SqliteRuntimeStore` default backend
When a chunk is written through the runtime store and indexed
through the full-text adapter
Then the full-text adapter returns the chunk as a hit when the
query contains a substring present in the chunk.

### Requirement: deterministic stats

The `FullTextIndexPort.stats()` operation MUST return deterministic
results for a given index state so the `runtime-status` CLI report
is stable across calls.

#### Scenario: stats are stable across calls

Given an index over a fixed corpus
When the caller invokes `stats()` twice
Then the two responses contain identical numbers.

## Phase 3 task coverage

The change lists Phase 3 tasks 65 (`FullTextIndex` implementation)
and 69 (Wiki maintenance) that this capability exercises.

Out of scope:

- the dense ANN integration — Phase 4 task 70 (`EmbeddingModelPort`);
- the hybrid retrieval pipeline — Phase 4 task 71
  (`HybridRetrieval`);
- the multi-stage retrieval — Phase 4 task 72
  (`MultiStageRetrieval`);
- the reranker, metadata-driven filters, context assembler and
  retrieval benchmark — Phase 4 tasks 74-77.