# openspec-change-adapter Specification delta

Covers architecture section §53 (OpenSpec Integration). Reads
`openspec/specs/` and `openspec/changes/` and produces the
`Requirement`, `Specification`, `OpenSpecChange`, `Architecture
Decision` (ADR) and `Component` entities plus the
`SATISFIES`/`PART_OF`/`IMPLEMENTED_BY`/`DOCUMENTED_BY` relations that
the Phase 3 knowledge graph depends on.

The Phase 1 `canonical-knowledge-schema` capability provides the
entity/relation value types and the deterministic serializer; the
Phase 1 `document-source-adapters` capability provides the
`SourceAdapter` port that the OpenSpec adapter implements; the
`MarkdownAdapter` referenced from `document-source-adapters` is
reused to avoid duplication.

## ADDED Requirements

### Requirement: OpenSpecChangeAdapter

The platform MUST expose an `OpenSpecChangeAdapter` that implements
the `SourceAdapter` port and produces:

- one `OpenSpecChange` entity per change directory under
  `openspec/changes/` whose `id` matches the directory name (excluding
  the `archive/` subtree);
- one `Requirement` entity per `## Requirement` block in a spec
  delta, with attributes `openspecId`, `name`, `capabilityId`,
  `phase` (`current` | `proposed`) and `description`;
- one `Specification` entity per spec delta folder under
  `openspec/specs/` and per spec delta folder under
  `openspec/changes/<id>/specs/`, with attributes `openspecId`,
  `capabilityId`, `phase`, `status` (`draft` | `active` |
  `archived`) and the spec's YAML frontmatter if present;
- one `ArchitectureDecision` entity per ADR Markdown file under
  `openspec/changes/<id>/specs/` when the spec delta folder contains
  an ADR-style document (detected by the documented frontmatter shape);
- one `Component` entity per top-level platform module referenced by
  a spec delta (the module is named in the spec's "Phase 2 task
  coverage" or "Affected modules" section when present);
- `SATISFIES` relations from each `Specification` to the
  `Requirement`s it describes;
- `PART_OF` relations from each `Requirement` to its enclosing
  `OpenSpecChange` (or to the `Capability` entity derived from the
  capability folder);
- `IMPLEMENTED_BY` relations from each `Specification` to the
  `Component`s the future implementation change will populate
  (the component names are sourced from the spec's task coverage
  section, which is documentation-only and is never consulted as
  authoritative input to other rules per the v0.8 §22.3 contract);
- `DOCUMENTED_BY` relations from each `Component` to the ADRs that
  govern it.

#### Scenario: adapter emits OpenSpecChange entities

Given a change directory `openspec/changes/prepare-phase-2-ingestion`
with `proposal.md`, `design.md`, `tasks.md`, `context-impact.md` and
nine spec deltas under `specs/`
When the `OpenSpecChangeAdapter` is invoked
Then the adapter emits one `OpenSpecChange` entity with
`id="prepare-phase-2-ingestion"`
And the adapter emits one `Specification` entity per delta folder
under `specs/`
And the adapter emits `SATISFIES` relations from each
`Specification` to its `Requirement` entities
And the adapter emits `PART_OF` relations from each `Requirement`
to the `OpenSpecChange`
And the adapter emits `IMPLEMENTED_BY` relations from each
`Specification` to the `Component` entities referenced in the
spec's "Phase 2 task coverage" section.

#### Scenario: adapter reuses MarkdownAdapter

Given a `Source` whose `uri` is a Markdown file under
`openspec/specs/` or `openspec/changes/`
When the `OpenSpecChangeAdapter` parses the file
Then the adapter invokes the shared `MarkdownAdapter` documented in
`document-source-adapters` to produce the `Section` records
And the adapter does not duplicate the Markdown parser logic.

### Requirement: archived change handling

The adapter MUST skip the `archive/` subtree of `openspec/changes/`
when emitting `OpenSpecChange` entities so archived changes are not
re-introduced as proposed behavior. Archived changes MAY still
appear as `Specification` entities with `status="archived"` so the
Wiki can link to the historical spec.

#### Scenario: archived changes are skipped from active list

Given an archived change under
`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`
with the five Phase 1 spec deltas
When the `OpenSpecChangeAdapter` lists active changes
Then the archived change is excluded from the active `OpenSpecChange`
list
And the archived spec deltas appear with `status="archived"`.

### Requirement: spec YAML frontmatter

The adapter MUST parse the YAML frontmatter of every Markdown file
under `openspec/specs/` and `openspec/changes/` and surface the
declared capability name, kind (`spec` | `change` | `adr`) and phase
in the resulting entities. Fields whose key starts with the
documented `pi_` prefix MUST be preserved as `pi_`-prefixed
extensions on the entity metadata, mirroring the `OkfAdapter`
behaviour.

#### Scenario: frontmatter drives entity attributes

Given a spec file whose YAML frontmatter declares
`capability: ingestion-pipeline-driver`, `phase: 2`,
`kind: spec`, `pi_phase_planning_token: prepare-phase-2-ingestion`
When the adapter parses the file
Then the resulting `Specification` entity carries
`capabilityId="ingestion-pipeline-driver"` and `phase=2`
And the entity's `metadata` includes the `pi_phase_planning_token`
extension field unchanged.

### Requirement: traceability chain

The adapter MUST emit the §53 traceability chain
`Business Requirement → OpenSpec Change → Specification → Architecture
Decision → Component → Implementation → Test` so that downstream
consumers can reconstruct the chain from the entities alone. When
the implementation or test nodes are not yet present (a spec delta
in `openspec/changes/`), the adapter MUST emit a
`KnowledgeState.ASSUMPTION` entity naming the missing node and link it
via a `PENDING` relation so the gap is visible.

#### Scenario: pending implementation is flagged

Given a `Specification` entity whose spec delta lists Phase 2 task
45 as the implementation task
And the implementation change `implement-phase-2-ingestion` is not
yet archived
When the adapter builds the traceability chain
Then the adapter emits a `PendingImplementation` entity with
`KnowledgeState.ASSUMPTION`
And links the `Specification` to the pending entity by a `PENDING`
relation
And the operational log records the missing implementation change id.

## Phase 2 task coverage

The change lists Phase 2 task 50 (OpenSpec adapter) and the
`openspec-change-adapter` slice of task 58 (Phase 2 spec scenarios)
and task 59 (focused regression tests).

Out of scope:

- the Wiki materialisation of the entities (Phase 9 task 112);
- the MCP server exposing `project.find_implementation`,
  `project.trace_requirement`, `project.find_references` (Phase 6
  task 85);
- the YAML frontmatter validation work — the adapter reuses the
  Phase 1 OKF v0.2 frontmatter contract and does not duplicate the
  `OkfAdapter` logic.