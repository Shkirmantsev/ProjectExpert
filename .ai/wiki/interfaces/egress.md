---
id: interfaces.egress
title: Phase 8 Egress Decision interface
kind: interface
status: active
summary: Phase 8 Egress Decision port contract: every outbound MCP / A2A / REST / plugin call passes through EgressDecisionPort.evaluate before it leaves the platform.
sourceRefs:
  - openspec/changes/implement-phase-8-security/specs/2026-10-08-enterprise-security-boundary/spec.md
  - pi_platform/ports/security/egress.py
  - pi_platform/core/security/egress.py
  - pi_platform/adapters/security/egress_classifier.py
maintenance:
  mode: authored
related:
  - modules.security
  - interfaces.capabilities
  - modules.policy-engine
  - interfaces.audit-log
  - adr.0017-phase-8-enterprise-security-boundary
---

# Phase 8 Egress Decision interface

The `EgressDecisionPort` is the typed contract that
inspects every outbound call from the platform. The port
returns a typed `EgressDecision` carrying the verdict,
rationale and channel. The port is fail-closed.

## Contract

```text
EgressDecisionPort.evaluate(EgressRequest) -> EgressDecision
```

## EgressRequest

```text
EgressRequest(
    url                       # destination URL (HTTP / HTTPS / WSS / ...)
    classification            # PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED
    actor_role                # Role enum (VIEWER / DEVELOPER / ... / ADMINISTRATOR)
    capability_requested      # Phase 7 capability vocabulary
    actor_capabilities = ()   # the caller's granted capability set
    approval_token    = None  # operator approval for high-impact operations
    correlation_id    = ""    # deterministic correlation identifier
    resource          = ""    # opaque resource identifier (path, MCP tool)
)
```

## EgressDecision

```text
EgressDecision(
    allowed      : bool       # ALLOW or DENY
    rationale    : str        # human-readable rationale
    channel      : EgressChannel  # loopback / local / external / unknown
    request      : EgressRequest
)
```

`EgressDeniedError` is raised by helpers that prefer
exceptions over an inline check on the `allowed` flag.

## EgressChannel

The URL classifier
(`pi_platform/adapters/security/egress_classifier.py`)
maps a URL to one of four channels:

| Channel | Triggered by |
| --- | --- |
| `loopback` | `127.0.0.1`, `::1`, `localhost`, `ip6-localhost` |
| `local`    | RFC1918 / link-local / multicast addresses |
| `external` | Public IP / non-IP hostname |
| `unknown`  | Malformed URL / empty host |

## Default policy decision table

| Condition | Decision |
| --- | --- |
| `channel == loopback` | ALLOW (rationale "localhost") |
| `capability_requested != network.external` | DENY (capability required) |
| `policy_engine is None` | DENY (fail-closed) |
| `policy.decision != ALLOW` (no token) | DENY (REQUIRE_APPROVAL) |
| `classification ∉ endpoint_allow` | DENY (classification filter) |
| `classification == RESTRICTED` and no `approval_token` | DENY (§68.50) |
| All checks pass | ALLOW (rationale = "capability=... and endpoint_allow contains ...") |

The endpoint allow-list defaults to `{PUBLIC}`. Adding a
classification is the operator's job; `revoke_endpoint`
refuses to strip `PUBLIC`.

## Audit obligations

Every evaluation (ALLOW or DENY) emits an
`AuditRecord(operation=security.egress, result=..., resource=<url>)`
through the wired `AuditLogPort`. The audit resource is
the raw URL; payload values are redacted by the audit
recorder.

## Capability vocabulary

`EgressRequest.capability_requested` is matched against
the Phase 7 `Capability.NETWORK_EXTERNAL`. The egress
port consults the Phase 7 `PolicyEnginePort` with the
real `actor_role` and `actor_capabilities` carried on
the request.

## Fail-closed semantics

- Missing policy engine → DENY.
- Policy engine exception → DENY (`policy-engine-error`).
- Missing `approval_token` on RESTRICTED egress → DENY.
- `revoke_endpoint("PUBLIC")` is a no-op (the
  always-allowed floor).

## Non-goals

- Loopback does not imply "private network". A
  `192.168.1.1` URL is treated as `external` for the
  default policy and follows the standard
  capability / classification / approval flow.
- Wildcard host matching is out of scope; the egress
  port trusts only the explicit matchers.

## Cross-references

- `modules/security.md` — the boundary that owns the
  default `EgressPolicy`.
- `interfaces/capabilities.md` — the `network.external`
  / `network.local` capability vocabulary.
- `modules/policy-engine.md` — the Phase 7 Policy Engine
  consulted for high-impact authorisation.
- `interfaces/audit-log.md` — the audit log that receives
  every `security.egress` record.
- `adr/0017-phase-8-enterprise-security-boundary.md` —
  the Phase 8 architecture decision.
