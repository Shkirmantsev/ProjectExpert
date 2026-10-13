---
id: a2a-adapter
kind: module
title: A2A Adapter
status: active
pi_phase: 10
pi_section: "§50"
pi_capability: a2a-adapter
---

# A2A Adapter

The Phase 10 A2A adapter ships the platform-side implementation of
the agent-to-agent collaboration surface required by v0.8 §50. A2A
is **complementary** to MCP and REST: MCP exposes tools and context
to coding agents, REST exposes the human UI, A2A exposes the
platform as a peer agent to other agents.

## Ports and core

The adapter is split across three files, none of which imports any
A2A protocol library:

- `pi_platform/ports/a2a/` — the four ports
  (`A2aAdapterPort`, `AgentCardPort`, `ReverseDelegationPort`,
  `ExternalAgentPort`) and their value types;
- `pi_platform/core/a2a/` — the dispatch core, the Agent Card
  builder, the reverse-delegation policy core, the loopback binder
  and the `SecretRedactor`;
- `pi_platform/adapters/a2a/` — the HTTP and (planned) stdio
  transports and the wire-envelope translation.

The core never imports an A2A protocol library. The transport
modules translate wire formats at the adapter boundary.

## Capability handshake

The `CapabilityDiscovery` descriptor advertises the A2A surface
through two new blocks:

```yaml
protocols:
  mcp: { version: "1.3.0" }
  a2a: { enabled: true, specVersion: "1.0", supportedProtocols: ["tasks/send"], streaming: "not-supported" }
reverseDelegation: { enabled: <bool>, supportedAgents: ["claude-code", "codex", "opencode", "hermes", "generic-mcp", "generic-a2a"] }
```

The `enabled` flag toggles whether the A2A routes are served. The
`reverseDelegation.enabled` flag is independent and defaults to
`false` (Phase 10 §51 fail-closed rule).

## Spec version pin

`pi_platform.core.a2a.A2A_SPEC_VERSION` is a single tracked
constant (`A2aSpecVersion(major=1, minor=0)`) the capability
descriptor surfaces. When a peer offers a different major version,
the adapter refuses the handshake with `version-incompatible`
(10 GONE).

## Transport

The HTTP transport binds loopback by default. A non-loopback bind
requires an explicit operator override and is recorded on the audit
log on startup. The transport ships only the minimum A2A surface
required by §50:

- `GET /.well-known/agent-card.json` — Agent Card;
- `POST /a2a/v1/tasks:send` — inbound `tasks/send`.

Streaming, `tasks/sendSubscribe` and other extensions are explicitly
recorded as `not-supported` for v1.0.

## Related

- `kb://interfaces.a2a`
- `kb://modules.eval`
- `kb://adr.0021-a2a-adapter-isolation`
- `kb://adr.0023-stdlib-only-a2a-transport`
- `openspec/specs/2026-10-12-a2a-adapter/spec.md`
