# policy-engine Specification delta

## Purpose

Expose the central Policy Engine that resolves every sensitive execution path into the documented ALLOW / DENY / REQUIRE_APPROVAL decision contract.

## Requirements


### Requirement: Policy Engine exposes the §59.4 capability vocabulary

The Policy Engine MUST expose the documented §59.4
capability vocabulary:

```text
knowledge.read
knowledge.write
knowledge.materialize

retrieval.query
retrieval.admin

graph.read
graph.write

source.read
source.import

filesystem.read
filesystem.write

git.read
git.write

config.read
config.write

secret.reference
secret.resolve

mcp.invoke
mcp.admin

agent.delegate

network.local
network.external

audit.read
audit.write
```

The vocabulary MUST be enforced by the `Capability`
enumeration; the engine MUST reject any unknown capability
with the typed `UnknownCapabilityError`. The vocabulary is
shared across UI users, coding agents, A2A agents, plugins,
hooks, CLI operations and automation.

#### Scenario: engine rejects an unknown capability

Given an actor requests the capability `net.free`
When the engine evaluates the request
Then the engine raises `UnknownCapabilityError`
And the engine records an audit entry with
`operation=policy.evaluate`, `result=error`.

### Requirement: Policy Engine returns the documented decision contract

The Policy Engine MUST return one of the documented
decisions: `ALLOW`, `DENY`, `REQUIRE_APPROVAL`. The decision
MUST be a typed `PolicyDecision` value carrying
`decision`, `capability`, `resource`,
`policyDecisionRationale` (human-readable) and
`approvalRequestId` (when the decision is
`REQUIRE_APPROVAL`). The engine MUST record an audit entry
for every decision through the Phase 7 `AuditLog`.

#### Scenario: materialise returns REQUIRE_APPROVAL for a Viewer

Given a `Viewer` invokes `materialize_knowledge`
When the engine evaluates the request
Then the engine returns `PolicyDecision(decision="REQUIRE_APPROVAL", capability="knowledge.materialize", resource=...)`
And the engine records an audit entry with
`policyDecision="require_approval"`, `result=pending`.

#### Scenario: materialise returns ALLOW for a Maintainer with a valid approval token

Given a `Maintainer` invokes `materialize_knowledge`
with a valid approval token issued by the Phase 1
`MaterialiseService`
When the engine evaluates the request
Then the engine returns `PolicyDecision(decision="ALLOW", ...)`.

### Requirement: Policy Engine applies the documented role defaults

The Policy Engine MUST expose the documented §59.5 role
defaults:

```text
Viewer        — knowledge.read, retrieval.query, graph.read,
                source.read, git.read, config.read, audit.read
Developer     — Viewer + filesystem.write, config.write,
                source.import, mcp.invoke, audit.write
Maintainer    — Developer + knowledge.write, graph.write,
                retrieval.admin, git.write, secret.reference,
                mcp.admin, agent.delegate, network.local
Administrator — Maintainer + knowledge.materialize,
                secret.resolve, network.external
```

The engine MUST resolve authorization to capabilities; role
defaults are convenience initialisers, not the authorization
source of truth. The engine MUST support per-actor capability
overrides that take precedence over the role default.

#### Scenario: Viewer cannot perform git.write

Given a `Viewer` invokes `git.write`
When the engine evaluates the request
Then the engine returns `PolicyDecision(decision="DENY", capability="git.write", ...)`.

### Requirement: Policy Engine supports the documented read-only coding agent

The Policy Engine MUST recognise the documented §59.8
read-only coding agent capability set:

```text
knowledge.read      = allow
retrieval.query     = allow
config.read         = allow
audit.write         = allow

knowledge.write     = deny
knowledge.materialize = deny
config.write        = deny
git.write           = deny
secret.resolve      = deny unless explicitly scoped
```

A coding agent with this capability set MAY consume runtime
configuration through the Phase 7
`/control/runtime/context` port and emit audit / log events
through the Phase 7 `AuditLog`. The agent MUST NOT perform
durable writes through the documented capabilities.

#### Scenario: read-only coding agent can read runtime configuration

Given a coding agent carries the documented §59.8
read-only capability set
When the agent invokes `get_runtime_context`
Then the engine returns `PolicyDecision(decision="ALLOW", capability="config.read", ...)`.

#### Scenario: read-only coding agent cannot materialise knowledge

Given a coding agent carries the documented §59.8
read-only capability set
When the agent invokes `materialize_knowledge`
Then the engine returns `PolicyDecision(decision="DENY", capability="knowledge.materialize", ...)`.

### Requirement: Policy Engine is the central authorisation source

Every sensitive execution path (MCP tool, A2A request, REST
request, plugin, hook, agent delegation, materialisation,
Git write, secret resolution, external network request) MUST
consult the Policy Engine. The Phase 1 `PolicyDecisionStub`
continues to back the Phase 1 `MaterialiseService` approval
boundary until the implementation change rewires it; the
Policy Engine MUST NOT bypass the existing Phase 1
`TrustedApprovalBoundary`. Plugins MUST NOT implement
independent shadow authorization systems for core resources.

#### Scenario: MCP tool consults the policy engine

Given an MCP client invokes `project.materialize_knowledge`
When the MCP server processes the call
Then the MCP server consults the Phase 7 Policy Engine
before invoking the Phase 1 `MaterialiseService`
And the MCP server records an audit entry with the
documented §59.13 fields.

### Requirement: Policy Engine serialise is byte-stable

Two consecutive `serialise()` calls on the same policy
engine MUST return byte-identical JSON. The serialised form
MUST include the documented capability vocabulary, the
documented role defaults and the currently registered
per-actor capability overrides. The serialised form MUST
NOT include resolved secret values.

#### Scenario: serialise is byte-stable

Given the engine has registered four role defaults and one
per-actor override
When the operator invokes `serialise()` twice
Then the two returned JSON strings are byte-identical.
And neither string contains a resolved secret value.
