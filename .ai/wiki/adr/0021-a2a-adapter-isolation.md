---
id: adr-0021-a2a-adapter-isolation
kind: adr
title: "ADR 0021 — A2A Adapter Isolation from the Core Domain Model"
status: accepted
pi_phase: 10
pi_section: "§50, §68.22-23"
pi_capability: a2a-adapter
---

# ADR 0021 — A2A Adapter Isolation from the Core Domain Model

## Status

Accepted (2026-10-12). This decision is the Phase 10 design
record for the §50 isolation rule.

## Context

The v0.8 architecture documents A2A as an "agent-to-agent
collaboration" interface that is *complementary* to MCP and REST
(§50, §68.22-23). A2A wire formats evolve independently of the
core domain model. The architecture explicitly mandates that the
implementation "track a stable released A2A specification through
an adapter so protocol evolution does not leak into the core
domain model" (§50).

## Decision

The platform ships A2A as a dedicated adapter family with three
properties:

1. **No third-party A2A library in `pi_platform/core/`.** The core
   module graph never imports an A2A protocol library; a static
   guard test in `tests/test_phase_10_a2a.py` enforces this.
2. **Port value-types only inside the core.** Wire JSON dicts do
   not cross the adapter boundary; the
   `pi_platform.adapters.a2a.envelope` module is the only place
   where the wire format is interpreted.
3. **One tracked `A2A_SPEC_VERSION` constant.** A future A2A
   spec revision replaces the adapter, not the core, and not
   the spec.

## Consequences

- The core domain model is stable across A2A wire-format
  revisions. The capability descriptor always advertises the
  pinned major version.
- Adapters can be unit-tested in isolation by passing typed
  values to the ports.
- An A2A library change is bounded to the
  `adapters/a2a/` directory; no `core/` import requires an
  update.

## Alternatives considered

- **Adopt an existing A2A library in `core/`.** Rejected:
  violates §50, makes the core depend on a third-party supply
  chain, and drags the library's license into the platform
  inventory.
- **Skip the port boundary and call the adapter directly from
  the orchestrator.** Rejected: it couples the orchestrator to
  a specific wire format and removes the test isolation that
  the ports pattern provides.

## Related

- `openspec/specs/2026-10-12-a2a-adapter/spec.md` — Requirement
  *A2A adapter isolation from the core domain model*.
- ADR 0023 — A2A transport is stdlib-only for v1.0.
- `kb://modules.a2a`
