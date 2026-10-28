# dependency-research Specification

## Purpose
Give the platform a language-neutral way to answer questions about the
libraries a project uses. The capability covers the bounded dependency
graph, the controlled acquisition of an exact artifact and the bounded,
labelled read of library code, so a caller always receives evidence and
a truthful status instead of a guess.

## Requirements

### Requirement: Evidence-backed dependency graphs
The platform SHALL provide bounded dependency graph research for Maven/Gradle, Python and Node projects. Results SHALL distinguish declarations, lock resolution and observed installation, preserve scopes, markers, workspace relationships and source evidence, and report unresolved edges, unsupported formats and truncation. Completeness SHALL be relative to the selected environment and evidence; declared constraints SHALL NOT become exact versions without evidence.

#### Scenario: Transitive explanation
- **GIVEN** a supported lock with root to A to B and exact versions
- **WHEN** the caller asks why B is used
- **THEN** the response gives both edges, versions, scopes and lock locations

#### Scenario: Cycle and budget
- **GIVEN** a cyclic graph larger than the configured node/depth budget
- **WHEN** a bounded tree is requested
- **THEN** traversal terminates, returns stable identifiers and continuation or truncation details

#### Scenario: Missing lock
- **GIVEN** only a manifest with version ranges
- **WHEN** the caller requests resolved dependencies
- **THEN** the response labels declared-only partial evidence and identifies missing resolution inputs

### Requirement: Controlled artifact acquisition
Default research SHALL be offline. Explicit acquisition SHALL use approved sources and policy, exact package identity, integrity verification, time and size limits, and content-addressed reuse. It SHALL NOT execute package installation hooks or target build scripts. Restricted sources SHALL NOT be copied into durable Wiki pages or sent externally without applicable policy.

#### Scenario: Offline cache miss
- **GIVEN** a requested artifact is unavailable locally
- **WHEN** offline research runs
- **THEN** it returns unavailable with an actionable acquisition request and makes no network calls

#### Scenario: Integrity mismatch
- **GIVEN** an explicitly authorized artifact download with expected integrity
- **WHEN** downloaded bytes disagree with expected integrity
- **THEN** the artifact is rejected and not indexed

#### Scenario: Hostile archive
- **GIVEN** an archive containing traversal, symlinks or excessive expanded bytes
- **WHEN** inspection is requested
- **THEN** it fails safely without writes outside the designated cache or package code execution

### Requirement: Bounded code evidence
Research SHALL return searchable symbols and bounded code excerpts with package/version, artifact hash, member path, location and representation kind. Original source SHALL be preferred over recovered representations. Reconstructed output SHALL be labelled and linked to the exact binary and tool version; unsupported binaries SHALL return explicit partial analysis.

#### Scenario: Source preference
- **GIVEN** matching original source and binary artifacts
- **WHEN** an API body is requested
- **THEN** original source is returned with evidence and no unnecessary decompilation

#### Scenario: No recoverable body
- **GIVEN** an unsupported native binary with metadata
- **WHEN** method implementation is requested
- **THEN** metadata is returned as partial, with the body unavailable and a precise reason
