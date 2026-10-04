# content-addressed-processing Specification delta

Covers architecture section §13 (Content-Addressed Processing). The
spec defines the SHA-256 cache key contract, the cross-branch reuse
semantics and the property-based cross-branch reuse test that the
Phase 2 ingestion pipeline relies on. It extends the Phase 1
`canonical-knowledge-schema` content-address contract by adding
runtime cache reuse across Git branches.

The Phase 1 `canonical-knowledge-schema` capability defines the SHA-
256 content address (`pi_platform.core.canonical.content_address.
content_address(...)`) used to identify equivalent chunks;
`content-addressed-processing` defines the cross-branch reuse
semantics on top of that contract.

## ADDED Requirements

### Requirement: SHA-256 cache key contract

The platform MUST use the SHA-256 hex digest of the deterministic
canonical serialization of every durable artefact
(`Chunk`, `ContextualChunk`, `Entity`, `Relation`, `Evidence`,
`Document`, `Section`) as the runtime cache key. The cache key MUST
be computed by `pi_platform.core.canonical.content_address.
content_address(...)` for `Chunk` and by an analogous helper for
every other value type, so that two equivalent in-memory instances
produce the same cache key.

#### Scenario: equivalent chunks share the same cache key

Given two `Chunk` instances with the same `rawText` but different
`metadata` values
When `content_address(chunk)` is invoked on each
Then both calls return the same SHA-256 hex digest
And the runtime cache reports a single entry under that key.

### Requirement: cross-branch cache reuse

When the runtime cache observes a content address that was computed on a previous Git branch for the same ProjectVersion, the cache MUST reuse the previous chunk body, entity body and embedding without re-parsing or re-embedding.

#### Scenario: identical content shares the cache entry across branches

Given branch `main` that has been hydrated and the runtime cache
holds chunk `c-1` at `sha-256:A`
When the platform switches to branch `feature/x` and the same source
file yields chunk `c-1'` at `sha-256:A`
Then the runtime cache reports a cache hit for `sha-256:A`
And no second normalise step is performed for `c-1'`
And the hydrate report for `feature/x` lists `sha-256:A` under the
`cacheHit` count and zero under the `cacheMiss` count.

### Requirement: cross-branch reuse property test

The platform MUST expose a property-based test in
`tests/test_content_address_cross_branch.py` that:

- generates at least 100 random `Chunk`, `Entity` and `Relation`
  instances with shuffled insertion order;
- simulates two Git branches by computing the same artefact's
  content address twice in independent random contexts;
- asserts that the two content addresses are equal and the runtime
  cache reports a single cache hit;
- asserts that the existing Phase 1 round-trip test
  `tests/test_canonical_roundtrip.py` continues to pass byte-for-byte.

#### Scenario: cross-branch reuse property test passes

Given the property-based test in
`tests/test_content_address_cross_branch.py` invoked with 100 random
artefact seeds per value type
Then the test passes for every seed
And the test reports a single cache hit per content address pair
And the Phase 1 `tests/test_canonical_roundtrip.py` test continues to
pass unchanged.

### Requirement: cache key portability

The content address MUST be stable across platforms (CPU
architectures, line endings, filesystem encodings) because the
canonical serializer fixes `\n` line endings and the SHA-256 input
is the deterministic canonical JSON bytes. The platform MUST NOT
introduce environment-dependent inputs (timestamps, hostnames,
build paths) into the content-addressed computation.

#### Scenario: same content produces same key on any platform

Given the same `Chunk` instance serialised on two different host
machines
When `content_address(chunk)` is invoked on each
Then both calls return the same SHA-256 hex digest
And the test report does not list any environment-dependent input.

### Requirement: cache eviction by source identity

When the underlying Source changes (the Source.contentHash diverges from the cached entry's Evidence.sourceHash), the runtime cache MUST evict the stale cache entry and recompute the content-addressed artefact.

#### Scenario: source change evicts stale cache entry

Given a previous cache entry for `Chunk` `c-1` with
`Evidence.sourceHash=sha-256:S1`
When the underlying `Source` changes to `sha-256:S2` and a new
parse run completes
Then the runtime cache evicts the `sha-256:S1` entry for `c-1`
And the new entry under `sha-256:S2` is recorded
And the canonical snapshot under `project-knowledge/chunks/` is
preserved.

## Phase 2 task coverage

The change lists Phase 2 task 47 (`platform.core.canonical.Content
Address` final contract + cross-branch reuse test) and task 57
(`content-addressed-processing` spec scenarios).

Out of scope:

- the actual runtime DB storage of the cache (Phase 3 task 62);
- the ANN dense index of the chunk content addresses (Phase 4 task
  71);
- the embedding cache reuse (Phase 4 task 70 — the contract for the
  embedding cache is a separate capability that depends on this one).