# bidirectional-canonical-runtime-sync Specification

## Purpose
Define the bidirectional synchronization contract between the Git-
portable canonical knowledge (the durable source of truth) and the
runtime working knowledge store (the active operational state), so
that durable changes can be hydrated into the runtime store on
checkout and that enriched runtime knowledge can be materialised
back into the canonical tree.

## Requirements

### Requirement: hydrate loads canonical knowledge into runtime

When the platform starts up or reconciles after a Git-state change, the platform MUST run a hydrate operation that:

1. resolves the Git HEAD and working-tree state of the target
   repository;
2. loads the canonical manifests for the current Git state;
3. restores the runtime working knowledge store from canonical
   shards using the per-shard content hash as the primary key;
4. applies the working-tree overlay to the running store;
5. detects and surfaces stale derived knowledge in the hydrate
   report;
6. starts/continues MCP, A2A, REST and UI services only after the
   hydrate step reports a consistent state.

The graph index, sparse index, dense index and embedding cache are
added in Phases 3-4 by their respective capabilities. Until those
phases ship, hydrate operates over the canonical layer and the
runtime cache; the `hydrateReport` MUST accurately reflect what was
restored so missing-family behaviour is observable, not silently
absent.

#### Scenario: cold start on populated repository

Given a target project with a populated `project-knowledge/` tree
And no prior runtime cache
When the platform starts up
Then the platform reads every manifest, materialises shards into
the runtime working knowledge store, and reports counts per
knowledge family in the hydrate report
And the platform does not start serving MCP/A2A/REST traffic until
hydrate is consistent.

#### Scenario: warm start reuses cache

Given a target project with a populated canonical tree and a warm
runtime cache whose entries match the canonical content hashes
When the platform starts up
Then the platform hydrates from cache without re-normalising
unchanged content
And the platform reports per-family cache hit rates in the hydrate
report.

### Requirement: enrich runtime knowledge from sources

After hydration, the platform MUST accept new and changed source
inputs from:

- changed source files in the target repository (auto-detected
  between the previous and current Git state);
- `tmp/local/source/**` recursive scan;
- configured external-documentation directories;
- configured JAR artifacts and source JARs;
- OpenSpec change files under `openspec/changes/` and adopted
  specs under `openspec/specs/`;
- configured web/Confluence sources (when enabled).

For each new or changed input the platform MUST:

1. select a parser by content type and source family;
2. compute a content hash;
3. parse and chunk the input using semantic/structural boundaries;
4. contextualise chunks (deterministic + domain-rule + optional LLM);
5. extract candidate entities and relations;
6. produce dense embeddings and sparse index terms;
7. record provenance, source reference and content hash in the
   runtime working knowledge store;
8. mark any prior runtime entry whose source has changed as stale.

Deleted sources MUST invalidate or mark derived knowledge as stale
according to provenance.

#### Scenario: new source in tmp/local/source

Given a new PDF under `tmp/local/source/requirements/` with policy
`LOCAL_ONLY`
When the inbox scanner runs
Then the platform parses, chunks and indexes the PDF
And no canonical snapshot file is written.

#### Scenario: source deletion marks dependent chunks stale

Given a chunk produced from `requirements.md` previously indexed as
`verified`
When `requirements.md` is deleted from the target repository and
the platform reconciles
Then the chunk is marked `stale`
And the deletion is recorded with provenance.

### Requirement: materialise writes runtime back to canonical

When the operator decides that runtime-enriched knowledge should become durable, the platform MUST support a materialise operation that:

1. lets the operator select which runtime changes to durable-commit;
2. excludes runtime entries that originated from `LOCAL_ONLY`
   sources;
3. normalises the selected entities, relations and chunks;
4. serialises them deterministically;
5. re-shards the affected canonical knowledge families only;
6. updates the affected manifests and content hashes;
7. regenerates affected Wiki concept Markdown when configured;
8. validates provenance, references and license/security policy;
9. produces a Git diff for review;
10. waits for explicit operator/agent approval before committing
    (write/materialization is approval-gated; never automatic);
11. commits to the active branch of the target project.

The materialise operation MUST NOT commit binary runtime artifacts
(database pages, vector indexes, model caches) into the target
repository.

#### Scenario: materialise writes only durable changes

Given runtime changes that include LOCAL_ONLY sources and durable
graph edges
When the operator runs materialise
Then the platform proposes a Git diff containing only the durable
edges and the affected manifest updates
And the diff excludes the LOCAL_ONLY source snapshot
And the platform waits for operator approval before committing.

#### Scenario: materialise is approval-gated

Given an attempt to materialise durable changes
When the materialise operation is triggered by an automated agent
without an explicit operator approval token
Then the platform returns `REQUIRE_APPROVAL` and does not commit.

### Requirement: round-trip preserves durable knowledge

The following round trip MUST preserve equivalent durable knowledge:

```text
Canonical knowledge A
        ↓ hydrate
Runtime working knowledge store
        ↓ materialise
Canonical knowledge B
```

`A` and `B` MAY differ in harmless formatting/order details only if
the deterministic canonical serialization normalises them. For
unchanged knowledge, the round trip MUST produce no Git diff.

#### Scenario: idempotent round trip

Given a target project with a populated canonical tree
When the platform hydrates and immediately materialises without
runtime changes
Then the produced Git diff is empty.

#### Scenario: round trip after enrichment

Given the runtime working knowledge store has absorbed one new
verified entity and one new verified relation
When the operator runs materialise and commits
Then the canonical tree contains exactly one new entity file and
exactly one new relation file
And no other canonical file is rewritten.

### Requirement: incremental branch-switch reconciliation

A branch switch MUST be an incremental reconciliation operation, not
a mandatory full rebuild. The platform MUST use the per-family
manifest content hashes to:

1. drop or invalidate any runtime entry whose source is no longer
   present on the new branch;
2. hydrate any missing or changed canonical shard using the
   per-shard content hash as the primary cache key;
3. recompute any derived information that is configured to depend on
   the changed shards;
4. refresh sparse/full-text/vector/graph indexes only where needed;
5. apply the new working-tree overlay.

The recompute step respects the platform's "retrieval-first
escalation" — Phase 1 only recomputes information that the Phase 1
contract owns. Embedding, reranker, advanced-retrieval and graph-
index recomputation are added by Phases 3-5 and use the same
content-hash key, so a Phase 1 hydrate does not block a later
phase's recompute.

#### Scenario: branch switch reuses unchanged cache

Given two branches that share most source file content
When the operator switches branches
Then the platform reports the per-shard reuse count and the
re-ingested shard count in the reconcile report
And the switch completes within a documented budget
(`branchSwitchBudgetSeconds`).

### Requirement: stale-knowledge detection on every reconcile

Every hydrate and every incremental reconcile MUST detect and
report stale durable knowledge based on source hash mismatches between
the runtime working knowledge store and the canonical knowledge for
the current Git state.

Detected stale knowledge MUST be recorded in the runtime working
knowledge store and surfaced via the hydrate / reconcile report.
Once Phase 6 ships the MCP server, stale knowledge MUST also be
reportable via the `project.get_conflicts` MCP tool; once Phase 7
ships the control plane UI, it MUST also be reportable via the
control plane status panel. The contract requires the data to
exist; it does not require any specific phase's transport to be
present.

#### Scenario: stale entities recorded on reconcile

Given an entity whose source has changed since the last materialise
When the platform reconciles after a Git pull
Then the entity is marked `stale` in the runtime working knowledge
store
And the reconcile report lists the entity in the stale facts.

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
