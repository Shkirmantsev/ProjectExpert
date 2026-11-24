## ADDED Requirements

### Requirement: Bounded document work for compatible endpoints

The semantic index service SHALL make multiple requests' worth of text available to an evidence-gated dispatcher in one bounded window while retaining ordered association and complete chunk projection.

#### Scenario: Multiple approved endpoints

- **GIVEN** parity-validated endpoints with measured combined throughput and sufficient uncached text chunks
- **WHEN** semantic indexing runs with batching enabled
- **THEN** multiple endpoints receive document work and validated results remain associated with their original chunks
