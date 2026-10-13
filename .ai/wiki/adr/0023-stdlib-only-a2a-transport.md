---
id: adr-0023-stdlib-only-a2a-transport
kind: adr
title: "ADR 0023 — A2A Transport Uses the Python Standard Library for v1.0"
status: accepted
pi_phase: 10
pi_section: "§5.5, §48, §50"
pi_capability: a2a-adapter
---

# ADR 0023 — A2A Transport Uses the Python Standard Library for v1.0

## Status

Accepted (2026-10-12). Phase 10 design record for the A2A
transport choice.

## Context

The §5.5 / §48 license gate requires every bundled dependency
to have a known license and a gate verdict. The A2A transport is
one of the surfaces the platform exposes at runtime; an A2A
library adoption would be a permanent supply-chain entry in the
default container image. The current A2A specification is small
enough to express through the Python standard library.

## Decision

The Phase 10 A2A transport is implemented on the Python
standard library only:

- HTTP transport: `http.server.ThreadingHTTPServer`;
- JSON encoding: the `json` module;
- Concurrency limits: the platform's existing in-process
  counters;
- Bearer-token auth: handled by the existing secret provider.

Any future adoption of a third-party A2A library requires:

1. an ADR-style update;
2. an SPDX identifier in the dependency inventory;
3. a license-gate verdict before the dependency ships.

## Consequences

- Zero new Python dependency is added in Phase 10.
- The Phase 10 test suite exercises the transport in-process
  with an ephemeral port; no third-party test fixture is
  required.
- A future A2A spec revision that mandates features the stdlib
  cannot express (e.g. HTTP/2 push) requires reopening this
  ADR.

## Alternatives considered

- **Adopt an existing A2A library in v1.0.** Rejected: permanent
  supply-chain entry for a surface that the stdlib already
  covers; requires license inventory updates for a small
  benefit.
- **Adopt a low-level HTTP library (`requests`, `httpx`,
  `aiohttp`).** Rejected: the surface is intentionally narrow
  (a loopback HTTP listener) and the standard library already
  implements it without the supply-chain cost.

## Related

- `openspec/specs/2026-10-12-a2a-adapter/spec.md` — Requirement
  *A2A transport uses the Python standard library for v1.0*.
- ADR 0021 — A2A adapter isolation from the core domain model.
- `kb://modules.a2a`
