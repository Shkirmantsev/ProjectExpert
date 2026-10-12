---
id: modules.registry
title: Phase 7 Feature / Plugin Registry module map
kind: module
status: active
summary: Phase 7 control-plane Feature / Plugin Registry module map covering the §59.1 lifecycle state machine, manifest validation and dependency resolution.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-control-registry/spec.md
  - pi_platform/core/control/registry.py
  - pi_platform/ports/control/registry.py
maintenance:
  mode: authored
related:
  - interfaces.control-registry
  - adr.0014-control-plane-policy-engine
---

# Phase 7 Feature / Plugin Registry module map

The Phase 7 control plane ships a Feature Registry and a
Plugin Registry that share the documented §59.1 lifecycle
state machine. Built-in features and installed plugins use
the same vocabulary; the two registries differ only in the
semantic role they play.

## Lifecycle state machine

The documented §59.1 states:

```text
installed
enabled
disabled
failed
incompatible
blocked-by-policy
update-available
```

Transitions are validated by `ports/control/registry.py`
through the `_assert_can_transition` helper. Illegal
transitions raise `IllegalLifecycleTransition`. The state
graph is intentionally narrow so the registry surface stays
predictable.

## Manifest validation

Every manifest passes through the `_validate_manifest`
helper before installation. The helper checks:

- the documented capability vocabulary (`Phase 7 §59.4`),
  rejecting unknown capabilities with `ManifestValidationError(check="capabilities")`;
- the documented SPDX-like license identifier, rejecting
  empty or whitespace-only strings;
- the 64-character lowercase SHA-256 content hash;
- the MAJOR.MINOR.PATCH API version shape.

The Phase 1 `LicenseGate` remains the thorough checker for
SPDX identifiers; the registry's validator refuses only
malformed inputs.

## Policy engine wiring

The registry consults the Phase 7 `PolicyEnginePort` before
every mutation through `attach_policy_engine(policy)`. The
default wiring requires `Capability.MCP_ADMIN` for every
mutation; high-impact mutations demand an approval token
through the documented `REQUIRE_APPROVAL` decision contract.

## Audit wiring

The registry records an audit entry on every mutation
through `attach_audit_log(audit_log)`. The audit log is the
Phase 7 `DefaultAuditLog`; the registry's `_safe_record`
helper builds a typed `AuditRecord` and calls the audit
log's `record()` method positionally.

## Persistence

The default in-memory implementation is authoritative for
focused regression; durable state is persisted through the
Phase 1 `GitPort` / `WorkingTreeOverlayPort` and the Phase 3
`RuntimeStore`. The registry MUST NOT introduce a new
runtime store; that is the documented §59 architectural
invariant.

## Public surface

The public surface is `pi_platform.core.control.registry`
exposes:

- `DefaultFeatureRegistry`
- `DefaultPluginRegistry`

The two implementations are identical today; the ports
layer keeps them separate so a future distributed
implementation can diverge cleanly.