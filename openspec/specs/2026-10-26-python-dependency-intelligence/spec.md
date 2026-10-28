# Python dependency intelligence Specification

## Purpose

Provide static, offline dependency and public API evidence for Python inputs.

## Requirements

### Requirement: Static Python dependency intelligence
The platform SHALL ingest pyproject.toml project dependencies, optional dependency groups, build-system requirements, requirements text files, and wheel METADATA as structured Dependency records with normalized names, declared version constraints, extras, environment markers and source evidence. It SHALL distinguish declared constraints from installed/resolved versions and SHALL report unsupported or dynamic declarations as partial analysis. It SHALL NOT execute setup scripts, import target libraries, install dependencies, or fetch URLs during ingestion.

#### Scenario: Conditional optional dependency
- **GIVEN** a pyproject optional group containing a version constraint and environment marker
- **WHEN** ingested
- **THEN** the dependency is searchable and retains its optional scope and unevaluated marker

### Requirement: Python library APIs
The platform SHALL statically inspect Python source and wheel Python members for modules, public classes, functions, signatures, docstrings and imports. Wheel analysis SHALL be bounded and never extract archive members onto the filesystem. Syntax errors SHALL be explicit adapter failures.

#### Scenario: Untrusted wheel
- **GIVEN** a wheel with Python code and dist-info metadata
- **WHEN** ingested
- **THEN** dependency and API evidence is indexed without importing the package

### Requirement: Pipeline integration
Repository and inbox ingestion SHALL route Python inputs to the appropriate adapters and expose their chunks through normal project search. Unknown license approval and unresolved dependency closure SHALL remain explicit.

#### Scenario: Incremental reuse
- **GIVEN** an unchanged Python source after a successful ingestion
- **WHEN** ingested again
- **THEN** the existing content-addressed pipeline reuses its records

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
