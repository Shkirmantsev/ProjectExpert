# Specification delta

Proposed; not adopted current behavior.

## ADDED Requirements

### Requirement: Python resolved research inputs
Python research SHALL supplement existing static ingestion with supported uv.lock and poetry.lock records and explicitly selected installed distribution metadata. It SHALL retain environment markers, extras, groups, editable/local origins and unresolved requirements. It SHALL NOT import target packages or mutate a target environment. Unknown lock versions SHALL be partial or unsupported, never silently treated as complete.

#### Scenario: Environment-specific Python graph
- **GIVEN** a supported lock with platform markers and extras
- **WHEN** research selects an environment and extra set
- **THEN** included and excluded conditions are distinguishable and the environment is recorded

#### Scenario: Installed metadata disagreement
- **GIVEN** a selected environment with a different version from the lock
- **WHEN** the graph is requested
- **THEN** both observations and the mismatch are reported without overwriting either

#### Scenario: Python archive and bytecode fallback
- **GIVEN** a wheel or bounded source archive, or a supported pyc-only artifact
- **WHEN** library inspection is requested
- **THEN** source and stubs are preferred; supported bytecode fallback is labelled disassembly or decompiled approximation; unsupported CPython versions and native extensions remain partial
