---
id: modules.secret-provider
title: Phase 7 Secret Provider module map
kind: module
status: active
summary: Phase 7 control-plane Secret Provider module map covering the secret:// and env:// reference vocabulary and the mandatory redaction contract.
sourceRefs:
  - openspec/changes/prepare-phase-7-control-plane/specs/2026-10-08-secret-provider/spec.md
  - pi_platform/core/control/secrets.py
  - pi_platform/ports/control/secrets.py
maintenance:
  mode: authored
related:
  - interfaces.secret-provider
  - adr.0015-secret-references-and-redaction
---

# Phase 7 Secret Provider module map

The Phase 7 control plane ships the Secret Provider that
resolves the documented `secret://` / `env://` reference
vocabulary and exposes a redaction filter for MCP / A2A /
audit / LLM context channels.

## Reference vocabulary

The documented §59.10 reference vocabulary:

```text
secret://local/<name>[@<version>]
secret://enterprise/<name>[@<version>]
env://<name>
```

The `SecretReference` value type carries `scheme`, `backend`,
`name` and `version`. The provider rejects any reference
outside the documented vocabulary with the typed
`InvalidSecretReferenceError`.

## Backends

The default backends:

- `EnvironmentBackend` — resolves `env://<name>` references
  through `os.environ`;
- `EncryptedLocalStoreBackend` — resolves
  `secret://local/<name>` references through an encrypted
  local store (test double in this implementation; the
  production deployment MUST swap it for a real Fernet /
  AES-GCM wrapper through the Phase 1 `LicenseGate`);
- `KeychainBackend` — resolves
  `secret://enterprise/<name>` references through an OS
  keychain (test double; production deployment MUST swap it
  for a real `keyring` adapter through the Phase 1
  `LicenseGate`).

## Redaction

The `redact(value, context)` filter replaces every resolved
secret value with the documented redacted form
(`secret://<backend>/<name>[REDACTED]`) in:

- MCP responses
- A2A payloads (unless explicitly authorised)
- audit payloads
- LLM context

The redaction filter is applied by every consumer that
serialises a value to one of the four channels. The filter
returns a copy; the resolved value is never mutated.

## No-plain-text invariant

The runtime database MUST NOT contain a plain-text secret
value. The database MAY contain `SecretReference` records.
The Phase 1 `MaterialiseService` rejects any attempt to
persist a resolved value through the documented payload
contract; the audit log rejects any audit record that
carries a known resolved secret value through the typed
`SecretLeakageError`.

## Public surface

The public surface lives under
`pi_platform.core.control.secrets.DefaultSecretProvider`.
The port is `pi_platform.ports.control.secrets.SecretProviderPort`.