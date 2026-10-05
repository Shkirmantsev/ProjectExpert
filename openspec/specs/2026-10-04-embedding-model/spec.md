# 2026-10-04-embedding-model Specification

## Purpose
TBD - created by archiving change implement-phase-4-retrieval. Update Purpose after archive.
## Requirements
### Requirement: EmbeddingModelPort contract

The platform MUST expose an `EmbeddingModelPort` abstract class in
`pi_platform/ports/runtime/embedding_model.py` with the following
operations:

- `embed(text: str) -> Sequence[float]` — embed a single text snippet
  and return a fixed-dimensional `Sequence[float]`;
- `embed_batch(texts: Sequence[str]) -> Sequence[Sequence[float]]`
  — embed a batch of snippets and return the same number of vectors
  in the same order;
- `dimension() -> int` — return the fixed vector dimension that every
  returned vector MUST have;
- `model_version() -> str` — return the opaque model-version string
  that the `VersionIdentity.embeddingModelVersion` records;
- `license_id() -> str` — return the SPDX identifier of the
  embedded model and runtime (see §5.4 model-license inventory);
- `stats() -> Mapping[str, int]` — return operational counters
  (`{"calls": ..., "tokens": ..., "errors": ...}`).

#### Scenario: embed produces a fixed-dimension vector

Given an `EmbeddingModelPort` whose `dimension()` returns `384`
When `embed("FinishPack protocol message")` runs
Then the returned sequence has exactly `384` floats
And every float is finite (no `nan` or `inf`).

#### Scenario: embed_batch preserves order

Given a batch of three snippets `["a", "b", "c"]`
When `embed_batch(["a", "b", "c"])` runs
Then the returned list has three vectors in the order
`[vector("a"), vector("b"), vector("c")]`.

### Requirement: multilingual coverage

The default `EmbeddingModelPort` adapter MUST support multilingual
retrieval across German (DE), English (EN) and Ukrainian (UK) at
parity. Russian (RU) MAY be enabled through configuration. The
adapter MUST NOT silently drop text in any of DE, EN or UK.

#### Scenario: default multilingual embedding returns aligned vectors

Given a chunk with German text and a chunk with English text that
mean the same thing
When the default adapter embeds both chunks
Then both vectors have the configured dimension
And the cosine similarity between them is above the multilingual
alignment threshold declared by the adapter
And `stats()` records both calls.

#### Scenario: Russian is opt-in

Given `project-context.yaml:embedding.languages` lists only
`["en", "de", "uk"]`
When the platform embeds a Russian text snippet
Then the embedding call returns a vector (the model still encodes it)
And `stats()` records the call under the configured languages.

### Requirement: CPU-capable deployment

The default `EmbeddingModelPort` adapter MUST be executable on a
commodary CPU-only machine without a dedicated GPU. The default
adapter MUST NOT block startup when no GPU is detected. A GPU-backed
adapter MAY be registered when the optional GPU runtime is present.

#### Scenario: default adapter starts on CPU-only hardware

Given a host without a GPU (or with GPU access disabled)
When the embedding model is initialised
Then the default adapter registers successfully
And `embed("...")` runs end-to-end on CPU.

#### Scenario: GPU adapter is registered only when present

Given a host with the optional GPU runtime available
When the embedding model is initialised
Then the GPU adapter MAY be registered in addition to the default
CPU adapter
And the application layer chooses which adapter to call through the
`project-context.yaml:embedding.backend` configuration value.

### Requirement: replaceable provider

The `EmbeddingModelPort` MUST be implementable by a default
multilingual CPU adapter and one or more alternative adapters without
leaking backend-specific details into the port surface. The active
adapter MUST be selected through
`project-context.yaml:embedding.backend` configuration.

#### Scenario: backend swap does not change observable behaviour

Given a test that swaps the default adapter for an alternative
adapter implementing the same port
When the test calls `embed("FinishPack protocol message")` on both
adapters
Then both return a vector of the declared `dimension()`
And both record the same `model_version()` string in the
`VersionIdentity.embeddingModelVersion` field of any chunk they
produced vector for.

### Requirement: commercially-usable license

The default `EmbeddingModelPort` adapter MUST use a model and runtime
whose license satisfies the §5.1 preferred license policy OR the §5.5
`LicenseGate` approval process for review-required licenses. The
model and runtime license SPDX identifiers MUST appear in
`distribution/licenses/dependency-inventory.json` before the adapter
is registered. The adapter MUST NOT bundle a non-commercial,
research-only or source-available-restricted model without explicit
operator opt-in.

#### Scenario: LicenseGate blocks a non-commercial model

Given a proposed adapter whose `license_id()` returns a license
containing `Non-Commercial` or `Research Only`
When `LicenseGate` runs against the dependency inventory
Then the gate fails with a clear message
And the adapter is NOT registered.

#### Scenario: preferred-license adapter is registered

Given a proposed adapter whose `license_id()` returns `Apache-2.0`
or `MIT`
When `LicenseGate` runs against the dependency inventory
Then the gate passes
And the adapter is registered as the default.

### Requirement: deterministic vectorisation

The `EmbeddingModelPort.embed` operation MUST be deterministic for a
fixed `model_version()` and a fixed input text: the same call with
the same input MUST produce a vector whose element-wise values are
bit-wise identical (or within the numerical noise declared by the
adapter) across repeated invocations. Non-determinism in the
underlying runtime MUST be disabled through explicit configuration.

#### Scenario: repeated embed is deterministic

Given an `EmbeddingModelPort` adapter
When `embed("hello")` runs twice on the same input
Then both returned vectors are element-wise equal within the
adapter-declared numerical tolerance
And the dense index treats them as the same vector on a second
`index_chunk` call.

### Requirement: integration with Phase 3 dense index

The Phase 3 `DenseIndexPort` MUST consume the vectors produced by the
`EmbeddingModelPort` through the same `Sequence[float]` interface.
The chunk identifier, content address and
`KnowledgeState.embeddingModelVersion` stamp MUST travel with the
vector so the dense index records the model identity. A model
version change MUST trigger a re-embedding of affected chunks per
the Phase 3 `freshness-tracking` rule.

#### Scenario: dense index records the embedding model version

Given a chunk `c-1` indexed with `model_version() == "X.Y.Z"`
When the chunk is re-embedded because the model version changed to
`"A.B.C"`
Then the `DenseIndexPort` deletes the old entry and indexes the new
vector
And the freshness tracker records the transition from `verified` to
`stale` for the affected chunk until the re-indexing finishes.

