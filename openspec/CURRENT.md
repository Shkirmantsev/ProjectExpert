# Accepted project state ("actual is")

This is the central entry point for this repository's agreed current requirements.
The linked specs are canonical; this inventory does not duplicate their content.
The Wiki explains observed implementation. Report any discrepancy between specs
and implementation explicitly. Proposed changes are excluded from this view.

## Framework-provided capabilities

The development harness (see `AGENTS.md` and `docs/README.md`) ships with the
following accepted capabilities. They document the harness contract, not the
project product.

| Accepted capability | Canonical requirements |
|---|---|
| Project initialization | [Spec](specs/2026-09-07-project-initialization/spec.md) |
| Session handoff | [Spec](specs/2026-09-07-session-handoff/spec.md) |
| Skill integration | [Spec](specs/2026-09-07-skill-integration/spec.md) |
| Portable harness tooling | [Spec](specs/2026-10-03-portable-harness-tooling/spec.md) |
| Harness command lifecycle | [Spec](specs/2026-10-04-harness-command-lifecycle/spec.md) |
| OpenSpec governance | [Spec](specs/2026-10-03-openspec-governance/spec.md) |

## Project product capabilities

This project has not yet adopted accepted product specifications. Create new
specs through the OpenSpec workflow (`openspec/changes/<id>/` →
`openspec/specs/YYYY-MM-DD-domain-capability/`) and link them here when
adopted.

Maintain this inventory with every accepted addition, retirement or identity
migration. Dates record first acceptance, not the latest edit. Run
`python harness.py openspec-check` to verify its completeness and naming.