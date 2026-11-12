## ADDED Requirements

### Requirement: Durable validated vector batches
When batching is explicitly enabled the semantic service MUST group compatible
cache misses, validate every returned vector and persist each complete batch
atomically before reporting its completed count. Profile identity, revision,
normalization and retrieval hash MUST all match for reuse. Multimodal requests
MUST preserve per-input projection ordering and source identity.

#### Scenario: later batch fails
- **GIVEN** a committed first vector batch and a failed second model request
- **WHEN** the service restarts on the same profile and retrieval hashes
- **THEN** first-batch vectors are reused
- **AND** only missing vectors are embedded

#### Scenario: wrong vector blocks batch
- **GIVEN** a model reply containing a non-finite or wrong-dimensional vector
- **WHEN** the service validates the batch
- **THEN** no vector from that invalid batch is persisted
- **AND** the candidate is not activated
