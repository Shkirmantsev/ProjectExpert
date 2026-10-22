# 2026-10-18-real-embeddinggemma2-binding Specification

Covers plan §6.1, §9, §12–§14, §101 (PR 3 of §79).

## Purpose

Define the observable behaviour of the production EmbeddingGemma 2
binding: real inference instead of the not-bound stub, 512-dimensional
L2-normalized output produced with the upstream Matryoshka truncation
policy, task-aware query/document prompting, text/image loading,
the documented numeric policy (float32 on CPU, bfloat16 on supported
accelerators, never float16 by default), an immutable pinned revision,
a persistent model cache and startup health checks. External facts
verified in plan §101: `google/embeddinggemma-2`, Apache-2.0, 768d
native output with MRL support at 512/256/128, 8,192-token context,
100+ languages, task-specific query/document prompting, and the
upstream recommendation of bfloat16 or float32 rather than float16
(https://huggingface.co/google/embeddinggemma-2).

## Requirements

### Requirement: real inference in the production path

When the EmbeddingGemma 2 model is selected in the production profile,
the platform MUST produce vectors through real model inference and MUST
NOT reach any not-bound or stub code path. Selecting the model while its
runtime is unavailable MUST fail startup with an actionable error
instead of substituting another backend.

#### Scenario: missing runtime fails with an actionable error (verifies: real inference in the production path)

Given the production profile selects EmbeddingGemma 2 and its runtime is not installed
When the operator starts the platform
Then startup fails with an error naming the model
And the error names the command that pulls the model
And no other embedding backend is silently used

### Requirement: fixed output shape and normalization

The platform SHALL produce 512-dimensional vectors for the production
EmbeddingGemma 2 profile, obtained by truncating the native output
according to the upstream Matryoshka policy and re-normalizing after
truncation such that every returned vector has unit L2 norm.

#### Scenario: encoding returns 512-dimensional unit vectors (verifies: fixed output shape and normalization)

Given the production profile selects EmbeddingGemma 2 with weights present in the model cache
When the platform encodes a document-role text
Then the returned vector has 512 entries
And its L2 norm is 1 within floating-point tolerance

### Requirement: task-aware query and document formatting

The platform MUST format query-role inputs and document-role inputs
with the model's documented task-specific prompting policy, and prompt
formatting MUST remain internal to the binding so that the retrieval
pipeline never constructs model-specific prompts itself.

#### Scenario: query and document roles are formatted differently (verifies: task-aware query and document formatting)

Given the production profile selects EmbeddingGemma 2
When the platform encodes the same text once with query role and once with document role
Then the two vectors differ
And neither call site constructed a model-specific prompt

### Requirement: text and image loading

The production Gemma binding MUST retain the vision encoder needed for image
embeddings. Text inputs and supported repository images or extracted PDF figure
images MUST use the actual model; image bytes MUST NOT be replaced by filenames
or silently discarded. Audio/video ingestion is outside this binding's contract.

#### Scenario: image pixels participate in embeddings

Given the production profile selects Gemma with its vision components loaded
When two different supported images are embedded
Then their pixel content is passed to the model
And the outputs are normalized 512-dimensional vectors
And changing image bytes invalidates the cached image embedding.

### Requirement: numeric policy

The platform MUST use float32 on CPU and bfloat16 on supported
accelerators for this model, and MUST NOT default to float16. The
platform MUST re-check vector dimension and normalization after
encoding and MUST fail the health check when they deviate.

#### Scenario: CPU execution uses float32 (verifies: numeric policy)

Given no compatible accelerator is available
When the platform selects the execution device for EmbeddingGemma 2
Then the model runs in float32 on CPU
And the reported device and numeric policy are visible in the capability report

#### Scenario: float16 is never the default (verifies: numeric policy)

Given a supported accelerator with sufficient memory is available
When the platform selects the execution device for EmbeddingGemma 2
Then the model runs in bfloat16
And float16 is not selected

#### Scenario: health check catches malformed output (verifies: numeric policy)

Given the production profile selects EmbeddingGemma 2
When a health-check encoding returns a vector with the wrong dimension
Then the health check fails
And the platform reports the binding as not healthy instead of serving it

### Requirement: immutable revision and persistent cache

The platform MUST record an immutable upstream revision for this model
in the profile identity and in the model licence inventory, replacing
any placeholder revision. Downloaded weights MUST persist in the
configured model cache across container recreations, and a failed
download MUST abort startup with an actionable error.

#### Scenario: weights survive container recreation (verifies: immutable revision and persistent cache)

Given the model weights were pulled into the configured model cache
When the container is recreated and restarted with the same cache volume
Then the model loads without re-downloading
And the recorded revision matches the previously recorded immutable revision
