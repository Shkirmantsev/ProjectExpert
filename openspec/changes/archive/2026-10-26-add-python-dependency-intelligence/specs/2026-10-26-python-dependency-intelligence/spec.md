## ADDED Requirements
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
