---
id: adr.0016-audit-vs-operational-log-separation
title: ADR-0016 — Phase 7 audit vs operational log separation
kind: adr
status: proposed
summary: Adopt the Phase 7 §59.13 strict two-stream Audit Log / Operational Log separation and the no-secret-in-audit invariant.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-audit-log/spec.md
  - pi_platform/core/control/audit.py
  - pi_platform/ports/control/audit.py
  - project-intelligence-platform-architecture-v0.8.md §59.13
maintenance:
  mode: authored
---

# ADR-0016 — Phase 7 audit vs operational log separation

## Status

Proposed (Phase 7 implementation change adoption promotes
this ADR to `status: accepted`).

## Context

The v0.8 architecture baseline mandates the strict
two-stream Audit Log / Operational Log separation. The
Audit Log records security / state-relevant actions and
decisions; the Operational Log records diagnostics,
errors, performance and health. Secret values and
unnecessary source contents MUST never be written into
audit records.

Without strict separation, operators cannot prove who called
which MCP tool with which capability at which project
version. A bug in the writer dispatch could let the
Operational Log receive audit records or vice versa.

## Decision

Adopt the Phase 7 Audit Log that:

- records the documented §59.13 audit record schema
  (`timestamp`, `correlationId`, `projectVersion`,
  `actorType`, `actorId`, `plugin/agentId`, `operation`,
  `resource`, `policyDecision`, `result`, `duration`);
- is append-only; updates and deletes are not supported;
- enforces the no-secret-in-audit invariant through the
  Phase 7 Secret Provider redaction filter and the typed
  `SecretLeakageError` backstop;
- is strictly separated from the Operational Log; the two
  streams MUST NOT share a sink or a writer;
- refuses to start when the configured audit sink path
  matches the configured operational sink path or when the
  two streams share a writer instance.

## Consequences

- Every sensitive execution path (MCP tool, A2A request,
  REST request, plugin, hook, agent delegation,
  materialisation, Git write, secret resolution, external
  network request) MUST consult the Audit Log through the
  Phase 7 `_safe_record` helper.
- The Operational Log records diagnostics, errors,
  performance and health; the Operational Log MUST NOT
  contain audit records and MUST NOT be consulted for
  security / state-relevant queries.
- The Audit Log supports time-range queries and
  correlation-id queries; the query result MUST NOT include
  resolved secret values.
- A failed audit write MUST close the calling data-plane
  action and return a typed error to the operator.