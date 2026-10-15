# 2026-10-04-dense-index Specification delta

Covers plan §3.6, §17, §17.1.

## ADDED Requirements

### Requirement: USearch ANN adapter behind the existing port

The platform MUST expose a `USearchDenseIndex` adapter
that implements the existing `DenseIndexPort`. The
adapter MUST persist its index files under
`.project-intelligence-cache/indexes/<embedding_profile_hash>/`
and MUST be git-ignored.

#### Scenario: USearch conforms to the DenseIndexPort contract

Given a `USearchDenseIndex` adapter
When the platform runs the existing
`DenseIndexPort` contract tests
Then the USearch adapter passes the same tests as
`FlatDenseIndex`.

### Requirement: ANN backend selection is configuration-driven

The platform MUST support
`dense_index.backend ∈ {auto, flat, usearch}`. The
selection is configuration / capability driven. `auto`
MAY choose flat vs ANN based on benchmarked corpus
size and recall constraints; the choice MUST be
data-driven, not hard-coded as an architectural
invariant.

#### Scenario: backend is auto-selected by configuration

Given a `dense_index.backend = auto` configuration
When the platform starts
Then the platform chooses `flat` for small corpora
or `usearch` for larger corpora based on the
benchmarked threshold
And the choice is recorded in `index_state`.

### Requirement: index compatibility check

The platform MUST refuse to open an ANN namespace
whose `embedding_profile_hash` does not match the
active `EmbeddingProfile`. The error MUST be clear
and MUST NOT leak secret metadata.

#### Scenario: profile mismatch is rejected

Given an ANN namespace built for
`hashing-fallback`
When the active profile changes to
`embeddinggemma2-512-normalize`
Then the platform rebuilds the ANN from
`VectorRecordStorePort` records that match the new
profile
And the old hashing namespace remains available
under its own profile key.

## MODIFIED Requirements

None. The existing dense-index `Requirements` are
extended additively; their bodies are not rewritten.
