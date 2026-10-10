---
id: modules.audit-log
title: Phase 7 Audit Log module map
kind: module
status: active
summary: Phase 7 control-plane Audit Log module map covering the strict two-stream Audit / Operational Log separation and the no-secret-in-audit invariant.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-audit-log/spec.md
  - pi_platform/core/control/audit.py
  - pi_platform/ports/control/audit.py
maintenance:
  mode: authored
related:
  - interfaces.audit-log
  - adr.0016-audit-vs-operational-log-separation
---

# Phase 7 Audit Log module map

The Phase 7 control plane ships an Audit Log and an
Operational Log as two strictly separated streams. Secret
values and unnecessary source contents MUST never be
written into audit records.

## Audit record schema

The documented §59.13 audit record schema:

```text
timestamp
correlationId
projectVersion
actorType
actorId
pluginAgentId
operation
resource
policyDecision
result
duration
```

Every field MUST be present in every audit record; missing
fields raise `InvalidAuditRecordError`.

## Two-stream separation

The Audit Log and the Operational Log MUST NOT share a sink
or a writer. The control plane refuses to start if the
configured audit sink path matches the configured
operational sink path. The control plane refuses to start
if the two streams share a writer instance.

The `assert_separated_streams` helper enforces the invariant
in focused regression tests; the production wiring checks
the configured paths at startup.

## Redaction

The audit writer applies the Phase 7 `SecretProvider`
redaction filter to every value before writing to the
audit stream. The filter replaces every resolved secret
value with the documented redacted form
(`secret://<backend>/<name>[REDACTED]`).

The writer enforces the no-secret-in-audit invariant by
checking the redacted output for any known resolved secret
value; the writer raises the typed `SecretLeakageError` and
refuses to write the record if the invariant would be
violated. References (canonical strings ending in
`[REDACTED]`) are legitimate audit fields.

## Operational Log

The Operational Log records diagnostics, errors,
performance and health. The Operational Log MUST NOT
contain audit records; the Operational Log MUST NOT be
consulted for security / state-relevant queries.

## Public surface

The public surface lives under
`pi_platform.core.control.audit`:

- `DefaultAuditLog` — append-only audit log with strict
  redaction.
- `DefaultOperationalLog` — append-only operational log.
- `assert_separated_streams` — separation invariant helper.

The ports are `AuditLogPort` and `OperationalLogPort` in
`pi_platform.ports.control.audit`.