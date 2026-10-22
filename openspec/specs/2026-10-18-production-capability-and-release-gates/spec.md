# 2026-10-18-production-capability-and-release-gates Specification

Covers plan §53, §54, §61, §62, §64, §65, §66, §67, §68, §69, §70,
§71, §72, §89, §90, §91, §97 (PR 12 of §79).

## Purpose

Define the release gates that prove the production path contains no
real-component stubs, that real models / real USearch / real Docling
are exercised on every release, that branch switching is verified
end to end and that the capability report tells the truth. The
release gate is the difference between a working repository and a
production-grade release.

## Requirements

### Requirement: production-capability gate

The release pipeline MUST run a `production-capability-gate` that
fails the build if any production-enabled profile resolves to a
`pinned-stub`, a `not bound` binding, a `usearch-stub` backend, a
synthetic Docling adapter, or a production model adapter that raises
`EmbeddingModelError` unconditionally. The gate MUST also fail if
`distribution/licenses/model-licenses.json` contains any record with
`profile` in the production-enabled set whose `revision` or `status`
is `pinned-stub`.

The production-enabled set is the documented set of model profiles
that the `production` startup profile is permitted to bind: it
includes the EmbeddingGemma 2 and Qwen3-Embedding-0.6B profiles, and
explicitly excludes profiles that are still on the development
roadmap (rerankers, OCR engines, multimodal figure binding). The
excluded set is enumerated in
`openspec/changes/production-semantic-search-and-branch-reconciliation/excluded-profiles.md`
so the gate is deterministic and reviewable.

#### Scenario: production-capability gate blocks a production stub (verifies: production-capability gate)

Given a model record for the EmbeddingGemma 2 production profile
whose status is `pinned-stub`
When the release pipeline runs `production-capability-gate`
Then the gate fails
And the failure message names the offending record and the
profile it belongs to.

#### Scenario: production-capability gate ignores excluded development profiles (verifies: production-capability gate)

Given a model record for a profile in the excluded set (for
example the reranker or the multimodal figure profile) whose
status is `pinned-stub`
When the release pipeline runs `production-capability-gate`
Then the gate does NOT fail for that record
And the failure summary lists only production-enabled profile
records.

### Requirement: real model integration tests

The release pipeline MUST run integration tests that load the actual
EmbeddingGemma 2 and Qwen3-Embedding-0.6B weights, validate the
immutable revision, dimension, finite values, normalised vectors,
identical-input stability, semantically-related ranking, and the
query versus document prompting behaviour. Tests MUST run against a
cached model on the CI runner.

#### Scenario: real-model tests use cached weights (verifies: real model integration tests)

Given the CI runner has the EmbeddingGemma 2 weights cached
When the test loads the model
Then the loaded model reports the pinned immutable revision
And `embed` of an identical text returns a stable-close vector
And the returned vector has length 512, finite values and L2 norm
approximately equal to 1

### Requirement: model switch integration test

The release pipeline MUST include a model-switch integration test
that indexes with EmbeddingGemma 2, switches to Qwen3, switches
back, and asserts that the canonical Git tree is unchanged, the two
profile hashes are different, the two USearch files are distinct,
Gemma vectors are not recomputed on switch back, and results only
come from the active namespace.

#### Scenario: model switch test preserves Git knowledge (verifies: model switch integration test)

Given an index built with EmbeddingGemma 2
When the test switches to Qwen3 and then back to EmbeddingGemma 2
Then the canonical Git tree is unchanged
And the profile hash for the active generation is the EmbeddingGemma 2 hash
And the Qwen USearch file is not opened by the EmbeddingGemma 2 query

### Requirement: real USearch tests

The release pipeline MUST run tests that load the real USearch
native package, persist an index, reload it after a fresh process,
refuse to open a profile mismatch, rebuild from the vector record
store, and demonstrate atomic generation activation. ANN recall MUST
be compared to a flat exact baseline; the release threshold MUST be
defined against the recorded benchmark rationale.

#### Scenario: USearch persistence test (verifies: real USearch tests)

Given an index written to disk
When a fresh process opens the same cache root
Then the index loads without re-embedding
And a profile mismatch raises a structured error rather than mixing
vector spaces

### Requirement: branch reconciliation test matrix

The release pipeline MUST run the full branch reconciliation test
matrix from plan §68: identical knowledge, added chunk, modified
chunk, removed chunk, changed graph edge, changed source code,
return switch, dirty working tree, dirty-to-clean and clean-to-dirty
scenarios, switch while model indexing, switch while a query
arrives, crash during reconciliation, corrupted active index and
missing previous runtime snapshot.

#### Scenario: branch reconciliation matrix passes (verifies: branch reconciliation test matrix)

Given a complete branch reconciliation test matrix
When every scenario is executed
Then no scenario returns evidence unique to the old branch
And the active USearch generation matches the new effective corpus

### Requirement: real Docling tests

The release pipeline MUST run Docling integration tests against the
fixtures listed in plan §71 (native-text PDF, scanned PDF, mixed
PDF, tables, figures, captioned figure, multi-page table, 100-page
PDF, generated 600-page PDF). The tests MUST verify that the real
`DocumentConverter` is invoked, that page provenance is preserved,
that tables are structured, that table headers are repeated across
chunks, that figures and assets are linked, that selective OCR is
honoured, that resume after failure works, and that memory is
bounded.

#### Scenario: real Docling integration tests cover the plan §71 fixtures (verifies: real Docling tests)

Given the release pipeline is configured for a production Docling
profile
When the Docling integration tests run
Then every fixture listed in plan §71 is exercised
And the real `DocumentConverter` is invoked for each fixture
And page provenance, table headers, figures, selective OCR, resume
after failure and memory bounding are all verified

### Requirement: first-run end-to-end acceptance

The release pipeline MUST run a first-run end-to-end acceptance test
from an empty machine with Docker and network that mounts a target
project, runs one command, selects Gemma, waits for readiness,
queries over the project source, restarts the container and queries
again without re-downloading or re-embedding unchanged content. The
test MUST be repeated with Qwen3.

#### Scenario: first-run acceptance from empty machine (verifies: first-run end-to-end acceptance)

Given an empty machine with Docker and network
When the operator runs the one-command UX against a mounted target
repository
Then the control plane becomes ready within the documented budget
And the same query before and after a container restart returns
equivalent retrieval results
And the model weights are not re-downloaded
And unchanged vectors are not re-embedded

### Requirement: truthful capability reporting

`project.describe_capabilities` MUST report every production
component as either real-and-available, real-and-not-installed, or
disabled, together with model identifier, immutable revision,
dimension and execution device where applicable. The platform MUST
NEVER report a stub component as available.

#### Scenario: capability report is truthful (verifies: truthful capability reporting)

Given a production configuration with all real components
When the capability endpoint is queried
Then every component is reported as real-and-available
And no component is reported as `available=true` while raising
`EmbeddingModelError` from `embed`

### Requirement: no-stub inventory scan

Before declaring a production release the platform MUST scan the
production package for the markers `pinned-stub`, `not bound`,
`usearch-stub`, synthetic Docling document and `STUB`. Every
occurrence MUST be either removed or strictly located in test or
development-only code.

#### Scenario: stub inventory scan finds no production stubs (verifies: no-stub inventory scan)

Given a production code tree
When the stub inventory scan runs
Then no production file contains `pinned-stub`, `not bound`,
`usearch-stub`, or a synthetic Docling document
And any stub occurrence is strictly inside `tests/` or
`development/` paths

### Requirement: license inventory and SBOM

The release pipeline MUST run the license gate, the SBOM
generation and the NOTICE generation for the actual production
image, not only for the source package. The dependency inventory
MUST list sentence-transformers, transformers, torch, huggingface-hub,
usearch, numpy, docling, docling-core and transitive runtime
dependencies with their SPDX identifiers.

#### Scenario: production image SBOM lists the documented dependencies (verifies: license inventory and SBOM)

Given the production OCI image has been built
When the license gate, SBOM generator and NOTICE generator run
against the actual image
Then sentence-transformers, transformers, torch, huggingface-hub,
usearch, numpy, docling, docling-core and their transitive runtime
dependencies all appear in the SBOM
And every entry carries the correct SPDX identifier
And the license gate passes against the image (not only the source
package)

### Requirement: CLI status commands

The `embedding-status` command MUST NOT hard-code a hashing backend.
`retrieval-status` MUST report the active model, active embedding
profile identity, dense backend, current generation, vector count,
index count, sparse index and readiness. `capabilities` MUST use
the same runtime composition as the production path.

#### Scenario: CLI status commands report the live production state (verifies: CLI status commands)

Given the production runtime is ready and serving
When the operator runs `embedding-status`, `retrieval-status` and
`capabilities`
Then `embedding-status` derives its hashing backend from the active
profile rather than a hard-coded constant
And `retrieval-status` reports the active model, profile identity,
dense backend, current generation, vector count, index count, sparse
index and readiness
And `capabilities` resolves the same composition the production
path uses, not a parallel stub
