---
id: modules.policy-engine
title: Phase 7 Policy Engine module map
kind: module
status: active
summary: Phase 7 control-plane Policy Engine module map covering the §59.4 capability vocabulary, role defaults and the ALLOW / DENY / REQUIRE_APPROVAL decision contract.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-policy-engine/spec.md
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-capabilities/spec.md
  - pi_platform/core/control/policy.py
  - pi_platform/ports/control/policy.py
maintenance:
  mode: authored
related:
  - interfaces.policy-engine
  - interfaces.capabilities
  - adr.0014-control-plane-policy-engine
---

# Phase 7 Policy Engine module map

The Phase 7 control plane ships the central Policy Engine
that resolves every sensitive execution path (MCP tool, A2A
request, REST request, plugin, hook, agent delegation,
materialisation, Git write, secret resolution, external
network request) into the documented
`ALLOW / DENY / REQUIRE_APPROVAL` decision contract.

## Capability vocabulary

The §59.4 capability vocabulary is declared as the
`Capability` enumeration in `ports/control/policy.py`. The
enumeration is exhaustive: every control-plane subsystem
MUST consume the vocabulary through the typed enumeration
and reject any unknown capability with
`UnknownCapabilityError`.

## Role defaults

The §59.5 role defaults are declared as documented tuples:

```text
ROLE_VIEWER
ROLE_DEVELOPER
ROLE_MAINTAINER
ROLE_ADMINISTRATOR
ROLE_CODING_AGENT_READ_ONLY
```

The `DEFAULT_ROLE_CAPABILITIES` mapping carries the
documented capability assignment per role. Authorisation
resolves to capabilities; role defaults are convenience
initialisers, not the authorisation source of truth.

## Read-only coding agent

The §59.8 read-only coding agent capability set is exposed
as `ROLE_CODING_AGENT_READ_ONLY`. A coding agent with this
capability set MAY consume runtime configuration and emit
audit / log events; the agent MUST NOT perform durable
writes.

## Decision contract

The engine returns one of three typed decisions:

```text
Decision.ALLOW
Decision.DENY
Decision.REQUIRE_APPROVAL
```

The typed `PolicyDecision` value carries `decision`,
`capability`, `resource`, `policy_decision_rationale` and
`approval_request_id` (for `REQUIRE_APPROVAL`). The engine
raises the typed `DeniedError` for `DENY` and the typed
`ApprovalRequired` for `REQUIRE_APPROVAL` without an
approval token.

## Audit wiring

The engine records an audit entry for every decision
through `attach_audit_log(audit_log)`. The `_safe_record`
helper builds a typed `AuditRecord` and calls the audit
log's `record()` method positionally. The audit log
records the §59.13 fields with the documented decision as
`policyDecision` and `result`.

## Replacement of the Phase 1 stub

The engine replaces the Phase 1 `PolicyDecisionStub`
behind the existing `PolicyDecisionPort`. The Phase 1
`MaterialiseService` approval boundary and the Phase 1
`TrustedApprovalBoundary` remain in force.

## Public surface

The public surface lives under
`pi_platform.core.control.policy.DefaultPolicyEngine`. The
port is `pi_platform.ports.control.policy.PolicyEnginePort`.

## Phase 8 reuse

The Phase 8 [Enterprise Security Boundary](security.md) consults
this Policy Engine for every egress evaluation; the egress
port threads the *real* actor role + granted capabilities +
optional `approval_token` through the documented
`PolicyRequest` contract. The `NETWORK_EXTERNAL` capability
gates every non-loopback call, and a missing `approval_token`
on a RESTRICTED egress routes through the `REQUIRE_APPROVAL`
contract per §68.50.