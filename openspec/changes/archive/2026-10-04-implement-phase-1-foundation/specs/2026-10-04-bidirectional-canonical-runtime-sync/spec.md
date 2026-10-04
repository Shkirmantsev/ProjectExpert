# bidirectional-canonical-runtime-sync Specification delta (Phase 1 addendum)

This delta pins the concrete `platform/core/sync/` services that
the Phase 1 implementation delivers. The base specification in
[`openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md`](../../../../specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md)
remains authoritative for the platform-level contract.

## ADDED Requirements

### Requirement: HydrateService contract

The Phase 1 implementation MUST provide a
`pi_platform.core.sync.hydrate.HydrateService` class with a
`restore_runtime(...)` method that:

1. resolves the Git HEAD and working-tree state of the target
   repository via the `GitPort` adapter;
2. loads the canonical manifests under
   `project-knowledge/manifests/`;
3. restores the runtime cache (filesystem content-addressed cache
   under `.project-intelligence-cache/`) using the per-shard
   content hash as the primary key;
4. applies the working-tree overlay;
5. returns a `HydrateReport` dataclass with per-family shard
   counts and per-family cache hit rates.

The graph, sparse, dense indexes and embedding cache are not
populated by Phase 1; the `HydrateReport` accurately records them
as `not_implemented` for later phases rather than silently leaving
them absent.

#### Scenario: cold-start hydrate restores shards

Given a target repository with one shard in
`project-knowledge/objects/aa/aa00.json`
When `HydrateService.restore_runtime` is called with no warm cache
Then the runtime cache registers the shard under the cache key
equal to the shard's content hash
And the `HydrateReport.objects.cache_hit_rate == 0.0`.

#### Scenario: warm-start hydrate reports cache hits

Given a target repository with one shard already cached
When `HydrateService.restore_runtime` is called
Then the `HydrateReport.objects.cache_hit_rate == 1.0`
And no second normalise step is performed for that shard.

### Requirement: ReconcileService contract

The Phase 1 implementation MUST provide a
`pi_platform.core.sync.reconcile.ReconcileService` class with a
`reconcile_branch_switch(previous_head, current_head)` method that
performs incremental reconciliation rather than full rebuild. The
returned `ReconcileReport` MUST record:

- the per-family shard counts before and after the switch;
- the per-family reused shard counts;
- the stale fact identifiers detected during reconcile.

#### Scenario: branch switch reuses unchanged shards

Given two branches that share 99 % of their shard content
When `reconcile_branch_switch` is called
Then the `ReconcileReport` reports reused shard count >= 99 % of
the shared shard count
And the operation completes without rebuilding from scratch.

### Requirement: MaterialiseService contract

The Phase 1 implementation MUST provide a
`pi_platform.core.sync.materialise.MaterialiseService` class with a
`materialise_durable_changes(...)` method that:

1. excludes runtime entries sourced from a `LOCAL_ONLY`
   `SourcePromotionPolicy`;
2. calls `PolicyDecisionStub.decide(...)` and aborts when the
   decision is `REQUIRE_APPROVAL` unless an explicit
   `approval_token` argument is provided;
3. writes only durable changes to canonical shard paths;
4. regenerates affected Wiki Markdown via the OKF adapter;
5. runs the OKF conformance validator;
6. runs the license gate against the proposed change set;
7. returns a `MaterialiseReport` with the Git diff summary and
   the list of affected shard identifiers.

The service MUST NOT commit binary runtime artefacts (database
pages, vector indexes, ANN indexes, model caches) into the target
repository.

#### Scenario: materialise is approval-gated

Given a runtime change set
When `materialise_durable_changes` is called without an
`approval_token`
Then it raises `ApprovalRequired`
And no canonical file is rewritten.

#### Scenario: materialise excludes LOCAL_ONLY sources

Given a runtime change set with one LOCAL_ONLY-sourced entity
When `materialise_durable_changes` is called with an
`approval_token`
Then the Git diff excludes the LOCAL_ONLY entity
And the durable change set still includes any non-LOCAL_ONLY
change.

### Requirement: PolicyDecisionStub contract

The Phase 1 implementation MUST provide
`pi_platform.core.sync.policy_stub.PolicyDecisionStub` with a
`decide(action, target)` method returning one of `ALLOW`,
`DENY` or `REQUIRE_APPROVAL`. The default behaviour is:

- `materialise` → `REQUIRE_APPROVAL`;
- `hydrate` → `ALLOW`;
- `reconcile` → `ALLOW`;
- everything else → `REQUIRE_APPROVAL`.

#### Scenario: materialise requires approval by default

Given no operator acceptance token
When `PolicyDecisionStub.decide("materialise", ...)` is called
Then it returns `REQUIRE_APPROVAL`.

### Requirement: ProjectLock contract

The Phase 1 implementation MUST provide
`pi_platform.core.sync.project_lock.ProjectLock` that uses the same
advisory file-lock semantics as
[`scripts/file_lock.py`](../../../../../scripts/file_lock.py)
without importing it. The lock file path is
`tmp/local/project-locks/<project-id>.lock`. The product MUST NOT
own, edit or import `scripts/file_lock.py`; the implementation
duplicates the cross-platform `fcntl`/`msvcrt` semantics.

#### Scenario: concurrent acquisition serialises

Given two `ProjectLock` contexts opened on the same project from
different threads
When both call `acquire()` simultaneously
Then exactly one acquires the lock; the other waits.

### Requirement: WriteAheadLog contract

The Phase 1 implementation MUST provide
`pi_platform.core.sync.wal.WriteAheadLog` that records one JSON line
per materialise step at `.project-intelligence-cache/wal.log`. On
startup:

- if `.project-intelligence-cache/materialise_in_progress` exists,
  the WAL is rolled back to the last committed entry;
- otherwise the WAL is truncated.

#### Scenario: WAL recovers from an interrupted materialise

Given a `materialise_in_progress` marker file and a WAL with
three uncommitted entries
When `WriteAheadLog.recover()` is called
Then the WAL is truncated to the last committed entry
And no canonical file remains in an inconsistent state.