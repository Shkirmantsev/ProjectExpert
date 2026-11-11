# Managed fast workspace

## ADDED Requirements

### Requirement: Isolated local workspace

Explicit volume deployments SHALL use project-and-engine-specific named source/runtime volumes, a synchronous host canonical bind and the existing model volume. Bind SHALL remain compatible. Auto SHALL select bind until platform acceptance has been demonstrated. Native helper binaries SHALL ship with integrity records and require no host Python or Go installation.

#### Scenario: New volume installation

- **WHEN** an operator starts a clean deployment with PI_WORKSPACE_MODE=volume
- **THEN** the launcher validates a local Linux Docker engine and canonical mount, imports source before application startup, and supervises incremental synchronization without changing inference selection.

### Requirement: Safe committed imports

The synchronizer SHALL exclude canonical, runtime, VCS stores, credentials and generated content; refuse unsafe paths and links; transfer only changed bytes; reconcile deletes only from complete scans; and preserve committed authority or fail closed after interruption. Volume metadata SHALL retain the applied manifest and host VCS identity. Import application and complete index construction/publication SHALL share a cross-process lease.

#### Scenario: Import overlaps indexing

- **WHEN** a source import overlaps index construction or publication
- **THEN** mutations wait for the index lease, or indexing waits for committed recovery, and no partially transferred generation is published.

#### Scenario: Crash or unsafe archive

- **WHEN** transfer is corrupt, paths escape the workspace or application is interrupted
- **THEN** unverified bytes never become an acknowledged generation, and unfinished mutation blocks publication until reconciled.

### Requirement: Durable canonical knowledge

Canonical knowledge SHALL remain the original host directory. Wiki revision and approval behavior SHALL remain unchanged. Source synchronization SHALL never overwrite it.

#### Scenario: Canonical write succeeds

- **WHEN** an existing approved canonical write succeeds
- **THEN** its content is immediately present in the original host repository.

### Requirement: Compatible recoverable checkpoints

Checkpoints SHALL coordinate publication/writers, use SQLite online backup, include a complete compatible derived artifact set and checksummed generation/schema/profile metadata, exclude private credentials and model binaries, and publish only verified completed snapshots. Host export SHALL verify before atomic completion. Restore SHALL be explicit into an inactive volume and preserve the previous volume. Retention SHALL preserve at least one good snapshot.

#### Scenario: Backup interrupted or corrupted

- **WHEN** checkpoint/export is interrupted or a checksum is invalid
- **THEN** it is not selectable as a valid backup and the current runtime remains untouched.

### Requirement: Truthful status and acceptance

Status SHALL distinguish source generation, active index generation, pending work, last sync/backup and failures. Windows runtime, GPU, reboot registration and performance claims SHALL require observed platform evidence. Unverified hosts SHALL remain conditional.

#### Scenario: Platform unavailable

- **WHEN** a target platform or GPU cannot be exercised
- **THEN** its acceptance is recorded as NOT TESTED and auto promotion remains disabled.
