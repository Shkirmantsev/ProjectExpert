# Specification delta

Proposed; not adopted current behavior.

## ADDED Requirements

### Requirement: Help-first deployment commands
The exported kit SHALL show available public Make targets with a one-line description when invoked with no target or with help. Help SHALL succeed without Docker, Python, deployment.env, model downloads or service mutation. Explicit platform-start and start scripts SHALL retain startup behavior.

#### Scenario: Bare make is read-only
- **GIVEN** an exported kit on a machine without Docker
- **WHEN** the user runs make or make help
- **THEN** both exit zero with the same documented command list and perform no service or filesystem mutation

#### Scenario: Command coverage
- **GIVEN** the public targets in the exported Makefile
- **WHEN** help is requested
- **THEN** every public target is described, including start, stop, status, logs, pull, restart, model and maintenance operations

### Requirement: Consistent deployment service identity
Startup and helper operations SHALL preserve the active service topology and existing data. Valid active embeddings and model-setup services SHALL NOT be reported as orphans because a helper used an incomplete configuration. Genuine unrelated-service warnings SHALL remain visible; no automatic orphan deletion is permitted.

#### Scenario: Repeated start
- **GIVEN** an existing healthy CPU deployment with completed model setup
- **WHEN** startup runs twice
- **THEN** both runs reach readiness without false orphan warnings or deleting sidecars, model assets or indexed data

#### Scenario: Backend transition
- **GIVEN** an existing sidecar deployment
- **WHEN** a supported backend change or CPU fallback occurs
- **THEN** helpers and final startup use consistent project identity and preserve data; errors remain visible

### Requirement: Effective startup address
After readiness, startup SHALL report the effective configured browser URL. Failure SHALL return nonzero and SHALL NOT print Ready.

#### Scenario: Port from configuration
- **GIVEN** deployment.env configures a nondefault port and the shell does not override it
- **WHEN** explicit startup succeeds
- **THEN** the printed URL uses that port

#### Scenario: Readiness fails
- **GIVEN** a failing production health check
- **WHEN** startup reaches its timeout
- **THEN** the command fails with diagnostics and does not report readiness
