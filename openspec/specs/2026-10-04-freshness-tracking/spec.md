# 2026-10-04-freshness-tracking Specification

## Purpose
TBD - created by archiving change implement-phase-3-storage. Update Purpose after archive.
## Requirements
### Requirement: FreshnessTrackerPort contract

The platform MUST expose a `FreshnessTrackerPort` abstract class in
`pi_platform/ports/runtime/freshness.py` with the following
operations:

- `mark_verified(fact_id: str, *, source_hash: str, version:
  VersionIdentity) -> None` — records the `lastVerifiedAt`
  timestamp;
- `is_stale(fact_id: str, *, current_source_hash: str) -> bool`
  returns `True` when the fact's recorded `source_hash` differs
  from `current_source_hash`;
- `derived_staleness(derived_fact_id: str, *, depends_on:
  Sequence[str]) -> bool` returns `True` when any upstream fact is
  stale or unknown;
- `snapshot() -> FreshnessSnapshot` records the per-fact
  `lastVerifiedAt` and the current `current_source_hash` so a
  subsequent reconcile can replay the freshness delta without re-
  reading every fact.

#### Scenario: mark_verified stores the source hash and timestamp

Given a fact `f-1`
When `mark_verified("f-1", source_hash="sha-256:A",
version=VersionIdentity(...))` runs
Then `is_stale("f-1", current_source_hash="sha-256:A")` returns
`False`
And the snapshot includes `lastVerifiedAt` for `f-1`.

#### Scenario: source hash change marks the fact stale

Given a fact `f-1` with recorded `source_hash = "sha-256:A"`
When the source changes to `sha-256:B`
Then `is_stale("f-1", current_source_hash="sha-256:B")` returns
`True`.

### Requirement: derived staleness rule

The `FreshnessTrackerPort.derived_staleness` operation MUST return
`True` when any upstream fact is `stale` or `unknown` so derived
facts do not become orphaned evidence.

#### Scenario: derived fact becomes stale when an upstream fact goes stale

Given a derived fact `d-1` that depends on `f-1`
When `f-1` transitions to `KnowledgeState.STALE`
Then `derived_staleness("d-1", depends_on=["f-1"])` returns `True`.

#### Scenario: derived fact stays verified when all upstreams stay verified

Given a derived fact `d-1` that depends on `f-1`, `f-2`, `f-3`
When all three upstreams remain `KnowledgeState.VERIFIED`
Then `derived_staleness("d-1", depends_on=["f-1", "f-2", "f-3"])`
returns `False`.

### Requirement: FreshnessSnapshot is replayable

The `FreshnessTrackerPort.snapshot()` operation MUST return a
`FreshnessSnapshot` that can be replayed by a subsequent reconcile
without re-reading every fact. The snapshot MUST contain the
`lastVerifiedAt` timestamp per fact and the `current_source_hash`
per fact.

#### Scenario: snapshot round-trips through a reconcile replay

Given a `FreshnessSnapshot` over 1000 facts
When the snapshot is replayed by the reconcile flow
Then the replayed state matches the pre-snapshot state
And the replayed state includes the `lastVerifiedAt` and
`current_source_hash` for every fact.

### Requirement: §55 freshness contract compliance

The freshness tracker MUST follow the §55 freshness contract:

- changed source → dependency / provenance analysis → affected
  knowledge → mark stale / regenerate candidates → verify →
  materialize durable update;
- the tracker MUST NOT silently rewrite authoritative knowledge
  (§55 "avoid uncontrolled rewriting of authoritative knowledge").

#### Scenario: authoritative knowledge is not silently rewritten

Given a `verified` chunk with `lastVerifiedAt` recorded
When a stale-derived candidate suggests the same fact
Then the tracker marks the candidate as `KnowledgeState.STALE`
And the original `verified` chunk is preserved.

### Requirement: FreshnessTracker integration with reconcile

The reconcile flow MUST consume the freshness snapshot to populate
`ReconcileReport.stale_fact_ids` and the `KnowledgeStateFilter
.STALE` projection. The `runtime-status` CLI MUST report the
freshness snapshot so an operator can inspect staleness without
running a full reconcile.

#### Scenario: reconcile populates the stale fact list

Given a freshness snapshot over 100 facts with 10 stale
When the reconcile runs
Then `ReconcileReport.stale_fact_ids` lists the 10 stale facts
And the `runtime-status` CLI reports `stale_facts: 10`.

