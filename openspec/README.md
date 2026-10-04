# OpenSpec workflow

[Documentation map](../docs/README.md) · [Engineering conventions](../docs/conventions/README.md)

[config.yaml](config.yaml) selects [production-sdd](schemas/production-sdd/schema.yaml).
The schema names templates and their prerequisites:

| Artifact | Template | Requires |
|---|---|---|
| proposal | [proposal.md](schemas/production-sdd/templates/proposal.md) | none |
| specs | [spec.md](schemas/production-sdd/templates/spec.md) | proposal |
| design | [design.md](schemas/production-sdd/templates/design.md) | proposal, specs |
| context-impact | [context-impact.md](schemas/production-sdd/templates/context-impact.md) | proposal, specs, design |
| tasks | [tasks.md](schemas/production-sdd/templates/tasks.md) | specs, design, context-impact |

Create a bounded change under `changes/<id>/` using these artifacts. Implementation
follows tasks, with verification and affected Wiki updates before adoption/archive.
See the [OpenSpec skill](../.agents/skills/catalog/openspec-change/SKILL.md).

## Directory naming

Use lowercase kebab-case; underscores are invalid.

- Accepted specs: `specs/YYYY-MM-DD-domain-capability/spec.md`. Use the Git date
  when the capability first became an accepted spec; retain that date on updates.
- Active changes: semantic `verb-domain-purpose` without a date prefix.
- Archived changes: `changes/archive/YYYY-MM-DD-original-change-name/`, dated
  when archived. Never stack a second date prefix.

Delta capability folders for existing capabilities must match the dated accepted
identity; the harness gate rejects undated names and different dates for those
capabilities. New capabilities may retain a semantic proposed name until adoption;
assign their first acceptance date when adopting (or reconcile an intended date).
Historical archives retain their original paths as evidence. During this migration,
existing accepted capabilities use their original Git acceptance dates, including
the session-handoff spec's original loose-file history.

## Central current state (“actual is”)

[CURRENT.md](CURRENT.md) is the single navigation entry for the complete accepted
requirements under `specs/`. Each capability appears exactly once. It links to
canonical requirements rather than duplicating them. Proposed deltas in `changes/`
are excluded; the Wiki explains observed implementation and reports mismatches.
Update current specs and CURRENT together when a verified change is adopted,
renamed or retired. The harness gate checks naming, coverage and stale links.

Completed change evidence is retained under `changes/archive/` as
`YYYY-MM-DD-original-change-name/`, dated when archived.

Run `python harness.py openspec-check`. Its built-in structural check is limited;
full schema validation runs only when the OpenSpec CLI is installed.
