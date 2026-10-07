# agent-adapter-contract Specification delta

## Purpose

TBD - created by archiving change implement-phase-6-agent-integration. Update Purpose after archive.

## Requirements


Covers architecture section §46 (Agent Adapter Contract)
and §40 (Agent Integration Packaging Layer). The agent
adapter contract defines the narrow
`AgentIntegrationAdapter` port every vendor-specific
adapter implements. The contract supports one-click
setup while keeping installers replaceable; adapters
MUST NOT own retrieval / business rules.

The contract exposes 8 operations:

```text
AgentIntegrationAdapter
├── detect()
├── install()
├── configureMcp()
├── installSkill()
├── verifyCompatibility()
├── healthCheck()
├── uninstall()
└── describe()
```

The contract is a thin port layer; every adapter
composes the canonical Agent Skill, the MCP server
endpoint and the version handshake without inventing a
new runtime store. The Phase 7 Feature / Plugin Registry
is the long-lived consumer of the contract.



### Requirement: AgentIntegrationAdapter port contract

The platform MUST expose an `AgentIntegrationAdapter`
abstract class in
`pi_platform/ports/agent_integration/adapter.py` with
the documented 8 operations:

- `detect() -> AdapterDetectionReport` — detect whether
  the target coding agent is installed on the system
  and which version is present;
- `install() -> AdapterInstallReport` — install (or
  guide the user to install) the target coding agent;
- `configureMcp() -> AdapterConfigureReport` —
  register the MCP server with the target coding
  agent;
- `installSkill() -> AdapterInstallReport` — install the
  canonical Agent Skill into the target coding agent's
  skill directory;
- `verifyCompatibility() -> AdapterCompatibilityReport`
  — run the §39 version handshake against the
  installed agent;
- `healthCheck() -> AdapterHealthReport` — verify the
  MCP server is reachable from the target coding agent
  and the canonical skill is installed;
- `uninstall() -> AdapterUninstallReport` — uninstall
  the canonical Agent Skill and the MCP registration;
- `describe() -> AdapterDescriptor` — return the
  adapter descriptor (name, version, supported agents,
  MCP endpoint, supported semver range).

#### Scenario: adapter implements the 8 operations

Given an `AgentIntegrationAdapter` subclass for a
target coding agent is constructed
When the operator enumerates the adapter's methods
Then the documented 8 operations are present
And each operation has the documented return type.

### Requirement: adapters do not own retrieval / business rules

The agent adapter contract MUST keep adapters thin and
pluggable. Every adapter MUST delegate to the MCP
server and the canonical Agent Skill for retrieval and
business rules; the adapter MUST NOT duplicate
retrieval logic, MUST NOT implement its own capability
descriptor and MUST NOT replace the §47 capability
discovery.

#### Scenario: adapter delegates retrieval

Given an adapter is configured against a target
coding agent
When the adapter processes a user request
Then the adapter delegates to the MCP server through
`project.search` or `project.retrieve_context`
And the adapter does NOT implement its own retrieval.

### Requirement: plug-in replaceable installers

The contract MUST keep the installer replaceable per
adapter. Every adapter MUST expose the documented
`install` and `uninstall` operations, MUST NOT couple
the installer to a particular package manager and MUST
allow the future Phase 7 Feature / Plugin Registry to
swap installers without changing the contract.

#### Scenario: adapter installer is replaceable

Given an adapter ships an `install` operation backed
by a documented installer
When the Phase 7 registry replaces the installer with
an alternative
Then the contract surface is unchanged
And the adapter continues to expose the documented
operations.

### Requirement: deterministic describe output

The `describe()` operation MUST return a deterministic
`AdapterDescriptor` value type. Two consecutive `describe()
calls` on the same adapter MUST produce
byte-identical output (modulo reporting-specific timestamps
that are documented as variable-by-Variable).

#### Scenario: repeated describe is stable

Given a fixed adapter state
When `describe()` runs twice consecutively
Then the non-timestamp fields are byte-identical.

### Requirement: detect is read-only

The `detect()` operation MUST be read-only. The
operation MUST NOT install, configure or modify the
target coding agent. The operation MUST report the
target's presence, version and MCP registration state.

#### Scenario: detect does not modify the target

Given an adapter runs `detect()` against an installed
coding agent
When the operation completes
Then the operation reports the documented fields
And the operation does NOT modify the target's
configuration.

### Requirement: verifyCompatibility delegates to handshake

The `verifyCompatibility()` operation MUST delegate
to the §39 version handshake. The adapter MUST NOT
implement its own handshake; the handshake is the
single source of truth for version semantics.

#### Scenario: adapter delegates to handshake

Given an adapter runs `verifyCompatibility()`
When the handshake runs
Then the operation delegates to the
`VersionCompatibilityPolicy` value type
And the adapter MUST NOT return a custom verdict.

### Requirement: adapters report typed errors

The agent adapter contract MUST report typed errors.
The typed error vocabulary MUST cover at least:

- `AdapterNotDetectedError` — the target agent is not
  installed;
- `AdapterInstallError` — the `install` operation
  failed;
- `AdapterConfigureError` — the `configureMcp`
  operation failed;
- `AdapterSkillInstallError` — the `installSkill`
  operation failed;
- `AdapterVersionIncompatibleError` — the §39
  handshake failed;
- `AdapterHealthCheckError` — the `healthCheck`
  operation failed;
- `AdapterUninstallError` — the `uninstall` operation
  failed.

#### Scenario: typed error vocabulary is exhaustive

Given an adapter processes an operation that fails
When the adapter raises an error
Then the error type is one of the documented typed
errors
And the error payload identifies the failed operation
and the target coding agent.

### Requirement: adapters are documented per target

The agent adapter contract MUST be documented per
target coding agent. For each supported target the
documentation MUST cover the MCP registration path,
the skill install path, the version handshake
contract and the health-check contract.

#### Scenario: adapter documentation is per target

Given the Phase 6 implementation change ships an
adapter for Codex
When the operator reads the adapter documentation
Then the documentation covers the documented fields
for Codex.

## Phase 6 task coverage

The change covers Phase 6 task 93 (agent adapter contract
from §46 with `detect`, `install`, `configureMcp`,
`installSkill`, `verifyCompatibility`, `healthCheck`,
`uninstall`, `describe`). Tasks 89-92 (plugin
packagers) call the adapters when packaging vendor
bundles.

Out of scope:

- the MCP server — Phase 6 task 85 (`mcp-server`);
- the canonical Agent Skill content — Phase 6 task 87
  (`agent-skill-canonical`);
- the version handshake — Phase 6 task 88
  (`version-compatibility-handshake`);
- the Codex / ChatGPT plugin package — Phase 6 task 89
  (`codex-plugin-package`);
- the Claude Code plugin package — Phase 6 task 90
  (`claude-code-plugin-package`);
- the OpenCode plugin package — Phase 6 task 91
  (`opencode-plugin-package`);
- the generic agent bundle — Phase 6 task 92
  (`generic-agent-bundle`);
- the plugin supply-chain security gate — Phase 6 task
  94 (`plugin-supply-chain-security`);
- the Wiki maintenance and archive — Phase 6 task 95
  (`phase-6-wiki-archive`);
- the Phase 7 Feature / Plugin Registry — Phase 7
  tasks 96-100;
- A2A integration — Phase 10 tasks 119-123.