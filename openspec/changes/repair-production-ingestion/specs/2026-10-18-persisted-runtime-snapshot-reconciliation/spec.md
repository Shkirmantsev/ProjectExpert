## ADDED Requirements

### Requirement: failed candidate suspension
The monitor MUST suspend identical typed permanent or configuration failures across restart and permit explicit retry or changed input. Typed transient failures MUST use bounded delayed retries. Last-good published state MUST be retained.

#### Scenario: repeated bad encoding
- **WHEN** complete ingestion fails with unchanged source errors
- **THEN** subsequent automatic polling does not schedule the same failure repeatedly
- **AND** an explicit Reindex permits one further attempt
