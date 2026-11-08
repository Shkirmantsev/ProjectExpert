## ADDED Requirements

### Requirement: Skills extension discovery

The bundled MCP endpoint MUST advertise io.modelcontextprotocol/skills and the
resources capability when the bundled skill catalog is available, through
server/discover and legacy initialize. It MUST implement skills/list and
skills/get, preserving legacy resource URIs. Skill discovery MUST be independent
of indexing readiness and chat model availability.

#### Scenario: a new project discovers its server workflow

- **WHEN** an agent connects to ProjectExpert serving a new target repository
- **THEN** skills/list returns project-intelligence with its complete frontmatter
- **AND** skills/get for skill://project-intelligence/SKILL.md returns the same entry
- **AND** all files are readable with resources/read without a local skill install.

### Requirement: verifiable complete skill manifests

Every entry MUST enumerate SKILL.md and all supporting files exactly once with
raw byte sizes and sha256-prefixed digests. Frontmatter MUST retain nested
metadata. Standard resources MUST preserve raw bytes, including binary assets.
List/get responses MUST carry complete result type and cache hints. Invalid
URIs and cursors MUST return -32602 without accessing files outside the bundle.

#### Scenario: clients verify the complete package

- **WHEN** a client reads each resource in a skills/get manifest
- **THEN** bytes match the advertised SHA-256 and size
- **AND** nested references and binary assets are included.

#### Scenario: unsafe resources are refused

- **WHEN** a URI uses traversal, encoded escapes, an unknown file, or a symlink
- **THEN** the server refuses the request with -32602 and exposes no outside content.

### Requirement: progressive and compatible delivery

Listing MUST return metadata and manifests without embedding file contents.
Servers MUST provide a skill URI hint in server instructions. Existing clients
MUST still be able to list/read ordinary resources. Reading a resource MUST NOT
execute scripts, change client permissions, or imply activation of a skill.

#### Scenario: a client lacks native Skills support

- **WHEN** a client uses resources/list and resources/read
- **THEN** it can retrieve the bundled skill as ordinary resource content
- **AND** its own policy determines whether and how to use that content.
