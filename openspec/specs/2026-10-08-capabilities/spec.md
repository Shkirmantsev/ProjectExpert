# capabilities Specification delta

## Purpose

Expose the cross-cutting §59.4 capability vocabulary, role defaults and read-only coding-agent capability set used by every control-plane subsystem.

## Requirements


### Requirement: Capability vocabulary is the documented §59.4 enumeration

The platform MUST declare the documented §59.4 capability
vocabulary:

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

Every control-plane subsystem MUST consume the vocabulary
through the typed `Capability` enumeration. A subsystem that
invents a capability outside the vocabulary MUST be rejected
by the Phase 7 Policy Engine with the typed
`UnknownCapabilityError`.

#### Scenario: an invented capability is rejected

Given an actor requests the capability `net.free`
When any control-plane subsystem forwards the request to
the Phase 7 Policy Engine
Then the engine raises `UnknownCapabilityError`
And the subsystem rejects the request.

### Requirement: Role defaults match the documented §59.5 set

The platform MUST declare the documented §59.5 role defaults:

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

The platform MUST resolve authorization to capabilities; role
defaults are convenience initialisers, not the authorization
source of truth. A future ABAC layer MAY consider branch,
source classification, plugin identity, agent identity,
environment, network destination and operation risk.

#### Scenario: Maintainer cannot grant network.external

Given a `Maintainer` requests `network.external`
When the engine evaluates the request
Then the engine returns `DENY` because
`network.external` is reserved for `Administrator`.

### Requirement: Read-only coding agent capability set matches §59.8

The platform MUST declare the documented §59.8 read-only
coding agent capability set:

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

#### Scenario: read-only coding agent cannot materialise knowledge

Given a coding agent carries the documented §59.8
read-only capability set
When the agent invokes `materialize_knowledge`
Then the engine returns `DENY` because
`knowledge.materialize` is not in the documented set.
