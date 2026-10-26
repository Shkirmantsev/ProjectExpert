## ADDED Requirements

### Requirement: Monitor published bootstrap identity
A successful refresh MAY return its published project identity to the version monitor. The monitor SHALL use that identity as its baseline and SHALL still detect later user edits.

#### Scenario: Bootstrap persists effective settings
- **GIVEN** bootstrap writes settings and publishes the resulting identity
- **WHEN** the next monitor poll observes that identity
- **THEN** it does not invalidate readiness with a redundant refresh
