---
id: adr.license-governance-default
title: Default permissive license policy with explicit review gate
kind: adr
status: proposed
summary: Adopt a default permissive license policy with explicit operator acceptance for review-required licenses and a deny-list for non-commercial terms.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/plan-v0-8-platform-architecture/specs/license-governance/spec.md
maintenance:
  mode: authored
---

# Default permissive license policy with explicit review gate

## Context

The v0.8 architecture (§4) requires the platform to remain
commercially usable and redistributable. Every bundled library,
framework, model runtime, parser, database component, plugin,
hook package, UI extension and agent adapter must have its license
explicitly tracked and validated. Permissive OSI-approved licenses
are preferred; copyleft/reciprocal licenses require explicit
operator acceptance; restricted/non-commercial licenses are denied
by default.

## Decision

The platform will ship with a default `licensing.allow` list
(`Apache-2.0`, `MIT`, `BSD-2-Clause`, `BSD-3-Clause`, `ISC`) and a
default `licensing.review` list (`MPL-2.0`, `EPL-2.0`,
`LGPL-2.1-only`, `LGPL-3.0-only`). Model licenses are tracked
separately from library licenses. A CI license gate blocks releases
when the gate fails. Plugins, hooks, UI extensions and agent
adapters MUST be license-checked before activation.

## Alternatives considered

- Trusting upstream license declarations without automated gating.
  Rejected because missing or misdeclared licenses are a real supply-
  chain risk.
- Hard-denying copyleft licenses. Rejected because some organisations
  intentionally accept copyleft; the policy must remain a legal /
  product configuration, not hard-coded business logic.
- Tracking only model weights and ignoring library licenses. Rejected
  because both ship in the same artefact and both carry obligations.

## Consequences

- `license-governance` Phase 1 spec depends on this decision.
- Every dependency introduced in subsequent phases MUST pass the gate
  before adoption.
- The build pipeline MUST emit a dependency inventory, model license
  inventory, SBOM and NOTICE.

## Verification

`openspec/changes/plan-v0-8-platform-architecture/tasks.md`
(`plan-v0-8-platform-architecture` change) includes Phase 1 tasks
35-37 (`LicensePolicy`, `LicenseGate`, `DependencyInventoryPort`,
model-license tracker, CI license gate) and Phase 1 task 40 (CI
license-gate regression test) that exercise this decision.