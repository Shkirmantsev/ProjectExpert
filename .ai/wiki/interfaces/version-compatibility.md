---
id: interfaces.version-compatibility
title: Version compatibility handshake contract
kind: interfaces
status: active
summary: Phase 6 §39 + §47 — nine independently evolving dimensions, identifier sets for OKF, semver ranges for the rest, typed VersionIncompatibleError.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#39
  - project-intelligence-platform-architecture-v0.8.md#47
  - pi_platform/ports/agent_integration/__init__.py
  - pi_platform/core/agent_integration/version_compatibility.py
  - openspec/specs/2026-10-05-version-compatibility-handshake/spec.md
maintenance:
  mode: authored
related:
  - interfaces.mcp-tools
  - interfaces.plugin-supply-chain
---

# Version compatibility handshake contract

## The nine dimensions

- `platformVersion` — package release.
- `mcpApiVersion` — the product tool-schema API; distinct
  from the MCP SDK package version and the MCP wire
  protocol version.
- `mcpSdkVersion` — installed MCP Python SDK.
- `mcpWireProtocolVersion` — negotiated wire protocol.
- `knowledgeSchemaVersion` — canonical knowledge schema.
- `okfProfileVersion` — supported OKF profile versions
  (identifier set, not semver).
- `skillVersion` — canonical Agent Skill version.
- `a2aAdapterVersion` — UNIMPLEMENTED until Phase 10.
- `agentAdapterVersion` — UNIMPLEMENTED until Phase 7+.

## Semver vs identifier set

Semver `MAJOR.MINOR.PATCH` ranges apply to
`platformVersion`, `mcpApiVersion`, `mcpSdkVersion`,
`knowledgeSchemaVersion`, `skillVersion`. The OKF
profile is an identifier set; clients pick one member
of the set.

## Unavailable dimensions

`a2aAdapterVersion` and `agentAdapterVersion` are
reported with `available: false` in the
`CapabilityDescriptor.dimensions` block. The verifier
SKIPS unavailable dimensions, never compares them
against invented values.

## Typed `VersionIncompatibleError`

A failing dimension raises
`VersionIncompatibleError` carrying:

- `dimension` — the failing dimension name;
- `offeredValue` — the server / client advertised value;
- `clientConstraint` — the semver range or identifier set;
- `applicableAdapter` — the adapter the client configured,
  or `null`;
- `upgradeInstructions` — typed upgrade messaging.

## Byte-stability

`DefaultVersionCompatibilityPolicy.serialise()` is
byte-stable: two consecutive calls for an unchanged
deployment return identical JSON.

## Capability descriptor

The legacy short-form fields (`serverVersion`,
`mcpApiVersion`, `knowledgeSchemaVersion`, `okfVersions`)
are retained for backward compatibility. The new
`dimensions` block carries the same nine dimensions with
`available` flags.