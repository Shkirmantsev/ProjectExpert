## ADDED Requirements

### Requirement: Short verified Windows asset cache

The Windows launcher SHALL extract primary offline assets into a short user-local staging directory, verify the complete pinned manifest and preserve the previous pack on explicit repair.

#### Scenario: Deep project checkout

- **GIVEN** a deployment kit nested in a long Windows project path
- **WHEN** the launcher verifies a primary offline asset pack
- **THEN** extraction uses the short user directory and failed verification preserves the existing pack
