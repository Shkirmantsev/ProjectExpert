# Proposal — Implement the v0.8 Phase 8 Enterprise Security Boundary

## Why

The
[`prepare-phase-8-security`](../2026-10-11-prepare-phase-8-security/proposal.md)
change adopted the one Phase 8 capability spec
(`enterprise-security-boundary` / §56) into OpenSpec. The
current branch ships the Phase 7 control plane (registry,
hooks, policy, secrets, audit, flags, ui_extensions), the
Phase 4 metadata filter that drops hits with the
`security_denied` reason, and the Phase 6 MCP server /
A2A adapter that issue outbound calls without an egress
policy wrapper.

Without Phase 8 implementation:

- the §56 capability `enterprise-security-boundary`
  remains in OpenSpec without a runtime owner; the spec
  cannot be exercised end-to-end, so the platform cannot
  honour the §68 invariants #14 / #26 / #48 / #50;
- the Phase 4 metadata filter only honours a flat
  `security_denied` reason with no classification ceiling
  or source permission awareness, so a Viewer upstream
  of a RESTRICTED source could still see the content if
  the source adapter mis-labelled the classification;
- the Phase 6 MCP server issues outbound HTTP calls through
  the configured transport without ever consulting an
  egress policy, so a coding agent holding `mcp.invoke`
  can still reach arbitrary external URLs;
- a chunk that carries a raw (non-reference) AWS access
  key pasted into a customer comment can pass through
  ingestion, never reaches the Phase 7 Secret Provider,
  and retrieval emits the key into every MCP response;
- the §56 `redaction` step (classification-driven) is
  absent, so the Phase 7 Secret Provider's redaction is
  the only defence against `>= INTERNAL` content reaching
  a `CODING_AGENT_READ_ONLY` consumer.

Phase 9's one-click launcher needs the Phase 8 egress
policy to bake into its security smoke tests; Phase 10's
A2A delegation needs the Enterprise Boundary to wrap
delegation traffic. Implementing Phase 8 now unblocks both
subsequent phases and closes the §68 invariant family
documented in the v0.8 architecture baseline.

This change resolves the gap by implementing the Phase 8
ports and default core implementations behind the prepared
`enterprise-security-boundary` capability spec, wiring the
new ports into the existing Phase 4 metadata filter,
emitting Phase 7 audit records through the existing
`AuditLogPort`, extending the Wiki with the
`modules/security.md` and `interfaces/egress.md` nodes,
recording `adr/0017-phase-8-enterprise-security-boundary.md`,
archiving the change, and updating
`openspec/CURRENT.md`.

## Goal

Ship the Phase 8 Enterprise Security Boundary subsystem so
that the future Phase 9 (Distribution) and Phase 10 (A2A
and final quality gates) changes can compose the new
boundary:

- ship `DefaultEnterpriseBoundary` as the composition root
  that wires the four Phase 8 ports around the Phase 7
  Secret / Policy / Audit foundation;
- ship `DefaultSecurityClassifier` with the four-level §56
  vocabulary and the `PUBLIC` default for unlabelled
  chunks;
- ship `DefaultSecretDetector` with the documented
  pattern bank (AWS, GitHub, PEM, JWT, high-entropy
  base64) and the typed `SecretFinding` records;
- ship `DefaultSourcePermissionPolicy` with the documented
  `(source, role) -> ALLOW|REDACT|DENY` default policy;
- ship `DefaultEgressPolicy` with the documented
  localhost-allow / capability-gate / endpoint-allow-list
  behaviour and the fail-closed fallback when the policy
  engine is absent;
- ship `DefaultRedactionPipeline` that composes the
  Phase 7 Secret Provider redaction step with the
  classification-driven step and asserts the
  no-resolved-value invariant;
- ship `DefaultSecurityAuditRecorder` that wraps the Phase
  7 `AuditLogPort` with the documented `security.*`
  operation vocabulary and the Phase 7 redaction
  filter;
- extend `MetadataFilterCore` in-place with the
  `enterprise_boundary` parameter, the new
  `security_egress_denied` and `security_redacted` reasons
  and the documented preservation of the existing
  `security_denied` reason;
- ship `tests/test_phase_8_security.py` with regression
  suites for secret detection, outbound filtering,
  retrieval redaction, capability-based delegation,
  audit emission and failure isolation;
- author / update the Wiki nodes documented in the
  [`prepare-phase-8-security/context-impact.md`](../2026-10-11-prepare-phase-8-security/context-impact.md);
- record `adr/0017-phase-8-enterprise-security-boundary.md`;
- flip Phase 8 tasks 105-108 in
  [`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md);
  archive this change; update
  `openspec/CURRENT.md`.

Out of scope for this change:

- any Phase 9 / Phase 10 work;
- modifying Phase 7 Secret / Policy / Audit behaviour;
  Phase 8 composes the Phase 7 ports, never replaces
  them;
- any plugin / skill / container / OCI / UI changes
  (those arrive in later phases).

## Affected capabilities

### What changes

This change adopts the proposed `enterprise-security-
boundary` capability from
[`openspec/changes/prepare-phase-8-security/specs/2026-10-11-enterprise-security-boundary/spec.md`](../2026-10-11-prepare-phase-8-security/specs/2026-10-11-enterprise-security-boundary/spec.md)
into
[`openspec/specs/2026-10-11-enterprise-security-boundary/`](../../specs/2026-10-11-enterprise-security-boundary/spec.md).

Reconciliation note: if the date of first acceptance is
not 2026-10-08 the implementer must rename the deltas and
the accepted folder consistently before archiving the
change. The OpenSpec governance rules require that the
delta identity and the accepted folder name match.

This change does **not** modify any other Phase 1-7
capability. The Phase 4 retrieval filter extension is
additive; the existing `security_denied` reason and the
Phase 4 metadata filter public API remain unchanged.

### New Phase 8 source surface

| Path | Purpose |
| --- | --- |
| `pi_platform/ports/security/boundary.py` | `EnterpriseBoundaryPort` |
| `pi_platform/ports/security/classification.py` | `SecurityClassificationPort` + vocabulary |
| `pi_platform/ports/security/permission.py` | `SourcePermissionPort` |
| `pi_platform/ports/security/detection.py` | `SecretDetectorPort` + `SecretFinding` |
| `pi_platform/ports/security/egress.py` | `EgressDecisionPort` + `EgressRequest` |
| `pi_platform/ports/security/redaction.py` | `RedactionPipelinePort` |
| `pi_platform/ports/security/audit.py` | `SecurityAuditPort` |
| `pi_platform/core/security/boundary.py` | `DefaultEnterpriseBoundary` |
| `pi_platform/core/security/classification.py` | `DefaultSecurityClassifier` |
| `pi_platform/core/security/permission.py` | `DefaultSourcePermissionPolicy` |
| `pi_platform/core/security/detection.py` | `DefaultSecretDetector` |
| `pi_platform/core/security/egress.py` | `DefaultEgressPolicy` |
| `pi_platform/core/security/redaction.py` | `DefaultRedactionPipeline` |
| `pi_platform/core/security/audit.py` | `DefaultSecurityAuditRecorder` |
| `pi_platform/adapters/security/detection_patterns.py` | pattern bank |
| `pi_platform/adapters/security/egress_classifier.py` | URL classifier |
| `pi_platform/core/retrieval/metadata_filter.py` | extended with `enterprise_boundary` |
| `tests/test_phase_8_security.py` | regression suites |

## Compatibility / migration impact

This change adds new files; it does not delete or
rename existing files. The Phase 4 metadata filter
extension is additive: a `MetadataFilterCore` constructed
without `enterprise_boundary` behaves exactly as it does
today.

Compatibility constraints this change respects:

- the Phase 7 control plane (`SecretProvider`,
  `PolicyEngine`, `AuditLog`) is treated as a stable
  Phase 8 input; no Phase 7 file is modified;
- the existing `MetadataFilter` public surface is
  preserved; the new constant `DROP_SECURITY_EGRESS_DENIED`
  and `DROP_SECURITY_REDACTED` are added on the port side
  only;
- the Wiki edits are confined to
  `.ai/wiki/`. No harness file is modified.
- `openspec/CURRENT.md` is updated to list the one new
  accepted capability.

Backward compatibility flag: none required because
existing consumers continue to work unchanged.

## Related knowledge

- `kb://architecture.system-overview` — updated to cite
  §56 + the new accepted capability.
- `kb://architecture.platform-overview` — phase table
  updated to mark Phase 8 shipped.
- `kb://project.implementation-roadmap` — Phase 8 tasks
  105-108 flipped to shipped.
- `kb://interfaces.secret-provider` — Phase 7 port
  composed by Phase 8.
- `kb://interfaces.policy-engine` — Phase 7 capability
  vocabulary re-used by Phase 8.
- `kb://interfaces.audit-log` — Phase 7 audit log
  extended with the security.* operation vocabulary.
- `kb://adr.0017-phase-8-enterprise-security-boundary` —
  the new ADR for the Phase 8 decision.
- `kb://glossary.platform` — extended with the Phase 8
  vocabulary.
- external: `project-intelligence-platform-architecture-v0.8.md`
  §56 Enterprise Security Boundary, §68 invariants #14
  / #26 / #48 / #50.
