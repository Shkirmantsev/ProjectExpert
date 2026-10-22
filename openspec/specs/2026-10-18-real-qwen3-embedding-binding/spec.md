# 2026-10-18-real-qwen3-embedding-binding Specification

Covers plan §6.2, §10, §12–§14, §101 (PR 4 of §79).

## Purpose

Define the observable behaviour of the production Qwen3-Embedding-0.6B
binding: real inference instead of the not-bound stub, 1024-dimensional
L2-normalized output, query encoding with the upstream instruction
policy, document encoding without instruction, correct batched
encoding, device policy, an immutable pinned revision and startup health
checks. External facts verified in plan §101:
`Qwen/Qwen3-Embedding-0.6B`, Apache-2.0, 0.6B parameters, 32K context,
up to 1024d output with Matryoshka/custom dimension support, 100+
languages, instruction-aware query embedding and code retrieval
(https://huggingface.co/Qwen/Qwen3-Embedding-0.6B). The first production
release keeps the simple 1024d default; reduced-dimension variants, if
offered later, MUST be separate profile identities with separate
namespaces.

## Requirements

### Requirement: real inference in the production path

When the Qwen3 embedding model is selected in the production profile,
the platform MUST produce vectors through real model inference and MUST
NOT reach any not-bound or stub code path. Selecting the model while its
runtime is unavailable MUST fail startup with an actionable error
instead of substituting another backend.

#### Scenario: missing runtime fails with an actionable error (verifies: real inference in the production path)

Given the production profile selects Qwen3 embedding and its runtime is not installed
When the operator starts the platform
Then startup fails with an error naming the model
And the error names the command that pulls the model
And no other embedding backend is silently used

### Requirement: fixed output shape and normalization

The platform SHALL produce 1024-dimensional vectors for the production
Qwen3 embedding profile, and every returned vector MUST have unit L2
norm.

#### Scenario: encoding returns 1024-dimensional unit vectors (verifies: fixed output shape and normalization)

Given the production profile selects Qwen3 embedding with weights present in the model cache
When the platform encodes a document-role text
Then the returned vector has 1024 entries
And its L2 norm is 1 within floating-point tolerance

### Requirement: instruction-aware query encoding only

The platform MUST apply the documented query instruction when encoding
query-role inputs and MUST encode document-role inputs without that
instruction. The instruction policy MUST remain internal to the binding.

#### Scenario: query instruction applies only to queries (verifies: instruction-aware query encoding only)

Given the production profile selects Qwen3 embedding
When the platform encodes the same text once with query role and once with document role
Then the two vectors differ
And the query-role encoding used the documented query instruction
And the document-role encoding did not

### Requirement: batched encoding equivalence

The platform MUST support batched encoding, and a batched call MUST
produce vectors identical within floating-point tolerance to encoding
the same inputs one at a time.

#### Scenario: batch equals single encoding (verifies: batched encoding equivalence)

Given the production profile selects Qwen3 embedding
When the platform encodes three texts in one batch call
Then each batched vector matches the corresponding single-call vector within floating-point tolerance

### Requirement: device policy and health checks

The platform MUST select the execution device according to the resolved
runtime configuration (auto preferring a compatible accelerator with
sufficient memory, otherwise CPU) and MUST report the selected device
and the selection reason. The platform MUST run a startup health check
asserting output dimension and normalization and MUST refuse to serve a
binding that fails it.

#### Scenario: accelerator below memory threshold falls back to CPU (verifies: device policy and health checks)

Given a compatible accelerator whose free memory is below the safe threshold
When the platform resolves the execution device with policy auto
Then the model runs on CPU
And the reported reason is insufficient accelerator memory

### Requirement: immutable revision and persistent cache

The platform MUST record an immutable upstream revision for this model
in the profile identity and in the model licence inventory, replacing
any placeholder revision. Downloaded weights MUST persist in the
configured model cache across container recreations.

#### Scenario: revision placeholder is gone (verifies: immutable revision and persistent cache)

Given the production profile for Qwen3 embedding
When the platform reports the profile identity and the model licence inventory
Then the recorded revision is an immutable upstream revision
And no placeholder revision marker appears in either location
