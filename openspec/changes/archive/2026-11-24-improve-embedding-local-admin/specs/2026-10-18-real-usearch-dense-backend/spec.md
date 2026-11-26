## ADDED Requirements

### Requirement: Efficient candidate creation and restore

The runtime SHALL group dense index updates and reuse a fully validated saved generation without reinserting its vectors.

#### Scenario: Warm restore

- **GIVEN** a saved ANN generation and complete compatible SQLite vectors
- **WHEN** the runtime opens the same generation
- **THEN** it reports those vectors as reused and performs no inference or index mutations
