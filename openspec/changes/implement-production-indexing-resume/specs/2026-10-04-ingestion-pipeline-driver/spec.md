## ADDED Requirements

### Requirement: Atomic resumable source completion
The resumable engine MUST durably commit a source summary, canonical payloads,
ownership and candidate membership together only after successful ingestion.
Failed or cancelled sources MUST NOT expose partial canonical output.

#### Scenario: restart reuses completed sources
- **GIVEN** an interrupted candidate with committed compatible source outputs
- **WHEN** indexing restarts on the same inventory and pipeline
- **THEN** completed sources are reused without parsing
- **AND** incomplete sources are retried without duplicate ownership

### Requirement: Candidate generation isolation
The engine MUST select exact source versions for each candidate and preserve
previous generation membership while a candidate is incomplete or fails.
Only one builder may own a cache; stale leases alone MUST NOT allow takeover.

#### Scenario: changed or removed source
- **GIVEN** an older generation containing two sources
- **WHEN** one source changes and the other is removed
- **THEN** the new candidate contains only the changed source's new output
- **AND** the older generation's payloads remain intact

### Requirement: Observable durable progress
The engine MUST record stage totals and committed completion counts, separate
failures and degradation, and never equate liveness with retrieval readiness.

#### Scenario: failed source prevents complete publication
- **GIVEN** a source whose ingestion permanently fails
- **WHEN** complete indexing is required
- **THEN** candidate construction fails with an actionable diagnostic
- **AND** the last published runtime is preserved
