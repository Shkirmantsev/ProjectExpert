---
id: interfaces.plugin-supply-chain
title: Plugin supply-chain security gate
kind: interfaces
status: active
summary: Phase 6 §48 — typed gate every packager invokes before emit; ten documented controls; the verdict is recorded in the bundle's provenance payload; deterministic.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#48
  - pi_platform/core/agent_integration/supply_chain_gate.py
  - openspec/specs/2026-10-05-plugin-supply-chain-security/spec.md
maintenance:
  mode: authored
related:
  - interfaces.plugin-distribution
  - interfaces.agent-adapter-contract
---

# Plugin supply-chain security gate

## Documented controls

The gate enforces, in deterministic order:

1. pinned semantic version (`skillVersion` / `version`);
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
10. signature support: reported, never invented.

## Reason codes

`PluginSupplyChainError.reason` ∈

`missing_pinned_version`, `skill_hash_mismatch`,
`incompatible_mcp_api`, `license_not_allowed`,
`server_identity_mismatch`, `missing_source_provenance`,
`missing_permissions`, `missing_network_requirements`,
`hidden_auto_install`, `unknown_license`.

## Verdict

`SupplyChainVerdict` carries the per-control list
(`SupplyChainCheck`) and the aggregate `passed` flag.
The `DeterministicBuildRunner` translates any failing
verdict into a `DeterministicBuildError` so the build
never emits a bundle with a hidden gap.

## Provenance

Every packager calls
`PluginSupplyChainSecurityGate.record_in_provenance` to
embed the verdict in the bundle's `PROVENANCE.json`. The
provenance payload is part of the deterministic output
inventory; two isolated runs at different absolute paths
produce byte-identical `PROVENANCE.json` files.

## Signature support

Signature support is OPTIONAL but must be reported.
The gate records `signature_support: declared but
unverified` when the bundle carries no signature, and
`signature_support: verified against configured trusted
key` when a signature is present AND the trusted key
is configured. The gate NEVER invents a signature
verification.