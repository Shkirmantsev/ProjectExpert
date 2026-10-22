# 2026-10-04-runtime-store Specification

## Purpose
Cache content-addressed runtime artefacts across Git versions with recoverable writes, state-aware status, and version identity.
## Requirements
### Requirement: per-shard content-addressed cache

The `RuntimeStore` MUST expose a content-addressed cache where every
cached artefact is keyed by its SHA-256 hex digest (the Phase 1
`content_address_bytes` helper). The cache layout MUST mirror the
§10.2 `objects/<prefix>/<hash>.json` sharding pattern so identical
artefacts across Git branches share one canonical entry.

#### Scenario: cross-branch cache reuse

Given a first store write of `Chunk` `c-1` on branch `A` that
produces content address `sha-256:A`
When the same `Chunk` `c-1` is written on branch `B` to the same
runtime cache root
Then the store does not allocate a new entry for `sha-256:A`
And the store reports a single cache hit on the second write
And the canonical entry under `objects/<prefix>/<hash>.json` is
shared between branches.

### Requirement: version stamp on every write

Every mutation against the `RuntimeStore` MUST record the
`VersionIdentity` tuple from the Phase 1
`git-version-aware-runtime` spec so the runtime store can be queried
for its bound project version.

#### Scenario: store reports the bound version identity

Given a runtime cache initialised against
`VersionIdentity(gitHead="abc", workingTreeFingerprint="def",
knowledgeSchemaVersion="0.1.0", embeddingModelVersion="unknown",
indexSchemaVersion="0.1.0")`
When `runtime_status()` reports the store state
Then the report includes the bound `gitHead`,
`workingTreeFingerprint`, `knowledgeSchemaVersion`,
`embeddingModelVersion` and `indexSchemaVersion` values.

### Requirement: write-ahead log on every mutation

The `RuntimeStore` MUST append every mutation to a per-store WAL
under `.project-intelligence-cache/wal/`. The WAL MUST be replayable
by the Phase 1 `wal-recover` CLI command.

#### Scenario: WAL tail is replayable after a crash

Given a store write that crashes after the cache file is written
but before the index is updated
When `wal-recover` runs against the cache root
Then the WAL tail is replayed and the index is brought back to the
post-crash expected state
And no cache entries are lost.

### Requirement: per-project advisory file lock

The `RuntimeStore` MUST serialise mutations per target project via
the Phase 1 advisory file lock from
`pi_platform/core/sync/project_lock.py`. No new lock primitive is
introduced.

#### Scenario: concurrent writers serialise via the advisory lock

Given two `RuntimeStore` instances pointed at the same cache root
for project `p`
When both attempt a write at the same time
Then one write acquires the advisory lock and proceeds
And the other write waits and then proceeds once the first write
releases the lock
And the cache file system never observes a torn write.

### Requirement: KnowledgeStateFilter projection

The `RuntimeStore` MUST honour the `KnowledgeStateFilter` projection
set when restoring the runtime state. The default projection is
`KnowledgeStateFilter.DURABLE` (exclude `LOCAL_ONLY` facts); the
`KnowledgeStateFilter.ALL` and `KnowledgeStateFilter.STALE`
projections are opt-in via the `runtime-status` CLI flag.

#### Scenario: default projection excludes LOCAL_ONLY facts

Given a store holding one `LOCAL_ONLY` fact and one durable fact
When `runtime_status()` runs with the default projection
Then the report lists only the durable fact count
And the `LOCAL_ONLY` fact count is reported under the
`KnowledgeStateFilter.ALL` projection flag only.

### Requirement: dual-backend compatibility through the port

The `RuntimeStorePort` MUST be implementable by an SQLite default
backend and a PostgreSQL opt-in backend without leaking backend-
specific details into the port surface. The backend MUST be replaced
through the `project-context.yaml:storage.backend` configuration
value.

#### Scenario: backend swap does not change observable behaviour

Given a test that swaps the `SqliteRuntimeStore` default adapter for
a `PostgresRuntimeStore` adapter implementing the same port
When the test writes and reads canonical chunks through the port
Then the observable behaviour (write/read round-trip, content
address, version stamp, WAL append, file lock) is identical between
the two adapters.

### Requirement: phase 1 stub backward compatibility

The Phase 1 `pi_platform.runtime.cache.RuntimeCache` MUST continue to
expose the same `put` / `get` / `has` / `evict` / `stats` surface so
existing Phase 1 callers (init-project, hydrate, materialise) and
the Phase 2 driver continue to work without modification.

#### Scenario: phase 1 cache put/get round-trips after replacement

Given the Phase 1 `RuntimeCache` after the Phase 3 default adapter
replacement
When a Phase 1 caller invokes `put("chunk", body)` followed by
`get(content_hash)`
Then the `get` call returns the same body that was `put`.

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

