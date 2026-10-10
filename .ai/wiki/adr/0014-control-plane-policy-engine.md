---
id: adr.0014-control-plane-policy-engine
title: ADR-0014 — Phase 7 central policy engine separation
kind: adr
status: proposed
summary: Adopt the Phase 7 §59.4–§59.12 central Policy Engine and replace the Phase 1 PolicyDecisionStub behind the existing PolicyDecisionPort.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-policy-engine/spec.md
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-capabilities/spec.md
  - pi_platform/core/control/policy.py
  - pi_platform/ports/control/policy.py
  - project-intelligence-platform-architecture-v0.8.md §59.4, §59.5, §59.11, §59.12
maintenance:
  mode: authored
---

# ADR-0014 — Phase 7 central policy engine separation

## Status

Proposed (Phase 7 implementation change adoption promotes
this ADR to `status: accepted`).

## Context

The v0.8 architecture baseline mandates a central Policy
Engine that resolves every sensitive execution path
(MCP tool, A2A request, REST request, plugin, hook, agent
delegation, materialisation, Git write, secret resolution,
external network request) into the documented
`ALLOW / DENY / REQUIRE_APPROVAL` decision contract.

The Phase 1 `PolicyDecisionStub` in
`pi_platform/core/sync/policy_stub.py` is a minimal
hydrate/reconcile-allow + everything-else-required-approval
fallback. It does not implement the §59.4 capability
vocabulary, the §59.5 role defaults, the §59.8 read-only
coding-agent capability set or the typed `ApprovalRequired`
exception.

Without a central Policy Engine, the Phase 6 MCP server,
agent adapter contract, plugin supply-chain security gate and
version handshake cannot enforce a documented decision
contract; every consumer must invent its own authorisation
logic. Phase 7's Control Plane, Phase 8's enterprise
boundary, Phase 9's distribution launcher and Phase 10's
A2A delegation all depend on a single central authorisation
source.

## Decision

Adopt the Phase 7 central Policy Engine that:

- declares the §59.4 capability vocabulary as the typed
  `Capability` enumeration;
- declares the §59.5 role defaults (`Viewer / Developer /
  Maintainer / Administrator`) and the §59.8 read-only
  coding-agent capability set;
- returns the documented `ALLOW / DENY / REQUIRE_APPROVAL`
  decision contract through the typed `PolicyDecision`
  value;
- raises the typed `DeniedError` and `ApprovalRequired`
  exceptions when the consumer calls `authorize`;
- replaces the Phase 1 `PolicyDecisionStub` behind the
  existing Phase 1 `PolicyDecisionPort`;
- does NOT modify the Phase 1 `MaterialiseService`
  approval boundary or the Phase 1
  `TrustedApprovalBoundary`.

## Consequences

- Every Phase 6 MCP tool, Phase 6 plugin supply-chain
  security gate, Phase 6 agent adapter and Phase 5 query
  orchestrator that previously consumed the Phase 1 stub
  continues to operate through the existing
  `PolicyDecisionPort`; the backing implementation changes
  behind the port.
- The Phase 7 control plane ships with the typed
  `Capability` enumeration; future subsystems MUST consume
  the vocabulary through the enumeration and reject any
  unknown capability with the typed
  `UnknownCapabilityError`.
- High-impact capabilities (`knowledge.materialize`,
  `git.write`, `network.external`, `secret.resolve`,
  `mcp.admin`) require an explicit approval token; the
  engine returns the typed `ApprovalRequired` exception
  with the `approval_request_id` field.
- The Phase 8 enterprise boundary and the Phase 9
  distribution launcher consume the same central engine;
  no shadow authorization systems are allowed in plugins.