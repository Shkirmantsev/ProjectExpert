# 2026-10-16-embedding-execution-profile Specification

Covers plan §3.5, §3.6, §12, §13, §14, §15, §16, §17,
§17.1, §24, §31.

## Purpose

Define the `EmbeddingProfile` descriptor and identity key,
the `VectorRecordStorePort`, the disposable ANN index
contract, the separation between the `HashingEmbeddingModel`
fallback and the production semantic adapters
(`EmbeddingGemma 2`, `Qwen3-Embedding-0.6B`), and the
deployment profiles (`minimal`, `semantic-cpu`,
`semantic-gpu`, `quality`, `contextualized`,
`multimodal`). The `EmbeddingProfile` is the normative
identity for every vector that the platform ever embeds.

## Requirements

### Requirement: EmbeddingProfile descriptor

The platform MUST define `EmbeddingProfile` with the
following fields: `provider`, `model_id`,
`model_revision`, `modality`, `output_dimension`,
`normalization`, `instruction_profile`, `tokenizer_id`,
`strategy_version`.

The identity key is
`sha256(canonical(EmbeddingProfile))`. The canonical
serialisation MUST use sorted keys, no volatile data
(timestamps, hostnames, paths), and a documented JSON
shape.

#### Scenario: same profile produces the same identity

Given two `EmbeddingProfile` instances with identical
fields in different insertion order
When the platform computes the identity key
Then the two identity keys are byte-identical.

### Requirement: vector-space isolation

The platform MUST reject any attempt to mix vectors from
incompatible `EmbeddingProfile` identities in a single
ANN namespace. The dense index MUST refuse to open an
ANN namespace whose
`embedding_profile_hash` does not match the active
profile; the error message MUST NOT leak secret
metadata (no payload contents, no model artefacts
beyond the identity).

Vectors from different model families, different
dimensions, different normalization modes, or
incompatible revisions MUST NOT share an ANN namespace.

#### Scenario: incompatible vectors cannot be opened together

Given an ANN namespace built for
`EmbeddingGemma 2 / dim 512 / normalize: true`
When the platform attempts to open it with an active
profile of
`Qwen3-Embedding-0.6B / dim 1024 / normalize: false`
Then the platform rejects the operation with a clear,
redacted error
And the existing ANN namespace is not corrupted.

### Requirement: persistent vector records

The platform MUST define `VectorRecordStorePort` with
`VectorRecord`
(`chunk_id`, `content_hash`,
`embedding_profile_hash`, `model_revision`,
`dimension`, `normalization`, `vector_payload` (BLOB),
`created_from_retrieval_text_hash`).

The SQLite adapter MUST store vectors as BLOBs in the
`embeddings` table. Vectors MUST NOT be stored as JSON
arrays.

#### Scenario: deleting ANN does not require re-embedding

Given a populated `embeddings` table and a USearch ANN
namespace
When the ANN namespace is deleted
Then the platform rebuilds the ANN from
`VectorRecordStorePort` without re-running the
embedding model.

#### Scenario: unchanged retrieval text reuses embedding

Given a `chunk` whose `retrieval_text` content hash
matches an existing `VectorRecord`
When the platform re-evaluates the chunk
Then the platform reuses the existing
`VectorRecord` and does not re-embed.

### Requirement: ANN backend selection

The platform MUST support `dense_index.backend ∈ {auto,
flat, usearch}`. `FlatDenseIndex` and `USearchDenseIndex`
both implement the existing `DenseIndexPort`. The
selection is configuration / capability driven. `auto`
MAY choose flat vs ANN based on benchmarked corpus size
and recall constraints; the choice MUST be data-driven,
not hard-coded as an architectural invariant.

USearch index files MUST be stored under
`.project-intelligence-cache/indexes/<embedding_profile_hash>/`
and MUST be git-ignored. The index metadata MUST record
`embedding_profile_hash`, `index_schema_version`,
`source_generation`, `vector_count`. If any
compatibility key changes, the platform MUST rebuild the
ANN index.

#### Scenario: profile change triggers ANN rebuild

Given an existing ANN namespace built for profile
`hashing-fallback`
When the active profile changes to
`embeddinggemma2-512-normalize`
Then the platform rebuilds the ANN from
`VectorRecordStorePort` records that match the new
profile
And the old hashing namespace remains available
under its own profile key.

### Requirement: production semantic embedding adapters

The platform MUST bind at least one real local semantic
embedding adapter behind the existing
`EmbeddingModelPort` (the existing
`MultilingualSentenceTransformerEmbeddingModel` is a
contract stub and MUST be replaced by a working
adapter). The first profile is
`EmbeddingGemma 2` (text/code, optional multimodal
retrieval). `Qwen3-Embedding-0.6B` is a separate
profile, persisted in a separate
`embedding_profile_hash` namespace. The hashing
backend is kept for unit tests, zero-dependency boot,
and deterministic smoke tests.

#### Scenario: hashing model is the default in the minimal profile

Given a minimal profile and no optional dependencies
installed
When the platform starts
Then `HashingEmbeddingModel` is the active embedding
backend
And the platform boots without any network access.

#### Scenario: EmbeddingGemma 2 produces real semantic vectors

Given a real text input
When the platform calls the
`EmbeddingGemma2EmbeddingModel` adapter
Then the adapter returns a real semantic vector of
the configured dimension
And the vector is persisted under
`embeddinggemma2-512-normalize` (or the configured
profile).

### Requirement: deployment profile set

The platform MUST support the following deployment
profiles as configuration presets, not code paths:
`minimal`, `semantic-cpu`, `semantic-gpu`, `quality`,
`contextualized`, `multimodal`. The host-side embedding
accelerator is an optional deployment profile, not a
core requirement; the one-container CPU path remains
the default. The Control Plane diagnostics MUST expose
the active profile, model IDs and revisions, device,
RAM / VRAM capability result, fallback state, index
compatibility, and reranker status.

#### Scenario: profile change requires rebuild

Given an active `minimal` profile with hashing vectors
When the operator switches the active profile to
`semantic-cpu` (EmbeddingGemma 2, 512, normalize)
Then the platform rebuilds the vector namespace under
the new profile key
And Control Plane diagnostics reflect the active
profile, model ID, device, and index compatibility.
