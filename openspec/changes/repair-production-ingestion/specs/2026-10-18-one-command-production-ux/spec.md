## ADDED Requirements

### Requirement: truthful production recovery
Launchers MUST distinguish service URL from index readiness, signal cooperative workspace stop before waiting for operation locks, and preserve unverified asset rejection with structured diagnostics.

#### Scenario: active importer
- **WHEN** workspace stop reaches its deadline while an importer owns its operation lock
- **THEN** it reports STOP_PENDING instead of killing the publisher or claiming safe shutdown

#### Scenario: asset failure
- **WHEN** an offline pack fails validation
- **THEN** diagnostics identify the failed verification category and exact release pins without exposing source contents
- **AND** no unverified native binary is executed
