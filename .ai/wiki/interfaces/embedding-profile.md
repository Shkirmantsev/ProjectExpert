---
id: interfaces.embedding-profile
title: EmbeddingProfile contract
kind: interfaces
status: active
summary: EmbeddingProfile descriptor and identity key for vector-namespace isolation. The SHA-256 of the canonical serialisation is the namespace key; the runtime refuses to open an ANN namespace whose profile hash does not match the active profile.
sourceRefs:
  - pi_platform/ports/retrieval/embedding_profile.py
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/embedding-execution-profile/spec.md
  - openspec/changes/improve-ingestion-retrieval-local-models/specs/2026-10-04-embedding-model/spec.md
  - adr.0026-embedding-profile-identity-and-vector-namespace
maintenance:
  mode: authored
related:
  - interfaces.tokenizer
  - interfaces.dense-index
  - interfaces.vector-record-store
  - modules.embeddings
---

# EmbeddingProfile contract

The v0.8 refinement introduces `EmbeddingProfile` as the
normative identity of every vector the platform ever embeds.
The profile descriptor is a frozen dataclass with nine
fields; the identity key is `sha256(canonical(EmbeddingProfile))`.

The port lives at
`pi_platform/ports/retrieval/embedding_profile.py`.

## Descriptor

```python
@dataclass(frozen=True)
class EmbeddingProfile:
    provider: str            # "hashing", "embeddinggemma2", "qwen3-embedding-0.6b"
    model_id: str            # "hashing-1.0.0", "embeddinggemma2-512", ...
    model_revision: str      # "v1", "pinned-<sha>", "pinned-stub"
    modality: str            # "text", "code", "multimodal"
    output_dimension: int    # 384, 512, 768, 1024
    normalization: str       # "l2", "none"
    instruction_profile: str # "default", "query-document", "matryoshka-256", "matryoshka-512"
    tokenizer_id: str        # matches TokenizerPort.identity()
    strategy_version: str    # "embedding-profile-v1"
```

`identity()` returns `sha256(canonical_bytes()).hexdigest()`.
`canonical_bytes()` is a byte-stable JSON encoding with
sorted keys, no whitespace, no volatile data.

## Built-in profiles

| Profile | Provider | Dimension | Notes |
| --- | --- | --- | --- |
| `HASHING_DEFAULT` | `hashing` | 384 | `tokenizer_id="hashing/v1"`, `normalization="l2"`. The default in the `minimal` profile. |
| `EMBEDDINGGEMMA2_512` | `embeddinggemma2` | 512 | `model_revision="pinned-stub"` (placeholder until the real binding is wired), `instruction_profile="matryoshka-512"`. The first real local semantic profile. |
| `QWEN3_EMBEDDING_0_6B_1024` | `qwen3-embedding-0.6b` | 1024 | `model_revision="pinned-stub"`. The second evaluation profile. Persists in a separate `embedding_profile_hash` namespace from EmbeddingGemma 2. |

## Vector-space isolation

The `DenseIndexPort` (existing) refuses to open an ANN
namespace whose stored `embedding_profile_hash` does not
match the active profile. The error is clear and redacted
of secret metadata.

The `EmbeddingProfileRegistry.resolve(identity)` raises
`EmbeddingProfileMismatchError` for unknown identities.

The two production-profile stubs are STUB adapters (raise
`EmbeddingModelError` from `embed()` / `embed_batch()`);
the real binding ships in Change Package C.1.5.

## v0.8 invariants preserved

- Vectors from incompatible profiles can never be opened
  together.
- Re-embedding under a new profile produces a new namespace;
  the old namespace remains queryable under its own profile
  key.
- The ANN can be deleted and rebuilt from
  `VectorRecordStorePort` without re-running the embedding
  model.
- The hashing profile is the default; the Tier-1
  benchmark continues to pass byte-identically.

## Tests

- `tests/test_embedding_profile_identity.py` (6 tests) —
  canonical bytes byte-stable, identity deterministic,
  hash / embeddinggemma2 / qwen3 distinct, registry default
  resolves, registry unknown identity raises, registry
  register idempotent.
- `tests/test_embeddinggemma2_embedding_model.py` and
  `tests/test_qwen3_embedding_model.py` — adapter stubs
  raise on `embed` / `embed_batch`; profile() returns the
  same instance.
- `tests/test_hashing_embedding_fallback.py` (6 tests) —
  hashing dimension 384, deterministic, zero-norm on empty
  text, model version, license, no external deps.

[Vector record store](vector-record-store.md) ·
[Tokenizer port](tokenizer.md) ·
[Dense index](dense-index.md) ·
[ADR 0026](../adr/0026-embedding-profile-identity-and-vector-namespace.md)
