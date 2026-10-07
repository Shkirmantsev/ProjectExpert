---
id: adr.0013-plugin-supply-chain-security
title: "ADR 0013: Phase 6 plugin supply-chain security"
kind: adr
status: accepted
summary: Adopt a typed supply-chain security gate every packager invokes before emit; gate enforces pinned version, content hash, MCP API range, license allow-list, source provenance, permissions, network requirements, no hidden auto-install, and signature support against a configured trusted key; the verdict is recorded in the bundle's provenance payload.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#48
  - openspec/specs/2026-10-07-plugin-supply-chain-security/spec.md
  - pi_platform/core/agent_integration/supply_chain_gate.py
maintenance:
  mode: authored
---

# ADR 0013: Phase 6 plugin supply-chain security

- Status: accepted
- Date: 2026-10-07
- Deciders: Phase 6 implementation change
- Source spec:
  [`2026-10-07-plugin-supply-chain-security`](../../../openspec/specs/2026-10-07-plugin-supply-chain-security/spec.md)
- Architecture baseline:
  [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  §48 (Security and Trust for Skills and Plugins)

## Context

Phase 6 ships four per-vendor bundles (Codex, Claude Code,
OpenCode, generic agent) plus the canonical Agent Skill and
the MCP server. These are executable / instruction-bearing
supply-chain artifacts; §48 requires explicit release
controls (pinned version, content hash, SBOM, malware /
secret scan, deterministic build, signature support,
source provenance, permissions, network requirements, no
hidden auto-install). Write / materialization tools must
remain approval-controlled even when a skill / plugin
requests them.

## Options

1. **Trust every bundle by default** because it came from
   the harness repo. (Rejected — supply-chain invariant is
   on the artifact, not the source.)
2. **External dependency scanner** only (SBOM, license).
   (Rejected — misses content hash, hidden auto-install,
   signature support.)
3. **Typed `PluginSupplyChainSecurityGate`** with the
   documented controls, invoked by every packager before
   emit, with the verdict recorded in the bundle's
   `PROVENANCE.json`. (Chosen.)

## Decision

Adopt `pi_platform/core/agent_integration/supply_chain_gate.py`
with `PluginSupplyChainSecurityGate`. The gate runs the
following controls in a deterministic order:

1. pinned semantic version;
2. skill content hash matches canonical release metadata;
3. MCP API compatibility range present;
4. SPDX license identifier on the allow-list
   (`Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`,
   `ISC` by default);
5. server identity matches the shared release identity
   (skill content hash, server version, MCP range, license);
6. source repository / provenance metadata present;
7. permissions block declared;
8. network requirements block declared;
9. no hidden auto-install directives in any script;
10. signature support: OPTIONAL but reported; the gate
    records "unverified" when the bundle has no signature
    and `verified` only when a configured trusted key is
    available.

A failed control raises a typed
`PluginSupplyChainError` with a documented reason code;
`DeterministicBuildRunner` translates any failing verdict
into a `DeterministicBuildError` so the build never emits
a bundle with a hidden gap.

## Consequences

- Every bundle carries its own audit trail in
  `PROVENANCE.json` (the verdict, the per-check detail,
  the shared release identity).
- The four packagers agree on the shared release identity;
  any disagreement fails the build before emit.
- Signature support is honest: the gate never invents a
  verification; absence is reported as unverified.
- The license gate (Phase 1) keeps its allow-list; the
  supply-chain gate extends it with explicit detection of
  unattributed dependencies.
- Future supply-chain controls (e.g. SBOM attestation,
  Sigstore-style transparency log) plug in by adding one
  more check to the gate; the verdict shape is stable.