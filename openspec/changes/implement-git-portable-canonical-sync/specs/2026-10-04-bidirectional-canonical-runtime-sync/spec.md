## ADDED Requirements

### Requirement: Production portable snapshots
The system SHALL stage deterministic, bounded textual snapshots of the published
resumable generation, exclude restricted source derivatives, and publish only
through the trusted materialisation boundary. Publication SHALL preserve Wiki,
v1 data and the previous valid root on failure and SHALL NOT run Git mutations.

#### Scenario: Cross-machine reuse
- **WHEN** a committed v2 snapshot is checked out in a different repository path
- **THEN** matching source bytes, policy and portable pipeline identity seed the
  actual resumable cache before parsing and only current source membership serves.

#### Scenario: Exact optional vectors
- **WHEN** approved textual vectors match the active embedding profile
- **THEN** float32 bytes roundtrip and unchanged document embeddings are reused.

#### Scenario: Invalid snapshot
- **WHEN** a declared file, checksum, record, membership or path is invalid
- **THEN** verification fails before source import or query publication.

#### Scenario: Repeat export
- **WHEN** the published eligible generation is unchanged
- **THEN** export produces identical bytes, no rewritten canonical files and no
  generated source admissions.
