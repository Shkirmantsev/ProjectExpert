---
id: modules.security
title: Phase 8 Enterprise Security Boundary module map
kind: module
status: active
summary: Phase 8 Enterprise Security Boundary module map covering the §56 four-level classification vocabulary, source-level permissions, secret detection, egress policy, redaction pipeline, security audit, and the additive metadata-filter integration.
sourceRefs:
  - openspec/changes/implement-phase-8-security/specs/2026-10-08-enterprise-security-boundary/spec.md
  - pi_platform/ports/security/boundary.py
  - pi_platform/core/security/boundary.py
  - pi_platform/core/security/classification.py
  - pi_platform/core/security/permission.py
  - pi_platform/core/security/detection.py
  - pi_platform/core/security/egress.py
  - pi_platform/core/security/redaction.py
  - pi_platform/core/security/audit.py
  - pi_platform/adapters/security/detection_patterns.py
  - pi_platform/adapters/security/egress_classifier.py
maintenance:
  mode: authored
related:
  - interfaces.egress
  - interfaces.capabilities
  - modules.policy-engine
  - modules.secret-provider
  - interfaces.audit-log
  - adr.0017-phase-8-enterprise-security-boundary
---

# Phase 8 Enterprise Security Boundary module map

The Phase 8 control plane ships the Enterprise Security
Boundary that separates local access from external
transmission. Phase 8 composes the Phase 7 Secret / Policy
/ Audit foundation without replacing it.

## Composition root

`DefaultEnterpriseBoundary`
(`pi_platform/core/security/boundary.py`) is the single
composition root. It wires five ports:

```text
SecurityClassificationPort       (PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED)
SourcePermissionPort             (ALLOW / REDACT / DENY)
SecretDetectorPort               (AWS / GitHub / PEM / JWT / API-key / entropy)
EgressDecisionPort               (loopback / local / external)
RedactionPipelinePort            (Phase 7 + classification-driven)
```

Every port has a default implementation under
`pi_platform/core/security/`; every default is replaceable
through the port boundary per ADR 0004.

## Classification vocabulary

The four-level `ClassificationLevel` carries a stable
ordered integral `RANK`:

| Level | Rank | Default reach |
| --- | --- | --- |
| PUBLIC | 0 | Everyone |
| INTERNAL | 1 | All except `CODING_AGENT_READ_ONLY` (REDACT) |
| CONFIDENTIAL | 2 | `MAINTAINER` / `ADMINISTRATOR` only |
| RESTRICTED | 3 | `ADMINISTRATOR` only |

Unlabelled chunks default to `PUBLIC`; unknown values
raise `UnknownClassificationLevelError`. A configured
source ceiling clamps a chunk DOWN but never UPGRADES it
(ceiling is a max-bound, not a downgrader).

## Source-level permissions

`DefaultSourcePermissionPolicy` maps
`(source_id, classification, role)` to
`ALLOW / REDACT / DENY` with the documented matrix.
The policy file lives under the canonical tree
`project-knowledge/security/permissions.yaml` (loaded
at hydrate time per §7.1).

## Secret detection

`DefaultSecretDetector` + the regex bank
(`adapters/security/detection_patterns.py`) cover the
documented Phase 8 pattern set:

```text
AWS_ACCESS_KEY         = AKIA[0-9A-Z]{16}
GITHUB_TOKEN          = ghp_[A-Za-z0-9]{36}
PEM_PRIVATE_KEY_HEADER = -----BEGIN (RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----
JWT_BEARER            = eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}
GENERIC_API_KEY       = api_key="…"
HIGH_ENTROPY_BASE64   = shannon_entropy >= 4.5 AND len >= 40 AND no_whitespace
```

Every finding is redacted to `[REDACTED:<kind>]` before
audit emission; raw values never reach the audit log.

## Redaction pipeline

`DefaultRedactionPipeline` runs two ordered steps:

1. Phase 7 Secret Provider redaction (replaces resolved
   values with `<ref>[REDACTED]`).
2. Classification-driven redaction
   (`[REDACTED:<LEVEL>]` for `VIEWER` /
   `CODING_AGENT_READ_ONLY` on `>= INTERNAL`).

The pipeline asserts the no-resolved-value invariant
via `SecretProvider.has_resolved`; a violation raises
`RedactionFailureError(reason="leak")`. The
`actor_capabilities` argument is honoured: an actor
without `secret.reference` reaching `>= INTERNAL` content
is redacted per the capability-delegation Requirement.

## Egress policy

`DefaultEgressPolicy` inspects every outbound call.
Decision order (fail-closed):

1. Loopback (`127.0.0.1` / `::1` / `localhost`) → ALLOW.
2. `network.external` capability required.
3. Policy Engine consultation with the *real* actor
   role + granted capabilities + `approval_token`.
4. Classification against the endpoint allow-list.
5. RESTRICTED egress without `approval_token` → DENY
   (per §68.50).
6. Missing policy engine → DENY.

Every evaluation emits `security.egress` audit with the
redacted URL.

## Metadata-filter integration

`MetadataFilterCore` accepts an optional
`enterprise_boundary` parameter. The Phase 4 `security_denied`
reason is preserved; the new `security_egress_denied` and
`security_redacted` reasons are additive. Redacted hits
are KEPT (not dropped); the context assembler replaces
their textual content with `[REDACTED:<LEVEL>]`.

## Audit vocabulary

Every security-relevant action emits through the Phase 7
`AuditLogPort` with the `security.*` operation vocabulary:

```text
security.detect
security.classify
security.egress
security.redact
security.audit
```

Audit emission is best-effort; a failed Audit Log never
breaks the data plane.

## Operational notes

- The pattern bank is versioned (`phase-8.0`).
- The endpoint allow-list defaults to `{PUBLIC}`; the
  PUBLIC level is always allowed.
- The in-memory decision history is capped at 1024
  entries so long-running processes do not grow unbounded.
- The redaction pipeline is composition-only; it never
  re-implements Phase 7 Secret Provider behaviour.

## Cross-references

- `interfaces/egress.md` — `EgressDecisionPort` /
  `EgressRequest` / `EgressDecision` contract.
- `interfaces/capabilities.md` — Phase 7 capability
  vocabulary re-used for egress and capability
  delegation.
- `modules/policy-engine.md` — the Phase 7 Policy Engine
  consulted by the egress policy.
- `modules/secret-provider.md` — Phase 7 Secret Provider
  composed by the redaction pipeline and the audit
  recorder.
- `interfaces/audit-log.md` — the Phase 7 audit log that
  the security audit recorder wraps.
- `adr/0017-phase-8-enterprise-security-boundary.md` —
  the Phase 8 architecture decision.
- architecture baseline §56; §68 invariants 14, 26, 47,
  48, 50.
