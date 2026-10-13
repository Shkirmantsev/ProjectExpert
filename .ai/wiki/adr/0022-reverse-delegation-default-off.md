---
id: adr-0022-reverse-delegation-default-off
kind: adr
title: "ADR 0022 — Reverse Delegation is Opt-In by Default"
status: accepted
pi_phase: 10
pi_section: "§51, §5.5"
pi_capability: external-coding-agent-integration
---

# ADR 0022 — Reverse Delegation is Opt-In by Default

## Status

Accepted (2026-10-12). Phase 10 design record for the §51
fail-closed rule and the §5.5 fail-closed discipline.

## Context

§51 makes reverse delegation an *optional* capability: "If the
platform contains an orchestrator/local-agent capability, it
should be able to participate in A2A communication through a
pluggable A2A adapter." The architecture also requires a
fail-closed stance for outbound traffic (§5.5, §68.26,
§68.48/§48). A reverse delegation that is enabled by default
would silently let the orchestrator call external agents on
Level 2 escalations, which is a clear bypass of operator
consent.

## Decision

The `reverse-delegation` feature flag defaults to **disabled**.
When disabled, the orchestrator never calls any
`ExternalAgentPort` and the L1 path is the only on-platform
escalation. Enabling the flag is an operator decision and is
recorded in the audit log.

## Consequences

- Operators must opt in to outbound escalation, matching the
  §5.5 fail-closed discipline.
- A future change that flips the default requires a documented
  ADR and a security review.
- The capability descriptor records the `reverseDelegation`
  block only when the feature is enabled, so the public
  capability contract is honest about what is available.

## Alternatives considered

- **Default-on.** Rejected: violates the §5.5 fail-closed
  rule, the §48 supply-chain guard, and the §68.26 egress
  requirement.
- **Default-on with a per-call confirmation dialog.** Rejected:
  the dialog is meaningful only when the orchestrator is
  driving a human session, which the architecture explicitly
  disclaims.

## Related

- `openspec/specs/2026-10-12-external-coding-agent-integration/spec.md` —
  Requirement *Reverse delegation is opt-in by default*.
- `kb://interfaces.reverse-delegation`
- `kb://modules.a2a`
