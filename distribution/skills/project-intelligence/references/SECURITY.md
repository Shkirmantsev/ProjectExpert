# Security Reference

This document specifies the §48 supply-chain security gate
the MCP server enforces on every plugin / vendor bundle, the
trusted approval boundary that guards write / materialisation
tools, and the shared release identity every vendor packager
must agree on.

## Plugin supply-chain gate

Every packager calls
`PluginSupplyChainSecurityGate.run(manifest)` before emit.
The gate enforces:

- pinned semantic version (`skillVersion` / `version`);
- skill content hash matches the canonical release metadata;
- MCP API compatibility range present;
- SPDX license identifier on the allow-list;
- server identity matches across the four vendor bundles
  (shared release identity);
- source repository / provenance metadata present;
- permissions block declared;
- network requirements block declared;
- no hidden auto-install directives in any script.

The gate records its verdict in the bundle's provenance
payload so the artefact carries its own audit trail.

## Trusted approval boundary

`MaterialiseService.materialise_durable_changes` and the
write MCP tools (`project.materialize_knowledge`,
`project.refresh_sources`) require an `approval_id` issued by
`TrustedApprovalBoundary`. The boundary:

- signs tokens with an operator key (HMAC-SHA-256);
- binds each token to an action (`materialise` /
  `refresh_sources`);
- binds each token to a canonical repo root;
- binds each token to a set of change ids (or an empty set);
- expires tokens (default 5 minutes);
- rejects `DENY` from `PolicyDecisionPort` unconditionally.

When the boundary is closed (no key configured) every write
fails closed. The default `MaterialiseService` wiring uses the
closed boundary.

## Typed errors

The MCP server surfaces these typed errors as JSON
`{type, message, ...}` payloads:

- `ApprovalRejected.reason` ∈
  `missing_token, policy_denied, forged_signature, expired,
  not_yet_valid, wrong_action, wrong_repository,
  change_superset_mismatch, malformed_token, no_issuer_key`.
- `RuntimeNotReadyError.snapshot.consistent` is `False` when
  the runtime project knowledge is not in a consistent state.
- `VersionIncompatibleError.dimension` is the failing
  dimension; `server_offered_range`, `client_offered_value`,
  `applicable_adapter`, `upgrade_instructions` are populated.
- `FilteredEscalationNotSupportedError.level` is the
  requested escalation level; `filters` and
  `project_version` describe the rejected envelope.

## Shared release identity

All four packagers (`projects/codex/`,
`projects/claude-code/`, `projects/opencode/`,
`projects/generic-agent/`) MUST agree on:

- skill content hash;
- skill version;
- MCP API compatibility range;
- license identifier;
- server identity (the `serverIdentity` block in the
  distribution manifest).

A mismatch in any one dimension fails the shared build.

## Signature support

Signature support is OPTIONAL but must be reported. The gate
records `signature_support: declared but unverified` when the
bundle carries no signature, and `signature_support: verified
against configured trusted key` when a signature is present
AND the trusted key is configured. The gate NEVER invents a
signature verification.

## Provenance

Every generated bundle carries a `provenance` payload with:

- the source repository URL;
- the build identity (deterministic content hash of the
  release input);
- the supply-chain gate verdict (pass / fail with per-check
  detail);
- the shared release identity fields.