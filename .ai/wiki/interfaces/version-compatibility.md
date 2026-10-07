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
  - openspec/specs/2026-10-07-version-compatibility-handshake/spec.md
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
- `a2aAdapterVersion` — UNIMPLEMENTED until Phase 10.
- `knowledgeSchemaVersion` — canonical knowledge schema.
- `okfProfileVersion` — supported OKF profile versions
  (identifier set, not semver).
- `skillVersion` — canonical Agent Skill version.
- `pluginDistributionSchemaVersion` — release manifest
  schema identifier (identifier set, not semver).
- `agentAdapterVersion` — UNIMPLEMENTED until Phase 7+.
- `runtimeIndexSchemaVersion` — the runtime index schema
  version (UNIMPLEMENTED until Phase 7+).

## Semver vs identifier set

Semver `MAJOR.MINOR.PATCH` ranges apply to
`platformVersion`, `mcpApiVersion`,
`knowledgeSchemaVersion`, `skillVersion`. The OKF
profile and the plugin-distribution schema are identifier
sets; clients pick one member of the set.

## Unavailable dimensions

`a2aAdapterVersion`, `agentAdapterVersion` and
`runtimeIndexSchemaVersion` are reported with
`available: false` in the `CapabilityDescriptor.dimensions`
block. The verifier SKIPS unavailable dimensions, never
compares them against invented values.

## Typed `VersionIncompatibleError`

A failing dimension raises
`VersionIncompatibleError` carrying:

- `dimension` — the failing dimension name;
- `serverOfferedRange` — the range the server advertised
  (e.g. `>=1.3.0 <2.0.0` or `one of {0.2}` or
  `(unavailable)`);
- `clientOfferedValue` — the value the client declared;
- `applicableAdapter` — the adapter the client is configured
  with, or `null`;
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