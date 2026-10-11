---
id: adr.0017-phase-8-enterprise-security-boundary
title: Phase 8 Enterprise Security Boundary
kind: adr
status: accepted
date: 2026-10-11
summary: Phase 8 ships the §56 Enterprise Security Boundary: classification vocabulary, source-level permissions, secret detection, egress policy, redaction pipeline, security audit, and the additive metadata-filter integration. Composes the Phase 7 Secret / Policy / Audit foundation without replacing it.
related:
  - adr.0002-canonical-runtime-separation
  - adr.0004-ports-and-adapters-extension-style
  - interfaces.secret-provider
  - interfaces.policy-engine
  - interfaces.audit-log
  - interfaces.egress
  - modules.security
  - architecture.system-overview
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#56-enterprise-security-boundary
  - openspec/changes/implement-phase-8-security/specs/2026-10-08-enterprise-security-boundary/spec.md
  - pi_platform/ports/security/boundary.py
  - pi_platform/core/security/boundary.py
maintenance:
  mode: authored
---

# ADR 0017 — Phase 8 Enterprise Security Boundary

## Context

Phases 1-7 ship canonical stores, retrieval, MCP, and the control
plane (Secret Provider, Policy Engine, Audit Log). Local access and
external transmission are still conflated: transient secrets never
resolved by the Secret Provider reach MCP responses, the Phase 6
transport can call arbitrary URLs, and the Phase 4 metadata filter
drops only on a flat `security_denied` allow-list check.

§56 requires a boundary that separates local access from external
transmission. §68.14 / §68.26 / §68.48 / §68.50 require security
metadata in retrieval, policy-controlled egress, secret
non-serialization, and operator approval for high-impact operations.

## Decision

1. `DefaultEnterpriseBoundary` (`pi_platform/core/security/boundary.py`)
   is the single composition root over five ports: classification,
   source permission, secret detection, egress, redaction — composed
   around the Phase 7 Secret Provider, Policy Engine and Audit Log
   (never replacing them).
2. Classification vocabulary is the four-level typed
   `ClassificationLevel` (PUBLIC=0 / INTERNAL=1 / CONFIDENTIAL=2 /
   RESTRICTED=3, stable `RANK`); unlabelled chunks default to PUBLIC;
   unknown values raise `UnknownClassificationLevelError`.
3. `DefaultSourcePermissionPolicy` maps
   `(source_id, classification, role)` to `ALLOW / REDACT / DENY` with
   the documented matrix (coding-agent redacts INTERNAL; viewers
   redact CONFIDENTIAL; RESTRICTED is `ADMINISTRATOR`-only).
4. `DefaultSecretDetector` + `adapters/security/detection_patterns.py`
   scan transient values (AWS / GitHub / PEM / JWT / generic API-key
   regexes plus Shannon-entropy base64 ≥ 4.5 over len ≥ 40) and emit
   typed `SecretFinding`s whose values are redacted to
   `[REDACTED:<kind>]` at every audit / log / response boundary. The
   detector composes the Phase 7 Secret Provider; it never replaces it.
5. `DefaultEgressPolicy` inspects every outbound call: localhost
   ALLOW, otherwise `network.external` capability gate +
   classification against an endpoint allow-list; DENY is fail-closed
   on missing policy engine or policy error; every evaluation emits
   `security.egress` audit. The policy engine is consulted with the
   *real* actor role carried on the `EgressRequest`.
6. `DefaultRedactionPipeline` runs the two ordered steps
   (Phase 7 Secret Provider redact, then classification-driven
   `[REDACTED:<LEVEL>]` for `VIEWER` / `CODING_AGENT_READ_ONLY` on
   ≥ `INTERNAL`) and asserts the no-resolved-value invariant via
   `SecretProvider.has_resolved`, raising
   `RedactionFailureError(reason="leak")` on violation.
7. `DefaultSecurityAuditRecorder` wraps `AuditLogPort` with the
   `security.{detect,classify,egress,redact,audit}` vocabulary; all
   emission is best-effort and redacted — audit failure never breaks
   the data plane. `security.classify` is emitted by the
   classifier on every resolve.
8. `MetadataFilterCore` gains an optional `enterprise_boundary` and
   the role-aware helper `MetadataFilter.for_actor(actor_role, ...)`;
   drop reasons `security_egress_denied` and `security_redacted` are
   additive next to the preserved Phase 4 `security_denied`; the
   allow-list check runs *first* so the Phase 4 reason stays
   canonical, and `security_redacted` keeps (does not drop) the
   candidate. The context assembler replaces the kept-but-redacted
   text with `[REDACTED:<LEVEL>]`.
9. Ports live in `pi_platform/ports/security/`, defaults in
   `pi_platform/core/security/`, tech adapters in
   `pi_platform/adapters/security/` (ADR 0004). Classification source
   ceilings are canonical knowledge under
   `project-knowledge/security/` projected read-only at runtime
   (ADR 0002).

## Consequences

- Phase 4 metadata filter extension is additive and regression-guarded
  by `tests/test_phase_4_retrieval`; Phase 8 adds
  `tests/test_phase_8_security.py` (≥ 30 scenarios over the eight
  spec Requirements: detection, egress, redaction, retrieval
  integration, auditability, capability delegation, classification,
  permissions, plus the §68.50 approval gate).
- Phase 7 contracts are inputs only; no Phase 7 file is modified.
  `SecretProvider.has_resolved` is added to `SecretProviderPort`
  (backward compatible — abstract default returns `False`) so the
  pipeline invariant is enforceable on every provider, not just the
  in-process default.
- New Wiki nodes `modules/security.md` and `interfaces/egress.md`;
  updates to capabilities / policy-engine / secret-provider /
  glossary / INDEX / system-overview (per
  `prepare-phase-8-security/context-impact.md`).
- Phase 9 smoke tests and Phase 10 A2A delegation wrap traffic
  through `EnterpriseBoundaryPort.evaluate_egress` and
  `EnterpriseBoundaryPort.redact`.
- High-impact security operations (RESTRICTED egress override,
  endpoint allow-list change) route through the Phase 7
  `REQUIRE_APPROVAL` contract (§68.50).

## Invariants honoured

- **§68.14** — security metadata participates in retrieval filtering
  (`security_denied` / `security_egress_denied` / `security_redacted`).
- **§68.26** — every outbound call passes `EgressDecisionPort`
  (fail-closed).
- **§68.48** — secrets resolved only via Secret Provider; detector
  findings and audit payloads are redacted before serialization.
- **§68.50** — high-impact security operations route through the
  Phase 7 `REQUIRE_APPROVAL` / `approval_token` contract.
- **§68.47** — capability-based authorization reuses §59.4
  vocabulary (`network.local`, `network.external`,
  `secret.reference`).
- **§68.46 / §68.52** — stable ports, modular core, no new
  deployment unit.

## Cross-references

- `.ai/wiki/modules/security.md`, `.ai/wiki/interfaces/egress.md`
  (new)
- `openspec/changes/implement-phase-8-security/specs/2026-10-08-enterprise-security-boundary/spec.md`
- `.ai/wiki/adr/0002-canonical-runtime-separation.md`
- `.ai/wiki/adr/0004-ports-and-adapters-extension-style.md`
- `.ai/wiki/interfaces/secret-provider.md`,
  `policy-engine.md`, `audit-log.md`
- architecture baseline §56; §68 invariants 14, 26, 47, 48, 50
