## ADDED Requirements

### Requirement: Stable-tree retry
Failed refreshes SHALL retry without another edit, including explicit refreshes of unchanged content; only verified content identities may be published.

#### Scenario: Clean external repository
- **WHEN** the user starts the platform in a clean external repository
- **THEN** the runtime follows this contract without development-harness prerequisites
