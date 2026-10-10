---
id: interfaces.capabilities
title: Phase 7 Capability vocabulary interface
kind: interface
status: active
summary: Phase 7 §59.4 capability vocabulary interface used by every control-plane subsystem.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-capabilities/spec.md
  - pi_platform/ports/control/policy.py
maintenance:
  mode: authored
related:
  - interfaces.policy-engine
  - modules.policy-engine
---

# Phase 7 Capability vocabulary interface

The §59.4 capability vocabulary is the cross-cutting
contract every control-plane subsystem uses. The vocabulary
is shared across UI users, coding agents, A2A agents,
plugins, hooks, CLI operations and automation.

## Vocabulary

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

## Role defaults

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

## Read-only coding agent

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

## Port surface

The vocabulary is declared as the `Capability` enumeration
in `pi_platform.ports.control.policy`. The role defaults
are declared as `ROLE_*` constants and the
`DEFAULT_ROLE_CAPABILITIES` mapping.