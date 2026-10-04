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

| Accepted capability | Canonical requirements |
|---|---|
| Project knowledge repository layout | [Spec](specs/2026-10-04-project-knowledge-repository-layout/spec.md) |
| Canonical knowledge schema | [Spec](specs/2026-10-04-canonical-knowledge-schema/spec.md) |
| Git version-aware runtime | [Spec](specs/2026-10-04-git-version-aware-runtime/spec.md) |
| Bidirectional canonical runtime sync | [Spec](specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md) |
| License governance | [Spec](specs/2026-10-04-license-governance/spec.md) |
| Content addressed processing | [Spec](specs/2026-10-04-content-addressed-processing/spec.md) |
| Context enrichment | [Spec](specs/2026-10-04-context-enrichment/spec.md) |
| Document source adapters | [Spec](specs/2026-10-04-document-source-adapters/spec.md) |
| Ingestion pipeline driver | [Spec](specs/2026-10-04-ingestion-pipeline-driver/spec.md) |
| Jar dependency intelligence | [Spec](specs/2026-10-04-jar-dependency-intelligence/spec.md) |
| Local source inbox | [Spec](specs/2026-10-04-local-source-inbox/spec.md) |
| Openspec change adapter | [Spec](specs/2026-10-04-openspec-change-adapter/spec.md) |
| Semantic structural chunking | [Spec](specs/2026-10-04-semantic-structural-chunking/spec.md) |
| Structured code intelligence | [Spec](specs/2026-10-04-structured-code-intelligence/spec.md) |

These product capabilities define the foundation and ingestion phases of the v0.8
Project Intelligence Platform. Subsequent phases (Storage,
Retrieval, Orchestration, Agent integration, Control plane, Security,
Distribution, A2A and quality gates) will introduce additional
accepted capabilities. Create new specs through the OpenSpec workflow
(`openspec/changes/<id>/` → `openspec/specs/YYYY-MM-DD-domain-capability/`)
and link them here when adopted.

Maintain this inventory with every accepted addition, retirement or identity
migration. Dates record first acceptance, not the latest edit. Run
`python harness.py openspec-check` to verify its completeness and naming.