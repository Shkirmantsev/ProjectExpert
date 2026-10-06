# skill-distribution-plane Specification delta

Covers architecture section §38 (Skill Distribution Plane)
and §37 (Versioned Agent Skill Distributed with the MCP
Server). The skill distribution plane is the URL namespace
the MCP server exposes for clients that need runtime skill
discovery. The plane is an MCP resource surface; it does
NOT introduce a backend database — the canonical skill
content lives in `distribution/skills/`, the distribution
manifest is computed from the registry state and the
versioned skill URI is served from the canonical skill
files on disk.

The MCP server exposes the §38 custom resources:

```text
project-intelligence://distribution/manifest
project-intelligence://skills/index
project-intelligence://skills/<name>/<version>/SKILL.md
project-intelligence://skills/<name>/<version>/references/...
project-intelligence://skills/<name>/<version>/assets/...
```

The URI namespace is stable and versioned. Vendors that
require install-time snapshots consume the same content
through the build / install-time path documented in §38.0.2
— the plane and the snapshot path share a single
canonical source so the two paths cannot disagree.

## ADDED Requirements

### Requirement: skill distribution plane URI namespace

The MCP server MUST expose the §38 skill distribution
plane URI namespace as MCP resources. The URI namespace
MUST be stable and versioned; the MCP server MUST reject
attempts to register a conflicting URI namespace and MUST
refuse to serve a URI whose path does not match the
documented schema.

#### Scenario: plane URIs match the §38 schema

Given the MCP server is started
When a client enumerates the registered MCP resources
Then the resource URIs include
`project-intelligence://distribution/manifest`,
`project-intelligence://skills/index`,
`project-intelligence://skills/<name>/<version>/SKILL.md`
for every installed skill
And the URIs are stable across restarts.

#### Scenario: server rejects conflicting URI namespace

Given an external component attempts to register a URI
that collides with the documented namespace
When the MCP server boots
Then the MCP server raises a documented
`SkillPlaneConflictError`
And the offending URI is NOT registered.

### Requirement: distribution manifest schema

The MCP server MUST expose
`project-intelligence://distribution/manifest` as a
machine-readable JSON manifest. The manifest MUST carry
the documented fields:

- `platformVersion` (str) — semver of the running
  platform;
- `mcpApiVersion` (str) — semver of the MCP API the
  server speaks;
- `knowledgeSchemaVersion` (str) — semver of the
  canonical knowledge schema;
- `distributionSchemaVersion` (str) — semver of the
  distribution manifest schema;
- `skill` (object) — `name`, `version`, `sha256`,
  `mcpApiRange` (semver range);
- `okf` (object) — `supported` (sequence of OKF
  versions);
- `agentAdapters` (object) — `codex`,
  `claude-code`, `opencode` semver versions of the
  built-in adapters.

#### Scenario: manifest carries the documented fields

Given the MCP server is started with the Phase 5
`CapabilityDiscoveryPort` registered and the canonical
Agent Skill installed
When a client reads
`project-intelligence://distribution/manifest`
Then the returned JSON contains every documented field
And `skill.sha256` matches the SHA-256 of the canonical
`SKILL.md` content.

#### Scenario: manifest reports optional capabilities

Given a deployment with the stub `LocalLLMPort` (`is_
available() == False`)
When a client reads the manifest
Then the manifest reports `features.localLlm == False`
through the documented fields
And the optional capability surfaces remain absent
rather than emitted as null.

### Requirement: skill index enumerates installed skills

The MCP server MUST expose
`project-intelligence://skills/index` as a JSON index
that lists every installed skill with its name, version,
the SHA-256 content hash and the `mcpApiRange` semver
range. The index MUST be sorted by `(name, version)` so
two consecutive reads return the same byte sequence.

#### Scenario: skill index is sorted

Given two skills `project-intelligence` and
`agent-bridge` are installed
When a client reads `project-intelligence://skills/
index`
Then the index lists both skills
And the order is deterministic across reads.

### Requirement: versioned skill URI

The MCP server MUST expose
`project-intelligence://skills/<name>/<version>/SKILL.md`
(and the `references/...`, `scripts/...`, `assets/...`
paths) as MCP resources. The `<version>` MUST match the
skill's documented semver; the MCP server MUST refuse
requests for `<version>` values that do not exist.

#### Scenario: versioned SKILL.md matches the canonical file

Given the canonical Agent Skill is installed
When a client reads
`project-intelligence://skills/project-intelligence/
<version>/SKILL.md`
Then the returned content is byte-identical to the
canonical `distribution/skills/project-intelligence/
SKILL.md` content
And the SHA-256 of the served content matches the
manifest's `skill.sha256`.

#### Scenario: missing skill version is rejected

Given the canonical Agent Skill ships at version `1.4.0`
When a client requests
`project-intelligence://skills/project-intelligence/
9.9.9/SKILL.md`
Then the MCP server returns a documented
`SkillVersionNotFoundError`.

### Requirement: snapshot vs runtime distribution parity

The MCP server MUST ensure the runtime distribution
matches the snapshot distribution. When a vendor plugin
package consumes the skill at install time, the package
MUST be regenerated whenever the canonical skill content
changes; the MCP server MUST detect a mismatch between
the served URI content and the canonical skill and MUST
emit a `SkillSnapshotStaleWarning` rather than silently
serving the snapshot.

#### Scenario: stale snapshot triggers a warning

Given a vendor plugin was packaged at version `1.4.0`
of the canonical skill and the canonical skill has since
been updated to `1.5.0`
When a client reads the snapshot's `SKILL.md`
Then the MCP server emits a
`SkillSnapshotStaleWarning`
And the served content is the canonical `1.5.0`
content, not the stale `1.4.0` snapshot.

### Requirement: integrity metadata on every distribution

The MCP server MUST carry integrity metadata on every
distribution surface (manifest, index, versioned URI).
The integrity metadata MUST include the semantic version,
the content hash, the license, the build provenance and
the compatible MCP API range.

#### Scenario: integrity metadata is present

Given any distribution resource is read
When the resource is served
Then the response carries `version`, `sha256`,
`license`, `build_provenance` and `mcp_api_range`
fields
And the values match the manifest's documented values.

### Requirement: deterministic manifest ordering

The MCP server MUST serialise the manifest with a
deterministic key ordering. Two consecutive reads of
`project-intelligence://distribution/manifest` MUST
return byte-identical JSON for a fixed platform state.

#### Scenario: repeated reads are byte-identical

Given a fixed platform state
When the manifest is read twice consecutively
Then the byte sequence of both responses is identical.

## Phase 6 task coverage

The change covers Phase 6 task 86 (skill distribution
resources: manifest, index, versioned skill URI). Task
87 (canonical Agent Skill) provides the canonical
content the plane serves; task 88 (version handshake)
provides the version-range parsing the manifest uses.

Out of scope:

- the canonical Agent Skill content — Phase 6 task 87
  (`agent-skill-canonical`);
- the version-compatibility handshake — Phase 6 task 88
  (`version-compatibility-handshake`);
- the Codex / ChatGPT plugin package — Phase 6 task 89
  (`codex-plugin-package`);
- the Claude Code plugin package — Phase 6 task 90
  (`claude-code-plugin-package`);
- the OpenCode plugin package — Phase 6 task 91
  (`opencode-plugin-package`);
- the generic agent bundle — Phase 6 task 92
  (`generic-agent-bundle`);
- the MCP server wiring of the URI namespace — Phase 6
  task 85 (`mcp-server`);
- the agent adapter contract — Phase 6 task 93
  (`agent-adapter-contract`);
- the plugin supply-chain security gate — Phase 6 task
  94 (`plugin-supply-chain-security`);
- the Wiki maintenance and archive — Phase 6 task 95
  (`phase-6-wiki-archive`);
- A2A integration — Phase 10 tasks 119-123;
- the Control Plane and Feature / Plugin Registry —
  Phase 7 tasks 96-100.