# 2026-10-04-runtime-store Specification delta (MODIFIED)

Covers plan §23, §24, §26, §29, §42 (PR 5, PR 6, PR 8 of §79).

## Purpose

Reconcile the accepted runtime store contract with the production
requirements that:

- the `VectorRecordStore` is the authoritative embedding storage;
- dense numeric keys are tracked through a separate
  `dense_keys` table keyed by `(embedding_profile_hash,
  numeric_key, chunk_id)` so chunk IDs and USearch numeric keys
  cannot silently diverge;
- the active dense generation is identified by
  `source_generation = SHA256(active chunk IDs + retrieval text
  hashes + embedding profile hash + index schema version)` and
  not by Git branch;
- a persisted active runtime snapshot is written only after
  successful reconciliation and atomic index activation;
- removed chunks are tombstones in the active sparse index and
  absent from the active dense generation.

This delta is **MODIFIED** (not ADDED); the existing runtime
store port signature is preserved. New tables, new
identifiers and new lifecycle hooks are defined.

## MODIFIED Requirements

### Requirement: dense numeric key map table

The runtime store MUST expose a `dense_keys` table with the
schema:

```sql
CREATE TABLE dense_keys (
    embedding_profile_hash TEXT NOT NULL,
    numeric_key INTEGER NOT NULL,
    chunk_id TEXT NOT NULL,
    PRIMARY KEY (embedding_profile_hash, numeric_key),
    UNIQUE (embedding_profile_hash, chunk_id)
);
```

Numeric keys MUST be allocated by a monotonic counter and MUST
NOT be derived from a truncated hash without collision
handling. Profile mismatch on insert or lookup MUST raise a
structured error.

#### Scenario: numeric key allocation is monotonic per profile

Given a runtime store opened for embedding profile hash P
When two chunks are appended
Then the first chunk receives numeric key 1
And the second chunk receives numeric key 2
And no two rows in `dense_keys` for P share the same
`chunk_id`.

#### Scenario: profile mismatch on numeric key insert is rejected

Given a runtime store opened for embedding profile hash P
When a chunk is appended with a vector labelled with a
different profile hash
Then the append fails with a structured
`EmbeddingProfileMismatchError`
And no row is written to `dense_keys`.

### Requirement: active dense index generation identifier

The runtime store MUST compute
`source_generation = SHA256(active chunk IDs + retrieval text
hashes + embedding profile hash + index schema version)` and
MUST persist it with the active index metadata. The identifier
MUST NOT be the Git branch name.

#### Scenario: source generation changes when retrieval text changes

Given two persisted vector records whose retrieval text hash
differs
When the runtime store computes `source_generation`
Then the new identifier differs from the previous one
And the active index metadata records the new identifier.

### Requirement: persisted active runtime snapshot

The runtime store MUST expose a `runtime-state/` subtree that
records the last successful runtime snapshot, naming the active
project version, its branch, HEAD, working-tree fingerprint,
manifest snapshot hash, source snapshot hash, embedding profile
identity, active index generation and the last successful
refresh identifier. The snapshot MUST be written only after
reconciliation and atomic index activation succeed.

#### Scenario: snapshot is written only after activation

Given a refresh that fails to validate the candidate dense
generation
When the refresh terminates
Then the persisted active runtime snapshot is unchanged
And the previous generation remains active.

#### Scenario: snapshot records working-tree fingerprint

Given a refresh that succeeds
When the snapshot is written
Then it records the current Git HEAD, the current branch, the
current working-tree fingerprint, the manifest snapshot hash,
the source snapshot hash, the active embedding profile hash
and the active index generation.

### Requirement: removed chunks are tombstones

When reconciliation marks a chunk as REMOVED, the runtime
store MUST mark the chunk's sparse entry as `tombstoned` and
MUST remove its vector from the active dense generation on the
next atomic activation. The removed chunk MUST NOT be
searchable in the active retrieval path.

#### Scenario: removed chunk is not searchable after refresh

Given chunk C is in the persisted active runtime snapshot
And the next reconciliation marks C as REMOVED
When the refresh completes
Then a query for the topic of C returns no hits from C
And the active dense generation does not contain C's vector
And the active sparse index marks C as `tombstoned`.
