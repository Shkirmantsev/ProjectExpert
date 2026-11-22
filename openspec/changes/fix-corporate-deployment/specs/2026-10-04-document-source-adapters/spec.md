## ADDED Requirements

### Requirement: private source-stage failure reporting and encoding review
The platform MUST make per-source failures from the last attempted resumable source pass available to local operators without including source content or raw exception messages. The web administration form MUST support reviewing and saving encoding rules without editing JSON.

#### Scenario: strict index rejects a legacy source
- **WHEN** a selected source cannot be decoded under the configured encoding rules
- **THEN** the private report identifies the source and failing stage
- **AND** strict readiness continues to require a complete generation

### Requirement: Opt-in local index with source failures

Operators SHALL be able to allow isolated source failures during resumable local
indexing. Publication SHALL validate durable coverage and candidate artifacts.
Configuration, cancellation, model and integrity failures SHALL block publication.

#### Scenario: A minority of sources cannot be decoded

- **WHEN** the operator requests local indexing with skipped sources allowed
- **AND** otherwise valid sources finish parsing and embedding
- **THEN** the local index SHALL become searchable with a visible skipped-source count
- **AND** Git export SHALL require a published generation without skipped sources.
