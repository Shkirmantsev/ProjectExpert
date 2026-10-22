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
  - openspec/specs/2026-10-18-persisted-runtime-snapshot-reconciliation/spec.md
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
`.project-intelligence-cache/runtime-state/snapshot.json`. This authoritative
bundle contains active, manifest and source state and is replaced atomically.
The three original JSON files remain compatibility projections; old installs
are migrated into a coherent bundle before a projection can be overwritten.
A crash between projection writes cannot mix two served generations. `commit()` and `read_snapshot()`
are the two halves; `diff()` classifies the candidate snapshot
against the persisted one.

## Version monitor

`pi_platform.core.sync.version_monitor.ProjectVersionMonitor`
is the abstract poll contract. `PollingProjectVersionMonitor` is wired by
`start` and `serve`: it polls every three seconds (configurable within 2–5),
checks HEAD/branch and hashes discovered source contents plus canonical JSON.
Repeated edits with unchanged Git porcelain status still trigger refresh.
Runtime cache writes do not. Model/device/document settings changes trigger a
refresh as well. Failed builds retry without requiring another edit; changes
made during indexing are detected before publication and retried.
`ProjectVersionMonitorStub` is only a no-op lifecycle test double.

The complete hydrate → discover → index → snapshot → publication transaction
holds a project file lock under the target cache `locks/` directory. A shared
readiness lock also serializes monitor and administrative workers in-process.
HTTP starts with readiness false; retrieval remains closed during refresh and
after failures, while static UI, health, wizard and status stay accessible.

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
- Production refresh marks readiness false before mutation. Retrieval refuses
  evidence until a candidate matching the current Git/content state has been
  activated and published; failed candidates do not advance the active snapshot.

## Round trip

The Phase 1 hydrate → materialise round trip preserves durable
knowledge: when no runtime change is introduced, the produced
Git diff is empty. The
[`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py)
`SyncRoundtripTests` cover this contract.


## Native generation recovery

Production indexing derives generation identity from each chunk ID paired with
its retrieval-text hash and the embedding profile. A valid cached native file
loads without rewriting it or recomputing document embeddings. Generation-local
metadata and key sidecars must match profile, dimension, count, corpus keys and
schema; a sample query validates the saved native candidate before rename.
Missing/corrupted native files or metadata rebuild from authoritative SQLite
vectors. Invalid vector records are recomputed individually. The legacy
`index_meta.json` is a diagnostic view, not an activation pointer.

`tests/test_native_generation_recovery.py` covers cache reuse, corruption,
missing snapshots, operator precedence, failed activation and real subprocess
exit during snapshot publication. Its controlled embeddings are independent of
real-model quality checks. The seeded native recall benchmark achieved 0.998
Recall@10 on 1,000 normalized 64d vectors and 50 held-out queries against exact
cosine, with a 0.90 acceptance floor; broader semantic and scale acceptance
remains separate.

## Owned SQLite handles on Windows

File-backed vector stores use operation-scoped SQLite connections and close them
on success or failure; retained retrieval runtime objects do not keep database
files locked. Adapters given an existing connection preserve the caller's
transaction and ownership. PDF figure lookup also closes its temporary handle.
`tests/test_vector_record_store.py` exercises closure, errors and file rename;
Windows CI additionally verifies target repository teardown.
