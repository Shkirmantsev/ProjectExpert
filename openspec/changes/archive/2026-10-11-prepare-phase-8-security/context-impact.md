# Context Impact — prepare-phase-8-security

This change ships the Phase 8 capability spec and the
supporting OpenSpec artifacts under
`openspec/changes/prepare-phase-8-security/`. It ships
**zero production code**. The durable Wiki and ADR updates
listed below land in the future
`implement-phase-8-security` change, not in this one.

## Wiki nodes to create (future implement)

- `modules/security.md` — Phase 8 Enterprise Security
  Boundary module map. Covers the §56 vocabulary, the
  `DefaultEnterpriseBoundary` composition root, the
  relationship to Phase 7 Secret / Policy / Audit, and the
  Phase 4 metadata filter integration. Cross-links
  `interfaces/egress.md`, `interfaces/capabilities.md`,
  `modules/policy-engine.md`, `modules/secret-provider.md`
  and `interfaces/audit-log.md`.
- `interfaces/egress.md` — typed `EgressDecisionPort`,
  `EgressRequest`, `EgressDecision` contract and the
  default `EgressPolicy`. Cross-links
  `modules/security.md`, `modules/policy-engine.md` and
  `interfaces/audit-log.md`.

## Wiki nodes to update (future implement)

- `interfaces/capabilities.md` — extend the §59.4 / §59.5
  capability vocabulary section with the Phase 8 cross-
  reference (no capability is added or removed; the
  redaction cross-reference is the only edit).
- `modules/policy-engine.md` — note that Phase 8 reuses
  the Phase 7 Policy Engine for egress authorisation
  (`network.local`, `network.external`,
  `secret.reference`).
- `modules/secret-provider.md` — note that the Phase 8
  `RedactionPipeline` composes the Phase 7 Secret Provider
  redaction as step 1 of the documented two-step redaction
  pipeline.
- `glossary/platform.md` — extend with `EgressPolicy`,
  `SecretDetection`, `SourcePermission`,
  `SecurityClassification`, `RedactionPipeline`. Each term
  is documented with a stable id and a brief definition
  that links back to §56.
- `INDEX.md` — add the new `modules/security.md` and
  `interfaces/egress.md` entries with their cross-links.
- `architecture/system-overview.md` — extend the phase
  table and the security boundary paragraph to cite §56
  and the new accepted `enterprise-security-boundary`
  capability.

## ADR to create (future implement)

- `adr/0017-phase-8-enterprise-security-boundary.md` —
  records the Phase 8 architecture decision. Status
  `accepted` upon `implement-phase-8-security` start.
  Cites:
  - §56 Enterprise Security Boundary;
  - §68.14 (Metadata enforces version / security /
    correctness constraints);
  - §68.26 (External transmission is security-policy
    controlled);
  - §68.48 (Secrets are resolved through Secret Providers
    and never serialized into Git knowledge or logs);
  - §68.50 (High-impact operations may require explicit
    operator approval).
  Cross-links the existing ADRs:
  - `adr/0004-ports-and-adapters-extension-style`
    (Phase 8 follows the ports / adapters split);
  - `adr/0002-canonical-runtime-separation` (the
    classification source mapping is canonical).

## OpenSpec to update (future implement)

- `openspec/CURRENT.md` — add the one new accepted
  capability
  (`enterprise-security-boundary`) to the product
  capability table.
- `openspec/changes/plan-v0-8-platform-architecture/tasks.md`
  — flip tasks 105-108 to `[x]` after the future
  `implement-phase-8-security` change is adopted.

## Knowledge references

- `kb://architecture.system-overview` — cite §56 + the
  new capability from this node.
- `kb://architecture.platform-overview` — update the
  phase table to mark Phase 8 planned → shipped.
- `kb://project.implementation-roadmap` — mark Phase 8
  tasks 105-108 as shipped.
- `kb://project.task-handoff` — the durable task-state
  lifecycle records the Phase 8 implementation as
  completed when the future implement change is
  archived.

## Change bookkeeping

The future `implement-phase-8-security` change must
include a `context-impact.md` that confirms every node
above was created / updated before its archive step.

This change ships no code, no Wiki edits, no ADR file,
and no OpenSpec state changes; the only filesystem
impact in `openspec/changes/prepare-phase-8-security/`
is the planning artifacts.
