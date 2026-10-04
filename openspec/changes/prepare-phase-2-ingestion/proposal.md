# Proposal — Prepare the v0.8 Phase 2 Ingestion Pipeline Capabilities

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the ingestion pipeline as the second implementation phase:
nine behavioural capabilities (`ingestion-pipeline-driver`,
`structured-code-intelligence`, `jar-dependency-intelligence`,
`document-source-adapters`, `openspec-change-adapter`,
`local-source-inbox`, `content-addressed-processing`,
`semantic-structural-chunking`, `context-enrichment`) that turn raw
sources into canonical chunks, contextualised chunks and entity/relation
candidates that the later phases (Storage, Retrieval, Orchestration)
consume.

The Phase 1 foundation shipped in `try/2026-10-04-implement-phase-1-
foundation/` is the prerequisite. The five accepted Phase 1 specs
(`project-knowledge-repository-layout`, `canonical-knowledge-schema`,
`git-version-aware-runtime`, `bidirectional-canonical-runtime-sync`,
`license-governance`) define the canonical value-type catalogue, the
deterministic serializer, the SHA-256 content address, the Git
identity layer and the license gate that Phase 2 builds on. Without
Phase 2 specs there is no authoritative behavioural contract for the
ingestion subsystem, so the next implementation change has nothing to
validate against `openspec validate` and the regression suite cannot
express Phase 2 scenarios.

This change resolves the gap by authoring the nine Phase 2 capability
specs, the supporting design, context-impact and tasks, while shipping
zero production code. The implementation work ships under a future
`implement-phase-2-ingestion` change that depends on the nine Phase 2
specs being accepted into `openspec/specs/`.

## Goal

Author the Phase 2 capability specs and change artifacts so that a
later `implement-phase-2-ingestion` change can:

- introduce `platform.ingest.PipelineDriver` and the stage boundaries
  required by §18 (parsers → chunking → enrichment →
  graph/vector/metadata → runtime store) with explicit error-handling
  and idempotency contracts per stage;
- satisfy the §3 source-coverage requirements (application code,
  tests, Maven/Gradle, JARs, source JARs, bytecode, OpenSpec, ADR,
  Markdown, HTML, PDF, office documents, `tmp/local/source/**`) via a
  uniform `SourceAdapter` port and per-family adapters;
- extract structured code intelligence (§14 — packages, classes,
  interfaces, methods, constructors, inheritance, annotations, calls,
  JPA mappings, configuration, tests) using a documented Java parser
  library whose license passes the Phase 1 license gate;
- extract JAR dependency intelligence (§15 — coordinates, versions,
  packages, classes, signatures, annotations, inherited types,
  modules, resources, source JAR content, public APIs, dependency
  relationships) plus Gradle and `pom.xml` dependency-graph extraction;
- implement the local source inbox scanner with the §9.2
  `LOCAL_ONLY` / `REFERENCE` / `SNAPSHOT` policy contract;
- implement the OpenSpec change adapter that produces
  `Requirement`, `Specification`, `OpenSpecChange` entities plus the
  `SATISFIES`, `PART_OF`, `IMPLEMENTED_BY` relations from §16;
- implement §13 content-addressed processing with SHA-256 cache reuse
  across Git branches and a property-based cross-branch reuse test
  that complements the Phase 1 round-trip test;
- implement §19/§20/§21 semantic and structural chunking with the
  parent-link contract already validated by
  `tests/test_canonical_roundtrip.py`;
- implement the §22 three-layer enrichment (deterministic + domain
  rules + optional small LLM) that never invents authoritative
  identifiers, versions, dates or security classifications.

What this change does:

- proposes the nine Phase 2 capability specs under
  `openspec/changes/prepare-phase-2-ingestion/specs/`;
- documents the technical design covering the `PipelineDriver`
  coordinator, the `SourceAdapter` port and the planned adapters, the
  chunker strategy, the `ContextEnricher` strategy, the inbox scanner
  policy contract, the OpenSpec change adapter, the Java parser
  library selection rationale and the cross-branch reuse test;
- lists the Wiki, ADR and context-impact nodes the future
  `implement-phase-2-ingestion` change will need to create or update;
- enumerates Phase 2 tasks 45–59 (mirroring
  [`plan-v0-8-platform-architecture/tasks.md`](../../changes/plan-v0-8-platform-architecture/tasks.md))
  with concrete verification commands so a contributor or AI agent can
  execute them deterministically.

Out of scope for this change:

- any production code under `pi_platform/ingest/`,
  `pi_platform/ports/ingest/`, `pi_platform/adapters/java/` (or any
  other Phase 2 module);
- any addition to the runtime dependency inventory (no Java parser
  library, no embedded DB, no vector/graph backend — those land in the
  future `implement-phase-2-ingestion` change after each SPDX-tracked
  license inventory entry passes `LicenseGate`);
- storage of the runtime DB, ANN index, sparse index, dense index,
  sparse BM25 index, full-text index, the sharded graph and the MCP
  server — those belong to Phases 3, 4 and 6 respectively;
- archiving this change. The change stays active (proposal-only) until
  the future `implement-phase-2-ingestion` change uses it as
  prerequisite. The `plan-v0-8-platform-architecture` change remains
  the authoritative source for Phase 2–10 task ordering; tasks 45–59 stay
  `[ ]`.

## Affected capabilities

This change introduces the following additive capability specs. None
of the five accepted Phase 1 specs is modified or retired; Phase 2
specs depend on the Phase 1 specs (`canonical-knowledge-schema`,
`git-version-aware-runtime`, `bidirectional-canonical-runtime-sync`,
`project-knowledge-repository-layout`, `license-governance`) but do
not alter their normative content.

| New capability | Architecture sections | Phase 2 task(s) | Spec delta path |
|---|---|---|---|
| `ingestion-pipeline-driver` | §18 | 45, 56 (partial) | [`specs/2026-10-04-ingestion-pipeline-driver/spec.md`](specs/2026-10-04-ingestion-pipeline-driver/spec.md) |
| `structured-code-intelligence` | §14 | 51, 58 (partial) | [`specs/2026-10-04-structured-code-intelligence/spec.md`](specs/2026-10-04-structured-code-intelligence/spec.md) |
| `jar-dependency-intelligence` | §15 | 52, 53, 58 (partial) | [`specs/2026-10-04-jar-dependency-intelligence/spec.md`](specs/2026-10-04-jar-dependency-intelligence/spec.md) |
| `document-source-adapters` | §3, §8.2 | 48, 58 (partial) | [`specs/2026-10-04-document-source-adapters/spec.md`](specs/2026-10-04-document-source-adapters/spec.md) |
| `openspec-change-adapter` | §53 | 50, 58 (partial) | [`specs/2026-10-04-openspec-change-adapter/spec.md`](specs/2026-10-04-openspec-change-adapter/spec.md) |
| `local-source-inbox` | §9 | 49, 56 | [`specs/2026-10-04-local-source-inbox/spec.md`](specs/2026-10-04-local-source-inbox/spec.md) |
| `content-addressed-processing` | §13 | 47, 57 | [`specs/2026-10-04-content-addressed-processing/spec.md`](specs/2026-10-04-content-addressed-processing/spec.md) |
| `semantic-structural-chunking` | §19, §20, §21 | 54, 58 (partial) | [`specs/2026-10-04-semantic-structural-chunking/spec.md`](specs/2026-10-04-semantic-structural-chunking/spec.md) |
| `context-enrichment` | §22, §54, §55 | 55, 58 (partial) | [`specs/2026-10-04-context-enrichment/spec.md`](specs/2026-10-04-context-enrichment/spec.md) |

The nine specs cover Phase 2 tasks 45–59 from
[`plan-v0-8-platform-architecture/tasks.md`](../../changes/plan-v0-8-platform-architecture/tasks.md).
Tasks 45–59 remain `[ ]` in the plan change after this change is
archived; they will be flipped to `[x]` by the future
`implement-phase-2-ingestion` change when it lands.

Cross-phase task responsibility:

- the §18 PipelineDriver integration glue (task 45) is owned by Phase 2;
- the §13 content-addressed processing storage layer (Phase 3 task 62
  — `RuntimeStore`) and the §61 embedded storage engine selection
  belong to Phase 3; Phase 2 specs only contract the runtime DB write
  boundary, the cache key (SHA-256) and the cross-branch reuse
  semantics, not the database implementation;
- the MCP server exposing Phase 2 entities/relations (Phase 6 task 85)
  belongs to Phase 6;
- the OkfAdapter materialization of Phase 2 entities into Wiki concept
  pages (Phase 9 task 112) belongs to Phase 9.

Naming and adoption conventions (per
[`openspec/config.yaml`](../../config.yaml) and
[`openspec/README.md`](../../README.md)):

- active change IDs are undated semantic kebab-case
  (`prepare-phase-2-ingestion`);
- delta folders under `specs/` use the future first-acceptance date
  (`2026-10-04-<capability>`);
- `openspec/CURRENT.md` is updated by the future
  `implement-phase-2-ingestion` change when the nine Phase 2 specs are
  adopted, not by this change.

## Compatibility / migration impact

This change is a pure planning artifact. It adds:

- one new active change directory at
  `openspec/changes/prepare-phase-2-ingestion/`;
- nine new spec deltas under
  `openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-*/`.

It does not:

- modify any accepted Phase 1 capability spec under
  `openspec/specs/2026-10-04-*/`;
- modify `openspec/CURRENT.md`, the harness, the license inventory or
  the regression suite;
- introduce any source code, dependency or runtime configuration;
- rename any existing capability, port or adapter;
- alter the `plan-v0-8-platform-architecture` change
  (`tasks.md` still lists tasks 45–59 as `[ ]`).

Language and dependency decisions:

- the Python 3.11 platform source language decision recorded in
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  still holds. No new language dependency is being introduced by this
  change. The future `implement-phase-2-ingestion` change MAY add one
  Java parser library (e.g. `tree-sitter-java` under Apache-2.0, or
  `javalang` under MIT) and MAY invoke it as an out-of-process
  subprocess from a Python adapter — but only after an SPDX-tracked
  license inventory entry passes `LicenseGate`. The Python-only
  default ports in `pi_platform/ports/` stay language-neutral;
  Java-specific parsing is supplied as an adapter under
  `pi_platform/adapters/java/` so no port acquires a Java-runtime
  dependency.
- no change to the licence-governance defaults. Any new dependency
  must be SPDX-tracked and pass `LicenseGate` before it lands in
  `distribution/licenses/dependency-inventory.json`. The `tree-sitter-
  java` and `javalang` candidates are documented as review-required
  paths in the `design.md` so the future ADR
  (`adr.phase-2-parser-selection`) carries the documented rationale.

OpenSpec CLI conventions:

- the change folder uses lowercase kebab-case without a date prefix
  (`prepare-phase-2-ingestion`) per
  [`openspec/config.yaml`](../../config.yaml);
- the nine spec deltas are dated with the future acceptance date
  `2026-10-04` matching the Phase 1 archive convention; the archive
  step for the future `implement-phase-2-ingestion` change will produce
  `archive/2026-10-04-implement-phase-2-ingestion/` and rename the
  delta folders to drop the date prefix in the change-root view;
- no production code, license inventory entry or harness command is
  touched.

## Related knowledge

- `kb://architecture.platform-overview` — Phase 1 Wiki node; will be
  updated by the future `implement-phase-2-ingestion` change to add
  the Phase 2 module map (`ingest/`, `ports/ingest/`,
  `adapters/<content-type>/`).
- `kb://architecture.system-overview` — cross-cutting view; will gain
  a Phase 2 module map row.
- `kb://glossary.platform` — Phase 1 platform vocabulary; the future
  change adds `PipelineDriver`, `SourceAdapter`, `LocalSourceInbox
  Scanner`, `ContextEnricher`, `SourcePromotionPolicy`.
- `kb://glossary.domain` — cross-links to the platform vocabulary.
- `kb://project.implementation-roadmap` — links to Phase 2 entry.
- `kb://project.project-map` — Phase 2 module map placeholder.
- `kb://adr.platform-source-language` — Python 3.11 holds; Java
  adapter stays under `pi_platform/adapters/java/`.
- `kb://adr.canonical-runtime-separation` — Phase 2 specs respect
  invariants #1-#4 and the canonical/runtime boundary.
- `kb://adr.license-governance-default` — every Phase 2 dependency
  requires an SPDX-tracked inventory entry.
- future `kb://adr.phase-2-parser-selection` — Java parser library
  selection (the design candidate is `tree-sitter-java` Apache-2.0
  invoked as an out-of-process subprocess).
- future `kb://adr.phase-2-inbox-policy-default` — locks the inbox
  default policy to `LOCAL_ONLY` if the future
  `implement-phase-2-ingestion` change decides to do so.
- future `kb://modules.ingest` and `kb://interfaces.source-adapters`,
  `kb://interfaces.chunker`, `kb://interfaces.enrichment` Wiki
  modules/interfaces documented in [`context-impact.md`](context-impact.md).
- external: `project-intelligence-platform-architecture-v0.8.md`
  §3, §8.2, §9.1-#22, §53, §54, §55, §66 — every cited section is
  authoritative for the Phase 2 capability contracts.