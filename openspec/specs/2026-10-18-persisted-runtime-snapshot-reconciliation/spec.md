# 2026-10-18-persisted-runtime-snapshot-reconciliation Specification

Covers plan §31, §32, §33, §34, §35, §36, §37, §38, §39, §40, §41,
§42, §45, §46 (PR 8 of §79).

## Purpose

Define the runtime reconciliation loop that compares the last
successful persisted runtime snapshot against the current effective
snapshot (Git HEAD + working-tree fingerprint + canonical manifests
+ discovered source inventory), classifies each item as
UNCHANGED / ADDED / MODIFIED / REMOVED, activates a new atomic dense
index generation when valid, and fails closed while the refresh is in
progress. Switching Git branches MUST NOT leave old-branch evidence
searchable in the active retrieval path.

## Requirements

### Requirement: persisted last-served snapshot

The platform MUST persist the last successful runtime snapshot, naming
the active project version, its branch, HEAD, working-tree fingerprint,
manifest snapshot hash, source snapshot hash, embedding profile
identity, active index generation and the last successful refresh
identifier. The snapshot MUST be written only after reconciliation and
index activation succeed.

#### Scenario: snapshot is written only after activation (verifies: persisted last-served snapshot)

Given a refresh that successfully activates a new dense generation
When the activation completes
Then the persisted snapshot records the new branch, HEAD, working-tree
fingerprint, manifest hash, source hash, profile identity, generation
and refresh identifier
And no persisted snapshot is advanced while a refresh is still in
progress or has failed

### Requirement: manifest and source snapshots

The runtime MUST persist a manifest snapshot describing the chunks,
graph nodes and source inventory it last served. The reconciliation
loop MUST compute the new candidate manifest snapshot from the
currently checked-out canonical manifests and the current discovered
source inventory.

#### Scenario: manifest snapshot reflects effective corpus (verifies: manifest and source snapshots)

Given the persisted snapshot has manifest hash M0
And the currently checked-out canonical manifests and source
inventory now hash to M1
When the reconciliation loop runs
Then a new manifest snapshot with hash M1 is built
And only that snapshot is eligible for activation after diff
classification succeeds

### Requirement: old vs new diff with REMOVED handling

For every canonical and source item the reconciliation loop MUST
classify its state as UNCHANGED, ADDED, MODIFIED or REMOVED relative
to the persisted snapshot. Removed items MUST be tombstones in the
active sparse index and absent from the active dense generation.
Modified items MUST invalidate dependent derived records.

#### Scenario: removed chunk is no longer searchable (verifies: old vs new diff with REMOVED handling)

Given chunk C exists on branch A and is in the persisted snapshot
And chunk C does not exist on branch B
When the operator switches from branch A to branch B
And reconciliation completes
Then a query for the topic of C returns no hits from C
And the active sparse index no longer references C
And the active dense generation no longer contains C's vector

### Requirement: working-tree fingerprint triggers refresh

A change of HEAD alone MUST NOT be the only refresh trigger. The
reconciliation loop MUST trigger a refresh when the working-tree
fingerprint differs from the persisted fingerprint even if the HEAD
is unchanged. The same loop MUST trigger a refresh when the HEAD
changes.

#### Scenario: same HEAD but dirty tree triggers refresh (verifies: working-tree fingerprint triggers refresh)

Given the persisted snapshot has HEAD h and working-tree fingerprint f
And HEAD is still h but the working-tree fingerprint is now f'
When the version monitor polls
Then a reconciliation is scheduled
And the new snapshot is persisted only if reconciliation and index activation succeed

#### Scenario: switch back reuses valid cached generation (verifies: working-tree fingerprint triggers refresh)

Given branch A generation AG was valid and persisted
And the operator switched to branch B
And now switches back to branch A
When reconciliation runs
Then the unchanged vectors from AG are reused
And a new generation is built only if AG is no longer valid

### Requirement: background version monitor

The platform MUST run a portable background monitor that polls the
Git HEAD and the working-tree fingerprint at a configurable interval
between 2 and 5 seconds and schedules a reconciliation when either
changes. The monitor MUST NOT depend on OS-specific filesystem
watchers.

#### Scenario: background monitor detects branch switch (verifies: background version monitor)

Given the version monitor is polling every 3 seconds
And the operator runs `git checkout dev` in the target repository
When the next poll runs
Then the HEAD change is detected
And a reconciliation is scheduled

### Requirement: atomic index generation activation

The platform MUST build a new dense index generation as a sibling
file with a temporary suffix, validate the profile hash, dimension,
expected vector count and a sample query, and only then atomically
rename it into place. If validation fails the previous generation
MUST remain active and the runtime MUST remain in the refreshing
state.

#### Scenario: refresh failure leaves prior generation active (verifies: atomic index generation activation)

Given an active dense generation g
And a refresh that fails to validate its candidate generation g'
When the refresh terminates
Then generation g remains active
And readiness remains false
And the persisted snapshot is not advanced

### Requirement: project lock and refresh identity

The platform MUST NOT run more than one reconciliation or index
mutation for a project at a time. The platform MUST guard mutations
with a project-scoped lock and a refresh job identity. Requests
arriving while a refresh is in progress MUST receive a structured
not-ready or refreshing result and MUST NOT receive the previous
branch evidence.

#### Scenario: concurrent refresh fails closed (verifies: project lock and refresh identity)

Given a refresh for project P is in progress
When a retrieval request for project P arrives
Then the request receives a not-ready or refreshing result
And no previous branch evidence is returned

### Requirement: working-tree dirty detection

The reconciliation loop MUST detect a dirty working tree (HEAD
unchanged, working-tree changed) and MUST treat the resulting project
version as changed, triggering a full reconciliation and atomic
index generation swap.

#### Scenario: dirty working tree schedules a refresh (verifies: working-tree dirty detection)

Given HEAD is unchanged since the last persisted snapshot
And the working-tree fingerprint differs from the persisted one
When the version monitor polls
Then the reconciliation loop detects the dirty tree
And a full reconciliation is scheduled
And the new dense generation is activated atomically only if
reconciliation succeeds

### Requirement: Stable-tree retry
Failed refreshes SHALL retry without another edit, including explicit refreshes of unchanged content; only verified content identities may be published.

#### Scenario: Clean external repository
- **WHEN** the user starts the platform in a clean external repository
- **THEN** the runtime follows this contract without development-harness prerequisites

### Requirement: Monitor published bootstrap identity
A successful refresh MAY return its published project identity to the version monitor. The monitor SHALL use that identity as its baseline and SHALL still detect later user edits.

#### Scenario: Bootstrap persists effective settings
- **GIVEN** bootstrap writes settings and publishes the resulting identity
- **WHEN** the next monitor poll observes that identity
- **THEN** it does not invalidate readiness with a redundant refresh
