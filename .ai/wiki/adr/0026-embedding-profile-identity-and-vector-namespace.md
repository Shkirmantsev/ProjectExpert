---
id: adr.0026-embedding-profile-identity-and-vector-namespace
title: EmbeddingProfile identity and vector-namespace isolation
kind: adr
status: accepted
date: 2026-10-14
summary: Every vector the platform ever embeds carries an EmbeddingProfile descriptor; the SHA-256 of its canonical serialisation is the namespace key. The runtime refuses to open an ANN namespace whose profile hash does not match the active profile, so different model families, dimensions, normalisations, and revisions can never be mixed.
related:
  - adr.0004-ports-and-adapters-extension-style
  - adr.0009-embedding-model-selection
  - interfaces.embedding-profile
  - interfaces.dense-index
  - interfaces.vector-record-store
  - modules.embeddings
  - modules.runtime-store
sourceRefs:
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#13
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#16
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#17
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/embedding-execution-profile/spec.md
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/2026-10-04-embedding-model/spec.md
  - pi_platform/ports/retrieval/embedding_profile.py
  - pi_platform/ports/runtime/vector_record_store.py
  - pi_platform/adapters/runtime/sqlite_vector_record_store.py
maintenance:
  mode: authored
---

# ADR 0026 — EmbeddingProfile identity and vector-namespace isolation

## Context

The v0.8 platform persisted embedding vectors in a single
namespace keyed only by `chunkId`. Switching the active embedding
model (e.g. from the hashing fallback to a real multilingual
semantic adapter, or from EmbeddingGemma 2 512 to Qwen3-Embedding
0.6B 1024) would silently mix vectors produced by incompatible
backends in the same ANN index. Two failure modes followed:

1. The dense index would happily return nearest neighbours that
   were computed by a different model in a different vector
   space; the cosine similarity score was meaningless.
2. The vector record store had no way to know which model
   produced a given vector, so re-embedding the corpus on a
   model upgrade was indistinguishable from a no-op.

The plan §13 also calls for a strong separation between
"content changed", "enrichment changed", "embedding model
changed" and "ANN implementation changed" for incremental
processing (plan §30). Without a profile key the platform
cannot tell which of these fired.

## Decision

Introduce a frozen `EmbeddingProfile` dataclass with the
following fields:

- `provider` (e.g. `"hashing"`, `"embeddinggemma2"`,
  `"qwen3-embedding-0.6b"`)
- `model_id` (e.g. `"hashing-1.0.0"`, `"embeddinggemma2-512"`,
  `"qwen3-embedding-0.6b"`)
- `model_revision` (e.g. `"v1"`, `"pinned-<sha>"`,
  `"pinned-stub"` until the real binding is wired)
- `modality` (`"text"`, `"code"`, `"multimodal"`)
- `output_dimension` (e.g. `384`, `512`, `768`, `1024`)
- `normalization` (`"l2"`, `"none"`)
- `instruction_profile` (`"default"`, `"query-document"`,
  `"matryoshka-256"`, `"matryoshka-512"`)
- `tokenizer_id` (matches `TokenizerPort.identity()`, e.g.
  `"hashing/v1"`, `"embeddinggemma2/v1-stub"`)
- `strategy_version` (e.g. `"embedding-profile-v1"`)

The identity key is `sha256(canonical(EmbeddingProfile))` where
`canonical(...)` is a byte-stable JSON serialisation with sorted
keys, no whitespace, no volatile data. Two profiles with the
same fields in different insertion order produce the same key.

Three built-in profiles are pre-registered:

- `HASHING_DEFAULT` — `provider="hashing"`, `dimension=384`,
  `normalization="l2"`, `tokenizer_id="hashing/v1"`. The
  default in the `minimal` profile and the Tier-1
  deterministic benchmark.
- `EMBEDDINGGEMMA2_512` — `provider="embeddinggemma2"`,
  `dimension=512`, `normalization="l2"`,
  `instruction_profile="matryoshka-512"`, `model_revision=
  "pinned-stub"` (placeholder for the real binding). The
  first real local semantic profile.
- `QWEN3_EMBEDDING_0_6B_1024` — `provider="qwen3-embedding-0.6b"`,
  `dimension=1024`, `normalization="l2"`, `model_revision=
  "pinned-stub"`. The second evaluation profile; persists in a
  separate ANN namespace from EmbeddingGemma 2.

The `EmbeddingProfileRegistry` exposes
`default(name: str) -> EmbeddingProfile` and
`resolve(identity: str) -> EmbeddingProfile`; both raise
`EmbeddingProfileMismatchError` for unknown identities. Two
distinct profiles have distinct identities; the test
`test_hash_vs_embeddinggemma2_vs_qwen3_distinct` asserts this
invariant.

The `VectorRecordStorePort` (new port) persists
`VectorRecord(chunk_id, content_hash, embedding_profile_hash,
model_revision, dimension, normalization, vector_payload as
BLOB, created_from_retrieval_text_hash, created_at)`. The
SQLite adapter (`SqliteVectorRecordStore`) stores the
`vector_payload` as a `BLOB` of either `array.array("f",
vector).tobytes()` (float32) or `array.array("d",
vector).tobytes()` (float64). Vectors are NEVER stored as
JSON.

The `DenseIndexPort` (existing) refuses to open an ANN
namespace whose stored `embedding_profile_hash` does not
match the active profile's identity. The error is clear and
redacted of secret metadata.

The vector record store is logically decoupled from the
existing `RuntimeStorePort`. The two stores share the same
physical `runtime.db` but live in different tables; the
`runtime_entries` table is preserved unchanged.

The ANN index (Flat today; USearch is added by Change Package
D) is a disposable derived artefact under
`.project-intelligence-cache/indexes/<embedding_profile_hash>/`
and is git-ignored. The index metadata records
`embedding_profile_hash`, `index_schema_version`,
`source_generation`, and `vector_count`. If any compatibility
key changes, the platform rebuilds the index from the
`VectorRecordStorePort` records without re-running the
embedding model.

## Consequences

Positive:

- A future model switch cannot silently mix vectors; the
  dense index refuses the operation with a clear, redacted
  error.
- Re-embedding under a new profile produces a new namespace;
  the old namespace remains queryable under its own profile
  key.
- The ANN can be deleted and rebuilt from the vector record
  store without re-running the embedding model, which makes
  switching from Flat to USearch cheap.
- The HashingEmbeddingModel stays the default in the
  `minimal` profile; the Tier-1 benchmark
  (`tests/test_retrieval_benchmark`) continues to pass
  byte-identically.
- Incremental processing keys (plan §30) can distinguish
  "content changed" from "enrichment changed" from "embedding
  model changed" from "ANN implementation changed" because
  each is keyed by a different namespace.

Negative:

- The `EmbeddingProfile` descriptor is a small fixed
  vocabulary; adding a new field is a schema-level change
  (the `identity()` hash changes, which is correct, but
  existing vector records must be re-keyed).
- The two production profiles
  (`EMBEDDINGGEMMA2_512`, `QWEN3_EMBEDDING_0_6B_1024`) are
  stubs until the real model bindings are wired in
  Package C.1.5; their `model_revision` is the literal
  string `"pinned-stub"`. Operators must record the real
  revision in `distribution/licenses/model-licenses.json`
  when they bind a model.

## Rollback

The hashing profile is permanently registered. The two
production-profile stubs can be removed (and the registry
pruned) by deleting their registrations in
`pi_platform/ports/retrieval/embedding_profile.py`. Existing
vector records in the SQLite store are kept; only the
`embedding_profile_hash` key in the namespace is gone.
