## ADDED Requirements

### Requirement: Stable Wiki file access modes
On POSIX, new atomically written Wiki pages SHALL have mode 0644. Atomic replacement of an existing Wiki page or navigation index SHALL preserve its existing ordinary access bits, including intentionally restrictive permissions. Temporary files SHALL remain private while content is being written. Windows behavior SHALL remain compatible.

#### Scenario: New page
- **WHEN** an MCP caller creates a valid Wiki page
- **THEN** its POSIX mode is 0644 and its owner is the application writer

#### Scenario: Existing access policy
- **GIVEN** an existing Wiki page with mode 0640 or 0600
- **WHEN** an MCP caller updates it
- **THEN** its mode is retained and the updated content is stored atomically

#### Scenario: Reserved navigation index
- **GIVEN** an existing Wiki index with mode 0644
- **WHEN** page creation updates navigation
- **THEN** the index remains 0644
