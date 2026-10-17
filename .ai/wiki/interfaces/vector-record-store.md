---
id: interfaces.vector-record-store
title: VectorRecordStorePort contract
kind: interfaces
status: active
summary: Persists embedding vector records separately from the ANN index, keyed by (chunk_id, embedding_profile_hash). Vectors are stored as BLOBs (never JSON), so the ANN can be deleted and rebuilt without re-running the embedding model.
sourceRefs:
  - pi_platform/ports/runtime/vector_record_store.py
  - pi_platform/adapters/runtime/sqlite_vector_record_store.py
  - openspec/specs/2026-10-16-embedding-execution-profile/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-runtime-store/spec.md
  - adr.0026-embedding-profile-identity-and-vector-namespace
maintenance:
  mode: authored
related:
  - interfaces.dense-index
  - interfaces.embedding-profile
  - modules.runtime-store
  - modules.embeddings
---

# VectorRecordStorePort contract

The v0.8 refinement separates the ANN index from the
embedding vector records. The ANN index is a disposable
derived artefact; the vector records are the durable
source of truth. The two are linked by the
`embedding_profile_hash` namespace key.

The port lives at
`pi_platform/ports/runtime/vector_record_store.py`. The
SQLite adapter lives at
`pi_platform/adapters/runtime/sqlite_vector_record_store.py`.

## Surface

```python
@dataclass(frozen=True)
class VectorRecord:
    chunk_id: str
    content_hash: str
    embedding_profile_hash: str
    model_revision: str
    dimension: int
    normalization: str
    vector_payload: bytes   # raw float32/float64; never JSON
    created_from_retrieval_text_hash: str
    created_at: str         # ISO 8601 UTC; stamped at put() time


class VectorRecordStorePort(abc.ABC):
    @abstractmethod
    def put(self, record: VectorRecord) -> None: ...
    @abstractmethod
    def get(self, chunk_id: str, embedding_profile_hash: str) -> VectorRecord | None: ...
    @abstractmethod
    def delete(self, chunk_id: str, embedding_profile_hash: str) -> None: ...
    @abstractmethod
    def iter(self, embedding_profile_hash: str) -> Iterable[VectorRecord]: ...
    @abstractmethod
    def profile_hash_for(self, chunk_id: str) -> str | None: ...
    @abstractmethod
    def stats(self) -> Mapping[str, int]: ...
```

## SQLite schema

A single table `embeddings` with columns
`chunk_id TEXT NOT NULL`,
`embedding_profile_hash TEXT NOT NULL`,
`content_hash TEXT NOT NULL`,
`model_revision TEXT NOT NULL`,
`dimension INTEGER NOT NULL`,
`normalization TEXT NOT NULL`,
`vector_payload BLOB NOT NULL`,
`created_from_retrieval_text_hash TEXT NOT NULL`,
`created_at TEXT NOT NULL`,
`PRIMARY KEY (chunk_id, embedding_profile_hash)`.

The migration is `CREATE TABLE IF NOT EXISTS` and is
idempotent; existing `runtime_entries` rows are untouched.

## Vector serialisation

Vectors are stored as raw `array.array("f", vector).tobytes()`
(float32, the default) or
`array.array("d", vector).tobytes()` (float64). Helper
functions `encode_vector_payload(vector, *, dtype="f")` and
`decode_vector_payload(blob, *, dtype="f")` are provided.

Vectors MUST NOT be stored as JSON arrays. The contract test
`test_vector_payload_not_json` enforces this.

## v0.8 invariants preserved

- `RuntimeStorePort` API is unchanged. The new store shares
  the physical `runtime.db` but is logically decoupled.
- The existing `runtime_entries` table is preserved
  byte-identically.
- `HashingEmbeddingModel` remains the default in the
  `minimal` profile; the Tier-1 benchmark
  (`tests/test_retrieval_benchmark`) continues to pass
  byte-identically.

## Tests

- `tests/test_vector_record_store.py` (10 tests) — put and
  get roundtrip, get unknown returns None, delete, iter
  filters by profile, primary key uniqueness (overwrite
  semantics), vector_payload not JSON, encode-decode
  roundtrip, migration creates table, migration idempotent,
  stats counts records and profiles.

[Embedding profile](embedding-profile.md) ·
[Dense index](dense-index.md) ·
[Runtime store](runtime-store.md) ·
[ADR 0026](../adr/0026-embedding-profile-identity-and-vector-namespace.md)
