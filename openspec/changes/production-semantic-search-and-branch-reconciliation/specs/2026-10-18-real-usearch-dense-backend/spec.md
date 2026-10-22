# real-usearch-dense-backend Specification delta

Covers plan §21–§23, §29, §30, §42, §67 (PR 6 of §79).

## Purpose

Define the production dense retrieval backend: a real native
approximate-nearest-neighbour index (USearch, plan §101:
cosine metric, add/search, save/load/view, configurable connectivity
and expansion — https://github.com/unum-cloud/USearch) with a stable
mapping between string chunk identifiers and numeric index keys,
content-derived generation identity, atomic build and activation, and
rebuild from the vector store without re-embedding. The flat in-memory
backend remains available for tests and small corpora but MUST NOT be
reported as the production backend.

## ADDED Requirements

### Requirement: real native backend in production

In the production profile the dense backend MUST be the real native
approximate-nearest-neighbour backend, and the platform MUST NOT report
or serve a flat-memory stand-in as the production dense backend.

#### Scenario: production backend is reported as real (verifies: real native backend in production)

Given the production profile with the native dense backend installed
When the platform reports capabilities
Then the dense backend is reported as real
And no stub marker appears in the report

### Requirement: stable identifier mapping

The platform MUST map string chunk identifiers to stable numeric index
keys and back so that search results resolve to the same chunk
identifiers after save, load and process restart. Key reuse across
different chunk identifiers MUST NOT occur within a namespace.

#### Scenario: identifiers round-trip through numeric keys (verifies: stable identifier mapping)

Given a namespace containing chunks with string identifiers
When the platform indexes, saves, reloads and searches the namespace
Then every search result resolves to the original string identifier

### Requirement: generation identity

The platform MUST identify each index generation by a content hash over
the active chunk identifiers, their retrieval-text hashes, the profile
identity and the index schema version, and MUST store the generation
artifacts together with metadata recording the profile identity,
generation, vector count and schema version.

#### Scenario: profile change produces a different generation (verifies: generation identity)

Given a generation built under profile identity A
When the active profile becomes identity B
Then the generation identity differs from the A generation
And the A generation is not opened for B queries

### Requirement: atomic build and activation

The platform MUST build each generation into a temporary artifact,
validate profile identity, dimension, expected vector count, the
index metadata file, and a sample of representative queries,
atomically publish it, and only then record it as active. A
failed build MUST leave the previously active generation active and MUST
NOT mark incomplete state as current.

#### Scenario: failed build keeps previous generation active (verifies: atomic build and activation)

Given an active generation G1
When a build of G2 fails validation
Then G1 remains the active generation
And the failed artifact is discarded
And readiness is not falsely reported as current for G2

### Requirement: rebuild without re-embedding

The platform MUST be able to rebuild any generation from the vector
store alone and MUST NOT invoke the embedding model during rebuild.

#### Scenario: rebuild does not re-embed (verifies: rebuild without re-embedding)

Given a populated vector store and a missing index artifact
When the platform rebuilds the dense index
Then the rebuild finishes using stored vectors only
And the embedding model is not invoked

### Requirement: corrupt artifacts fail safely

When a generation artifact is corrupt or its metadata is incompatible
with the active profile, the platform MUST refuse to serve it, MUST
rebuild from the vector store, and MUST NOT return results from the
corrupt artifact.

#### Scenario: corrupt artifact triggers rebuild (verifies: corrupt artifacts fail safely)

Given a corrupt generation artifact on disk
When the platform attempts to activate it
Then it is rejected
And a rebuild from the vector store is started
And no search results are served from the corrupt artifact

### Requirement: generation reuse across switches

The platform MAY reuse an existing valid generation when the platform
returns to a previously seen combination of active content and profile
identity, and such reuse MUST NOT require recomputing vectors.

#### Scenario: returning to a previous branch reuses its generation (verifies: generation reuse across switches)

Given generation G-A for branch A and the active branch becomes A again
When the platform activates the dense index
Then G-A is reused if its metadata is still valid
And no vectors are recomputed
