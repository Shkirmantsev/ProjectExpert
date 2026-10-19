---
id: interfaces.sync
title: Sync interface reference
kind: interfaces
status: active
summary: Reference for the hydrate, reconcile, materialise, WAL, project lock, persisted runtime snapshot and version monitor interfaces implemented by Phase 1 / production semantic search.
sourceRefs:
  - pi_platform/core/sync/hydrate.py
  - pi_platform/core/sync/reconcile.py
  - pi_platform/core/sync/materialise.py
  - pi_platform/core/sync/wal.py
  - pi_platform/core/sync/project_lock.py
  - pi_platform/core/sync/policy_stub.py
  - pi_platform/core/sync/version_snapshot.py
  - pi_platform/core/sync/version_monitor.py
  - openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md
  - openspec/changes/production-semantic-search-and-branch-reconciliation/specs/2026-10-18-persisted-runtime-snapshot-reconciliation/spec.md
maintenance:
  mode: authored
---

# Sync interface reference

Implements the
[`bidirectional-canonical-runtime-sync`](../../../openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md)
spec.

## Hydrate

`pi_platform.core.sync.hydrate.HydrateService.restore_runtime(repo_root, cache_root)`
returns a `HydrateReport` with `project_version`, `families`,
`cache_hit_rates` and `stale_fact_ids`. Phase 1 only hydrates the
canonical layer and the content-addressed runtime cache; the
graph index, sparse index, dense index and embedding cache are
populated in Phases 3-4.

## Reconcile

`pi_platform.core.sync.reconcile.ReconcileService.reconcile_branch_switch(repo_root, previous_head, current_head, cache_root)`
returns a `ReconcileReport` with `families`, `reused_shards`,
`re_ingested_shards` and `stale_fact_ids`. Unchanged shards
between the two heads are not re-ingested.

`ReconcileService.reconcile_with_snapshot(repo_root, cache_root, snapshot)`
is the production-semantic-search entry point: it diffs the
persisted `RuntimeSnapshot` against the current effective
snapshot (HEAD + working-tree fingerprint + canonical manifests
+ discovered source inventory) via `RuntimeSnapshotService.diff()`
(classifies each item as UNCHANGED / ADDED / MODIFIED / REMOVED),
then atomically activates the new dense index generation when
the activation validation succeeds. REMOVED items become
tombstones in the sparse index and `dense_index.delete_chunk`
calls. When the activation fails, `ReconcileActivationError` is
raised, the previous generation stays active and the persisted
snapshot is not advanced.

## Persisted runtime snapshot

`pi_platform.core.sync.version_snapshot.RuntimeSnapshotService`
persists the last successful snapshot — branch, HEAD,
working-tree fingerprint, manifest hash, source hash, embedding
profile identity, active index generation, last successful
refresh identifier — under
`.project-intelligence-cache/active-runtime.json`. Writes go
through `.tmp` + `os.replace`; a crash mid-write leaves the
previous snapshot untouched. `commit()` and `read_snapshot()`
are the two halves; `diff()` classifies the candidate snapshot
against the persisted one.

## Version monitor

`pi_platform.core.sync.version_monitor.ProjectVersionMonitor`
is the abstract poll contract; the default
`ProjectVersionMonitorStub` polls the Git HEAD and the
working-tree fingerprint every 2-5 seconds and schedules a
reconcile when either changes. The monitor MUST NOT depend on
OS-specific filesystem watchers.

## Materialise

`pi_platform.core.sync.materialise.MaterialiseService.materialise_durable_changes(repo_root, cache_root, approval_token=None, changes=None)`
returns a `MaterialiseReport` with `diff_files`,
`excluded_local_only`, `policy_decision` and
`okf_validation_errors`. The service is approval-gated: when
`approval_token` is omitted and the policy decision is
`REQUIRE_APPROVAL`, the call raises `ApprovalRequired` and writes
nothing.

LOCAL_ONLY-sourced runtime changes are excluded from the diff;
they remain in the runtime cache but never reach the canonical
tree.

## Policy decision

`pi_platform.core.sync.policy_stub.PolicyDecisionStub.decide(action, target)`
returns one of `PolicyDecision.ALLOW`, `PolicyDecision.DENY` or
`PolicyDecision.REQUIRE_APPROVAL`. Default behaviour:

- `hydrate` → `ALLOW`
- `reconcile` → `ALLOW`
- `materialise` → `REQUIRE_APPROVAL`
- everything else → `REQUIRE_APPROVAL`

The full central Policy Engine arrives in Phase 7
([`adr.ports-and-adapters-extension-style`](../adr/0004-ports-and-adapters-extension-style.md)).

## Project lock

`pi_platform.core.sync.project_lock.ProjectLock(project_id, root)`
is a context manager that acquires an advisory file lock at
`tmp/local/project-locks/<project-id>.lock`. The lock uses
`fcntl.flock` on POSIX and `msvcrt.locking` on Windows with the
same semantics as `scripts/file_lock.py` but does NOT import the
harness script.

On Windows, acquisition locks byte zero directly, including when the lock
file is empty. It does not read or write that byte before locking: another
handle holding the lock prevents that I/O. Both blocking and timed
acquisition use this approach.

## Write-ahead log

`pi_platform.core.sync.wal.WriteAheadLog` records one JSON line
per materialise operation. Recovery behaviour:

- `materialise_in_progress` marker present → rollback to the
  last committed entry;
- no marker → truncate the WAL.

## Concurrency

- `hydrate` and `materialise` are serialised per project via the
  `ProjectLock` advisory file lock.
- `reconcile` can run in parallel with read-only retrieval
  operations because the runtime store presents a consistent
  snapshot through a version stamp.

## Round trip

The Phase 1 hydrate → materialise round trip preserves durable
knowledge: when no runtime change is introduced, the produced
Git diff is empty. The
[`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py)
`SyncRoundtripTests` cover this contract.
