---
id: adr.0015-secret-references-and-redaction
title: ADR-0015 — Phase 7 secret references and redaction
kind: adr
status: proposed
summary: Adopt the Phase 7 §59.10 secret:// / env:// reference vocabulary and the mandatory redaction contract.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-secret-provider/spec.md
  - pi_platform/core/control/secrets.py
  - pi_platform/ports/control/secrets.py
  - project-intelligence-platform-architecture-v0.8.md §59.10
maintenance:
  mode: authored
---

# ADR-0015 — Phase 7 secret references and redaction

## Status

Proposed (Phase 7 implementation change adoption promotes
this ADR to `status: accepted`).

## Context

The v0.8 architecture baseline mandates the Secret Provider
with the `secret://` / `env://` reference vocabulary and
mandatory redaction in MCP responses, A2A payloads (unless
explicitly authorised), audit payloads and LLM context.

The runtime database MUST NOT become a plain-text secret
vault. The provider resolves references through OS keychain,
environment variables, encrypted local store and (optionally)
enterprise vault; the provider exposes a redaction filter
that replaces every resolved secret value with the documented
redacted form.

Without a portable reference vocabulary, every consumer
must invent its own secret handling; secret values leak
through MCP responses, A2A payloads, audit records and
LLM context. Phase 7's Control Plane, Phase 8's enterprise
boundary, Phase 9's distribution launcher and Phase 10's
A2A delegation all depend on a single redaction contract.

## Decision

Adopt the Phase 7 Secret Provider that:

- accepts the documented `secret://<backend>/<name>`
  and `env://<name>` reference vocabulary;
- rejects any reference outside the documented vocabulary
  with the typed `InvalidSecretReferenceError`;
- exposes the `SecretReference` value type and the
  documented backends (`EnvironmentBackend`,
  `EncryptedLocalStoreBackend`, `KeychainBackend`);
- exposes the `redact(value, context)` filter that
  replaces every resolved secret value with the documented
  redacted form in MCP / A2A / audit / LLM context;
- enforces the no-plain-text-secret invariant through the
  typed `SecretLeakageError` in the Audit Log;
- does NOT persist resolved values to the runtime
  database; the database carries `SecretReference` records
  only.

## Consequences

- Every consumer that serialises a value to one of the
  four channels (MCP response, A2A payload, audit
  payload, LLM context) MUST apply the redaction filter.
- The runtime database MAY carry `SecretReference`
  records; it MUST NOT carry resolved values. The Phase 1
  `MaterialiseService` rejects any attempt to persist a
  resolved value through the documented payload contract.
- The audit log raises `SecretLeakageError` and refuses to
  write the record if the redaction filter failed to
  replace a known resolved secret value.
- The Phase 1 `LicenseGate` MUST extend its check to
  forbid runtime databases that contain plain-text secret
  values; the gate emits
  `LicenseGateFinding(severity="forbid", rule="no_plain_text_secret")`.