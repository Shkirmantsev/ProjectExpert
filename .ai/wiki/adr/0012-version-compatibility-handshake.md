---
id: adr.0012-version-compatibility-handshake
title: "ADR 0012: Phase 6 version compatibility handshake"
kind: adr
status: accepted
summary: Track nine independently evolving version dimensions (platform, mcpApi, mcpSdk, mcpWireProtocol, knowledgeSchema, okfProfile, skill, a2aAdapter, agentAdapter); use semver ranges for the first five and identifier sets for OKF; report unavailable dimensions as unavailable rather than fabricating placeholders; typed VersionIncompatibleError with offered value, client constraint, applicable adapter and upgrade instructions.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#39
  - project-intelligence-platform-architecture-v0.8.md#47
  - openspec/specs/2026-10-07-version-compatibility-handshake/spec.md
  - pi_platform/ports/agent_integration/__init__.py
  - pi_platform/core/agent_integration/version_compatibility.py
maintenance:
  mode: authored
---

# ADR 0012: Phase 6 version compatibility handshake

- Status: accepted
- Date: 2026-10-07
- Deciders: Phase 6 implementation change
- Source spec:
  [`2026-10-07-version-compatibility-handshake`](../../../openspec/specs/2026-10-07-version-compatibility-handshake/spec.md)
- Architecture baseline:
  [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  §39 (Protocol and Artifact Version Compatibility) and
  §47 (Capability Discovery)

## Context

The platform tracks nine independently evolving dimensions;
the canonical Agent Skill, the MCP server, the four vendor
adapters and the local model runtime must agree on a
compatibility handshake before any production traffic flows.
§39 requires explicit semver / identifier-set handling per
dimension and a typed error payload that the calling agent
can act on without parsing prose. §47 requires the
capability descriptor to advertise the actual offered
metadata, not architecture example numbers.

## Options

1. **Single version string** for the whole platform.
   (Rejected — couples independent dimensions.)
2. **Free-form version map** with no enforcement.
   (Rejected — clients would have to parse the JSON to
   learn what failed.)
3. **Nine-dimension typed policy** with semver ranges for
   five, identifier set for OKF, explicit unavailable flag
   for the rest, and a typed `VersionIncompatibleError`
   carrying the failed dimension, offered value, client
   constraint, applicable adapter, and upgrade
   instructions. (Chosen.)

## Decision

Adopt
`pi_platform/ports/agent_integration/{VersionRange, CompatibilityRange, ClientCapabilityReport, VersionCompatibilityPolicy, VersionIncompatibleError}`.
The implementation is in
`pi_platform/core/agent_integration/version_compatibility.py`
and uses `DefaultVersionCompatibilityPolicy`. Two
consecutive `serialise()` calls produce byte-identical JSON
for an unchanged deployment.

`mcpApiVersion` is the **product tool-schema API**; it is
distinct from the MCP SDK package version and the MCP wire
protocol version. `a2aAdapterVersion` and
`agentAdapterVersion` are reported unavailable until Phase 10
and Phase 7+ respectively; the verifier skips unavailable
dimensions, never compares them against invented values.

The capability descriptor exposes the same nine dimensions
through the new `dimensions` block; the legacy short-form
fields are retained for backward compatibility.

## Consequences

- Clients can act on a typed payload rather than parsing
  prose; upgrade instructions are explicit.
- Architecture example numbers (`0.8.0`, `1.3.0`, `0.7.0`,
  `0.2`) are not copied as runtime defaults.
- Adding a new dimension requires both the port and the
  capability discovery change; the handshake gate fails
  closed when the dimension is missing.
- The typed error is the source of truth for skill / plugin
  / adapter upgrade messaging.