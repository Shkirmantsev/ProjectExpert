# Proposal — Implement Phase 10 A2A and Quality Gates

## Why

The platform currently has no A2A adapter, no reverse delegation
path to a strong external agent, no machine-checkable §68 invariant
suite, and no schema-version migration guard. The v0.8 baseline
mandates §49, §50 and §51; without Phase 10 the platform is a v0.9
release candidate rather than a v1.0 release.

This change implements the three capability specs proposed by
[`prepare-phase-10-a2a-quality-gates`](../prepare-phase-10-a2a-quality-gates/proposal.md):
the A2A transport pair behind stable ports, the reverse-delegation
flow with deterministic policy and capability gating, and the
integration-quality-gates suites (including the §68 acceptance suite
and the schema-version migration guard).

## What changes

- New `a2a` port, core and HTTP/stdio adapter family.
- New `eval` core module carrying the metrics file schema and the
  invariant probe base class.
- New reverse-delegation ports, deterministic policy and one port
  implementation per supported external agent identity.
- New integration-quality-gates suites: retrieval-first compliance,
  version mismatch, stale and conflict, security-filter, plugin
  lifecycle, OKF conformance, round-trip, branch-switch, token and
  context cost, plus the 52-invariant §68 acceptance suite and the
  schema-version migration guard.
- New `make eval`, `make invariants` and `make metrics-gate`
  targets.
- Capability discovery descriptor advertises A2A and reverse
  delegation as separate entries.
- v1.0 close-out: container image tag recorded, OCI artefact and
  distribution bundles registered.

## Out of scope

- A third-party A2A library. v1.0 ships on the Python stdlib.
- Streaming responses, `tasks/sendSubscribe` and agent-card
  extensions. v1.0 records `streaming: not-supported` and `+streaming` is
  a documented future step.
- A code-level database migration tool. v1.0 records the schema
  migration path textually and refuses silent hydration.
- Any change to MCP, REST or skill distribution contracts.

## Impact

Adds the three new capabilities `a2a-adapter`,
`external-coding-agent-integration` and `integration-quality-gates`
and closes out the v0.8 plan tasks 117-123. No existing capability
is retired or modified.
