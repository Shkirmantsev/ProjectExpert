# version-compatibility-handshake Specification delta

Covers architecture section §39 (Protocol and Artifact
Version Compatibility) and §47 (Capability Discovery).
The version-compatibility handshake is the contract the
MCP server, the skill distribution plane and the plugin
packagers consume to validate that a client's declared
version range intersects the server's supported range.

The handshake tracks 9 independently evolving version
dimensions:

```text
platformVersion
mcpApiVersion
a2aAdapterVersion
knowledgeSchemaVersion
okfProfileVersion
skillVersion
pluginDistributionSchemaVersion
agentAdapterVersion
runtimeIndexSchemaVersion
```

Every dimension uses semantic versioning. Breaking
changes require a major version boundary or an explicit
compatibility adapter. The handshake MUST be
machine-checkable, MUST run without an LLM and MUST
return a typed `VersionIncompatibleError` when the
client's declared range does not intersect the server's
supported range.

## ADDED Requirements

### Requirement: handshake tracks 9 version dimensions

The platform MUST track the 9 §39 version dimensions
through a single `VersionCompatibilityPolicy` value
type. The value type MUST carry every dimension as a
semver string and MUST serialise to a deterministic
JSON.

#### Scenario: every dimension is present

Given a `VersionCompatibilityPolicy` instance is built
from the runtime registrations
When the operator serialises the policy
Then the JSON contains every documented dimension
And the values match the registered
`CapabilityDiscoveryPort.describe` output.

#### Scenario: serialised policy is deterministic

Given a fixed runtime state
When the policy is serialised twice consecutively
Then the byte sequence is identical.

### Requirement: handshake compares semver ranges

The handshake MUST compare semver ranges using a
deterministic range comparison. The comparison MUST
NOT depend on a network call to a remote model; the
comparison is a pure function of the declared range
and the supported range.

#### Scenario: intersecting ranges succeed

Given the server supports `mcpApiVersion 1.3.0`
And a client declares `mcp-api: ">=1.3.0 <2.0.0"`
When the handshake compares the ranges
Then the handshake succeeds
And the client receives the `describe_capabilities`
descriptor.

#### Scenario: disjoint ranges fail with a typed error

Given the server supports `mcpApiVersion 1.3.0`
And a client declares `mcp-api: ">=2.0.0 <3.0.0"`
When the handshake compares the ranges
Then the handshake raises a documented
`VersionIncompatibleError`
And the error carries the server's `mcpApiVersion`,
the client's declared range and the supported range.

### Requirement: handshake runs without an LLM

The handshake MUST be deterministic and MUST NOT
require a local LLM or any external LLM. The
`CapabilityDiscoveryPort` is the source of truth for
the server's capabilities.

#### Scenario: handshake works without a local LLM

Given the stub `LocalLLMPort` is registered (`is_
available() == False`)
When the handshake runs
Then the comparison completes without calling any LLM
And the descriptor is computed from the registered
port registry.

### Requirement: handshake covers all 9 dimensions

The handshake MUST validate every documented dimension
that the client declares. The validation MUST be
exhaustive across the 9 dimensions; the handshake MUST
NOT silently skip a dimension that the client omits.

#### Scenario: omitted dimension is flagged

Given a client declares `mcp-api` and `knowledge-
schema` but omits `okf-profile`
When the handshake runs
Then the handshake reports the omission
And the client is informed that an updated handshake
is recommended (without failing the connection unless
the server requires every dimension).

### Requirement: deterministic range parsing

The handshake MUST parse semver ranges with a
deterministic parser. The parser MUST accept the
documented range syntax (>, >=, <, <=, =, ^, ~, hyphen
range, semver range with multiple constraints) and MUST
reject ambiguous ranges with a documented
`VersionRangeSyntaxError`.

#### Scenario: ambiguous range is rejected

Given a client declares `mcp-api: ">=1.3.0"` with a
trailing comma (a malformed range)
When the parser parses the range
Then the parser raises
`VersionRangeSyntaxError`
And the error identifies the offending range.

### Requirement: backwards-compatible adapter support

The handshake MUST allow the server to advertise
compatibility adapters for older supported version
ranges. A newer server MAY retain a compatibility
adapter for older released skills for a bounded
support window. The handshake MUST prefer the
adapter's effective range when present.

#### Scenario: compatibility adapter widens support

Given the server supports `mcpApiVersion 1.3.0`
And the server also retains a compatibility adapter for
`mcpApiVersion 1.2.x`
When a client declares `mcp-api: ">=1.2.0 <1.3.0"`
Then the handshake succeeds through the compatibility
adapter
And the handshake response documents the effective
range that succeeded.

### Requirement: handshake result is serialisable

The handshake result MUST be a JSON-serialisable value
type. The result MUST carry the negotiated dimensions,
the rejected dimensions (if any), the compatibility
adapters consulted and the supported range for every
dimension.

#### Scenario: handshake result serialises

Given a successful handshake
When the operator serialises the result
Then the JSON contains the negotiated dimensions and
the documented fields
And two consecutive serialisations are byte-identical.

### Requirement: failure-clearly-or-upgrade contract

Per §39.0.1, the handshake MUST fail clearly when
incompatible and MUST offer upgrade instructions.
The failure MUST be a typed
`VersionIncompatibleError` whose payload includes the
server's `mcpApiVersion`, the supported range and the
client's declared range. The handshake MUST NOT silently
downgrade the negotiated version.

#### Scenario: failure includes upgrade instructions

Given a disjoint range
When the handshake fails
Then the typed error payload carries the upgrade
instructions documented in §39.0.1
And the error is rendered for the client without
requiring an LLM.

## Phase 6 task coverage

The change covers Phase 6 task 88 (version-compatibility
handshake for the 9 §39 version dimensions). Task 85
(MCP server) embeds the handshake in the session
startup; task 86 (skill distribution plane) advertises
the supported range in the manifest; tasks 89-92 (plugin
packagers) call the handshake before packaging.

Out of scope:

- the MCP server wiring — Phase 6 task 85
  (`mcp-server`);
- the skill distribution plane — Phase 6 task 86
  (`skill-distribution-plane`);
- the canonical Agent Skill — Phase 6 task 87
  (`agent-skill-canonical`);
- the Codex / ChatGPT plugin package — Phase 6 task 89
  (`codex-plugin-package`);
- the Claude Code plugin package — Phase 6 task 90
  (`claude-code-plugin-package`);
- the OpenCode plugin package — Phase 6 task 91
  (`opencode-plugin-package`);
- the generic agent bundle — Phase 6 task 92
  (`generic-agent-bundle`);
- the agent adapter contract — Phase 6 task 93
  (`agent-adapter-contract`);
- the plugin supply-chain security gate — Phase 6 task
  94 (`plugin-supply-chain-security`);
- the Wiki maintenance and archive — Phase 6 task 95
  (`phase-6-wiki-archive`);
- A2A integration — Phase 10 tasks 119-123.