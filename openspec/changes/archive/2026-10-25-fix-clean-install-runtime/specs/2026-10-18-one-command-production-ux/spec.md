## ADDED Requirements

### Requirement: Published runtime status
Status SHALL report the published content fingerprint and embedding revision.
Semantic chunk counts SHALL be distinct from canonical cache counts.

#### Scenario: Semantic runtime with empty canonical cache
- **WHEN** a clean source repository reaches retrieval readiness
- **THEN** status reports its active semantic chunks even if no canonical shards exist

### Requirement: Safe model cache maintenance
Native model loading and model pull/verify SHALL use the same hub cache layout.
The model command group SHALL support pruning incomplete downloads older than
24 hours only while holding the downloader lock. Complete and active downloads
SHALL be retained.

#### Scenario: Abandoned download
- **WHEN** the operator runs models prune-incomplete
- **THEN** old unlocked partial blobs are removed and reclaimed bytes are reported
- **AND** recent, locked and complete files remain
