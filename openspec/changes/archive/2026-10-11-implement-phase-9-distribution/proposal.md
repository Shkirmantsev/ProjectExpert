# Proposal — Implement Phase 9 Distribution

## Why

The platform currently has no consumer other than an AI coding agent. The v0.8
baseline requires human access independent of any harness (§57, §44.4) and a
"download → start → open browser" experience (§58), with a single container as
the default packaging (§45.1).

This change implements the three capability specs proposed by
[`prepare-phase-9-distribution`](../prepare-phase-9-distribution/proposal.md):
the UI-facing REST surface with a lightweight static frontend, the optional
Open WebUI profile, the OKF v0.2 validation gate, and the one-click launchers
with a finalised single-container image.

## What changes

- New `ui` port, core service and HTTP adapter family.
- New static frontend served by the core container.
- New feature-flagged OpenAI-compatible shim for the Open WebUI profile.
- OKF validation enforced in the materialisation path, plus a shippable OKF
  profile adapter.
- Completed Linux and Windows launchers, a finalised `Containerfile` and
  compose profiles.
- Phase 9 regression and launch smoke suites.

## Out of scope

- A2A and reverse delegation (Phase 10).
- Integration evaluation suites and the full §68 acceptance suite (Phase 10).
- New Python third-party dependencies.
- Bundling project Wiki content into the image.
- Any change to the existing MCP agent interface.

## Impact

Extends `canonical-knowledge-schema`, `plugin-supply-chain-security`,
`mcp-server` and `agent-adapter-contract`; adds the three new capabilities
`human-interface-web-ui`, `okf-wiki-profile-distribution` and
`one-click-distribution`.