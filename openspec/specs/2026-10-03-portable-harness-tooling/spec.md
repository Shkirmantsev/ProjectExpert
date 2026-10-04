# Portable Harness Tooling Specification

## Purpose

Define reusable downstream improvements to portable state, skill routing and
optional documentation tooling without depending on application business logic.

## Requirements

### Requirement: platform-aware atomic state durability

Context-pack, lesson-candidate and session-state writers SHALL atomically publish
complete files and flush file contents before replacement. They SHALL flush the
parent directory on POSIX and SHALL avoid POSIX directory handles on Windows.

#### Scenario: Windows publishes a state file

- **WHEN** a state writer replaces a file on Windows
- **THEN** readers receive the complete new contents
- **AND** publication does not attempt to open a POSIX directory handle.

### Requirement: literal environment replacements

Environment updates SHALL preserve replacement values literally, including
backslashes and Unicode text, using UTF-8 while retaining unrelated variables.

#### Scenario: Windows path replaces an existing value

- **WHEN** an existing environment variable is updated to a Windows-style path
- **THEN** backslashes and digit sequences are preserved without regex expansion
- **AND** unrelated variables remain unchanged.

### Requirement: unloaded routing fallback metadata

Uncertain deterministic skill plans SHALL expose sorted name/description metadata
for unselected catalog skills without loading their bodies. Confident plans SHALL
return an empty metadata index. Semantic selection SHALL respect activation caps,
dependencies, project scope and existing authorization.

#### Scenario: phrase matching misses an actionable task

- **WHEN** the deterministic router returns an uncertain plan
- **THEN** `catalog_index` contains only unselected skill names and descriptions
- **AND** the calling agent can select by meaning before asking about actual ambiguity.

### Requirement: optional minimal implementation skill

The Ponytail skill SHALL be catalog-only, activate on explicit selection or
simplicity-specific routing signals, and preserve acceptance criteria, safety and
verification without imposing a persistent persona.

#### Scenario: explicit Ponytail request

- **WHEN** a coding task explicitly selects Ponytail
- **THEN** the router selects the catalog skill within the normal activation cap
- **AND** core skill synchronization does not expose it directly.

### Requirement: opt-in authenticated documentation MCP

Context7 SHALL be disabled by default and SHALL use the existing HTTP client
transport when enabled. Claude, OpenCode and Codex configurations SHALL preserve
optional bearer authentication. Generated credential-bearing files SHALL be
published atomically with private POSIX permissions. URLs SHALL use HTTPS and
SHALL NOT contain embedded credentials. Core checks SHALL NOT require service
access or npm installation.

#### Scenario: enabled Context7 with an API key

- **WHEN** client configs are generated with Context7 enabled and a configured key
- **THEN** all three clients receive the endpoint and bearer authentication
- **AND** generated configs have private POSIX permissions.

#### Scenario: Context7 is not selected

- **WHEN** configuration does not enable Context7
- **THEN** no Context7 server is generated and existing integrations remain available.

### Requirement: platform executable resolution

The harness command launcher SHALL resolve available platform executable wrappers
before invoking subprocesses while preserving arguments and check behavior.

#### Scenario: an executable has a platform suffix

- **WHEN** command lookup resolves an executable wrapper
- **THEN** the subprocess invokes the resolved path with the original arguments.

### Requirement: current specifications participate in strict validation

Current specifications SHALL live at `openspec/specs/YYYY-MM-DD-domain-capability/spec.md`.
The harness SHALL reject loose Markdown specifications rather than silently
allowing the CLI to omit them. Accepted dated capability identifiers SHALL remain stable on subsequent
updates. Migration from undated identifiers SHALL preserve the original Git
acceptance date and update live links and active delta paths.

#### Scenario: a loose current specification exists

- **WHEN** the harness OpenSpec gate finds Markdown directly under `openspec/specs/`
- **THEN** it fails and identifies the expected capability-directory layout.

### Requirement: optional host adapters do not prevent portable imports

The optional Hermes ACL setup module SHALL load without POSIX-only imports on
Windows. Invoking its host setup there SHALL report the POSIX host requirement
before attempting account or ACL changes. Ancestor traversal SHALL terminate at
the native filesystem root.

#### Scenario: Windows loads the optional host adapter

- **WHEN** portable tooling imports the Hermes host setup module on Windows
- **THEN** module loading does not require `pwd`
- **AND** invoking setup reports that a POSIX ACL host is required.

### Requirement: Linux and Windows core verification

The portable harness core SHALL support Linux and Windows on Python 3.11 and
3.13. CI SHALL run unit suites on both systems and full core verification on
Linux and Windows with the declared MCP dependencies installed. Full Windows
verification SHALL include the real stdio MCP initialize/request exchange,
strict OpenSpec validation, Wiki validation, state verification and the artifact
manifest. Optional host-specific adapters SHALL NOT be prerequisites for the
portable core.

#### Scenario: Windows validates the complete portable core

- **GIVEN** Python, Node, OpenSpec and declared test/MCP dependencies are installed
- **WHEN** CI runs the Windows full core gate on Python 3.11 or 3.13
- **THEN** the gate passes including the real stdio MCP handshake
- **AND** no Docker or POSIX host setup is required.
