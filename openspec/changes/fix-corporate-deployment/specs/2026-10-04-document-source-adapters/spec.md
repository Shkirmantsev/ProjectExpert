## ADDED Requirements

### Requirement: private source-stage failure reporting and encoding review
The platform MUST make per-source failures from the last attempted resumable source pass available to local operators without including source content or raw exception messages. The web administration form MUST support reviewing and saving encoding rules without editing JSON.

#### Scenario: strict index rejects a legacy source
- **WHEN** a selected source cannot be decoded under the configured encoding rules
- **THEN** the private report identifies the source and failing stage
- **AND** strict readiness continues to require a complete generation
