# 2026-10-04-embedding-model Specification delta

Covers plan §3.5, §12, §13, §14, §15, §16.

## ADDED Requirements

### Requirement: EmbeddingProfile identity and namespace

The platform MUST define `EmbeddingProfile`
(`provider`, `model_id`, `model_revision`, `modality`,
`output_dimension`, `normalization`,
`instruction_profile`, `tokenizer_id`,
`strategy_version`) and its identity key
`sha256(canonical(EmbeddingProfile))`. The dense index
MUST refuse to mix vectors from incompatible profiles
in a single ANN namespace.

#### Scenario: incompatible vector spaces cannot be opened together

Given an ANN namespace built for
`EmbeddingGemma 2 / dim 512 / normalize: true`
When the platform attempts to open it with an active
profile of `Qwen3-Embedding-0.6B / dim 1024 /
normalize: false`
Then the platform rejects the operation with a clear,
redacted error
And the existing ANN namespace is not corrupted.

### Requirement: production semantic embedding adapters

The platform MUST bind at least one real local
semantic embedding adapter behind the existing
`EmbeddingModelPort`. The first profile is
`EmbeddingGemma 2` (text/code, optional multimodal
retrieval). `Qwen3-Embedding-0.6B` is a separate
profile. The hashing backend
(`HashingEmbeddingModel`) is preserved for unit tests,
zero-dependency boot, and deterministic smoke tests.

The existing `MultilingualSentenceTransformerEmbeddingModel`
stub MUST be replaced by a working adapter; the stub
is a correct placeholder architecture but is not a
production semantic embedding implementation.

#### Scenario: EmbeddingGemma 2 produces real semantic vectors

Given a real text input
When the platform calls the
`EmbeddingGemma2EmbeddingModel` adapter
Then the adapter returns a real semantic vector of
the configured dimension
And the vector is persisted under
`embeddinggemma2-512-normalize` (or the configured
profile).

### Requirement: VectorRecordStorePort persistence

The platform MUST persist vector records through
`VectorRecordStorePort` with the shape
`VectorRecord` (`chunk_id`, `content_hash`,
`embedding_profile_hash`, `model_revision`,
`dimension`, `normalization`, `vector_payload` (BLOB),
`created_from_retrieval_text_hash`). Vectors MUST be
stored as BLOBs, not as JSON arrays.

#### Scenario: unchanged retrieval text reuses embedding

Given a `chunk` whose `retrieval_text` content hash
matches an existing `VectorRecord`
When the platform re-evaluates the chunk
Then the platform reuses the existing
`VectorRecord` and does not re-embed.

## MODIFIED Requirements

None. The existing embedding-model `Requirements` are
extended additively; their bodies are not rewritten.
