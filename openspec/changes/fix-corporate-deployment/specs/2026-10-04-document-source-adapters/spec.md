## ADDED Requirements

### Requirement: private source-stage failure reporting and encoding review
The platform MUST make per-source failures from the last attempted resumable source pass available to local operators without including source content or raw exception messages. The web administration form MUST support reviewing and saving encoding rules without editing JSON.

#### Scenario: strict index rejects a legacy source
- **WHEN** a selected source cannot be decoded under the configured encoding rules
- **THEN** the private report identifies the source and failing stage
- **AND** strict readiness continues to require a complete generation

### Requirement: Automatic Windows text decoding
The text, Java, Markdown, and HTML adapters SHALL attempt supported Windows
code pages automatically after UTF-8 decoding fails and when the original
encoding has neither been declared nor explicitly configured. Selection SHALL
use deterministic bounded text evidence and strict decoding. The platform
SHALL record automatic decoding provenance and preserve source bytes.

#### Scenario: A project contains Windows-1251 SQL files
- **WHEN** an operator indexes a Windows-1251 SQL file with recognizable Cyrillic text
- **AND** no encoding override has been configured
- **THEN** indexing SHALL use the decoded text automatically and make the source searchable.

### Requirement: Opt-in local index with source failures

Operators SHALL be able to allow isolated source failures during resumable local
indexing. Publication SHALL validate durable coverage and candidate artifacts.
Configuration, cancellation, model and integrity failures SHALL block publication.

#### Scenario: A minority of sources cannot be decoded

- **WHEN** the operator requests local indexing with skipped sources allowed
- **AND** otherwise valid sources finish parsing and embedding
- **THEN** the local index SHALL become searchable with a visible skipped-source count
- **AND** Git export SHALL require a published generation without skipped sources.
