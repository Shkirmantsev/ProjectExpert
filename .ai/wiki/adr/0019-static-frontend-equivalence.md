---
id: adr.0019-static-frontend-equivalence
title: Phase 9 static frontend equivalence
kind: adr
status: accepted
date: 2026-10-11
summary: Phase 9 ships a hand-authored static frontend (HTML / CSS / vanilla JS) instead of the named default Ionic. No Node.js / npm / build stage at runtime or build time. The decision is documented as an ADR because it deviates from the named default in plan task 110.
related:
  - adr.0005-platform-source-language
  - adr.0018-rest-transport
  - interfaces.rest-api
  - modules.ui
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#57-human-interfaces
  - openspec/specs/2026-10-11-human-interface-web-ui/spec.md
  - pi_platform/adapters/ui/static/
  - tests/test_phase_9_distribution.py
maintenance:
  mode: authored
---

# ADR 0019 — Phase 9 static frontend equivalence

## Context

Plan task 110 says "Implement the lightweight custom UI (default Ionic
or documented equivalent)". The named default would introduce a
Node.js / npm build stage and a substantial dependency tree into the
final image, none of which is justified for a single-user local UI
that consumes ten documented operations.

The §1 invariants forbid silent changes to the runtime stack; this
decision deviates from the named default and is therefore recorded as
an ADR rather than as an implicit substitution.

## Decision

Ship the static frontend as hand-authored HTML, CSS and vanilla
JavaScript under `pi_platform/adapters/ui/static/`. The container
serves the assets directly. No bundler, no `require(`, no
`process.env`, no Node.js, no npm.

The frontend references all ten §44.3 operations and covers the §57
scenarios (ask a question, inspect evidence, browse sources, navigate
the graph, browse the Wiki, view project version, view indexing
status, view knowledge status, request materialisation with an
approval token, and request agent delegation).

The `tests/test_phase_9_distribution.py` suite includes assertions
that the frontend contains no `require(`, no `process.env` and no
admin/upload surfaces.

## Consequences

- **Pro** — the final image has no Node.js runtime; the licence
  inventory gains no entry.
- **Pro** — no build stage; the `Containerfile` `COPY` is enough.
- **Pro** — replaceable by any equivalent frontend that satisfies
  the §44.3 contract.
- **Con** — the UI lacks framework affordances (components,
  reactivity, bundler-tree-shaking). The implementation remains small
  because the surface is small (ten operations).
- **Neutral** — the static UI must be served from the same origin as
  the API; CORS is intentionally absent.

## Trigger for revisiting

If the UI grows beyond twenty operations, or requires streaming,
real-time updates, or component reuse that vanilla JS cannot sustain
cleanly, this ADR is the place to revisit and either upgrade the
static layer or replace it with a buildable equivalent while still
keeping Node.js out of the final image.