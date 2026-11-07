## ADDED Requirements

### Requirement: Project-user container cache writers
For a POSIX target owned by a non-root user, the application image SHALL automatically repair root-owned private project-cache entries at startup and execute application writers as the target UID/GID. New cache files across indexing, administrative actions and restarts SHALL be owned by that user. Settings, indexes, model access and private internal credentials SHALL be preserved. Source-tree ownership and external link targets SHALL not be recursively changed. Host CLI behavior SHALL be unchanged and operator UID/GID variables SHALL not be mandatory.

#### Scenario: Existing cache and new runtime writes
- **GIVEN** a user-owned target with root-owned cache files and internal model credentials
- **WHEN** the updated container starts and subsequently restarts or indexes
- **THEN** existing state remains usable, new cache files belong to the project user and the user can remove the cache without root privileges
