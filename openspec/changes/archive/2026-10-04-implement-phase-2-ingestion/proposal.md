# Proposal — Implement Phase 2 Ingestion Pipeline

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the ingestion subsystem in §3, §8.2, §9, §13–§22, §53–§55.
Nine Phase 2 capability specs are now proposed under
[`openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-*/`](../../changes/prepare-phase-2-ingestion/specs/)
and `openspec validate prepare-phase-2-ingestion --type change --strict`
returns `valid`. The five accepted Phase 1 capability specs
(`project-knowledge-repository-layout`, `canonical-knowledge-schema`,
`git-version-aware-runtime`, `bidirectional-canonical-runtime-sync`,
`license-governance`) supply the deterministic value-type catalogue,
the SHA-256 content address, the Git-version-aware runtime and the
license gate that Phase 2 builds on, but the repository still ships
zero production code under `pi_platform/ingest/`,
`pi_platform/ports/ingest/`, `pi_platform/adapters/ingest/`,
`pi_platform/adapters/java/`, `pi_platform/adapters/openspec/`,
`pi_platform/adapters/markdown/`, `pi_platform/adapters/html/`,
`pi_platform/adapters/pdf/`, or `pi_platform/adapters/openapi/`.
There is therefore no `PipelineDriver`, no `SourceAdapter`, no
`Chunker`, no `ContextEnricher`, no `LocalSourceInboxScanner`, no
`OpenSpecChangeAdapter`, no Java structured-code intelligence, no
JAR / Maven / Gradle dependency intelligence, and no SHA-256
cross-branch reuse test. The runtime has no way to turn a raw
source into canonical chunks and `ContextualChunk` records, the
license inventory has no entry for the documented Java parser
library, and `python -m pi_platform.cli` cannot ingest any source
end-to-end.

This change resolves the gap by implementing the Phase 2 production
code per the nine accepted specs, the per-scenario regression
suite (`tests/test_platform_phase2.py`), the property-based
cross-branch reuse test (`tests/test_content_address_cross_branch.py`),
the new `ingest-sources` CLI subcommand, the new
`distribution/licenses/dependency-inventory.json` entries (only for
dependencies whose SPDX identifier is recorded and that pass
`LicenseGate`), the Phase 2 Wiki nodes, the parser-selection and
inbox-policy ADRs and the
`openspec/CURRENT.md` adoption of the nine new capabilities. After
this change is archived, the Phase 2 spec deltas are promoted to
`openspec/specs/2026-10-04-*/`, the planning-change tasks 45-60 are
flipped to `[x]`, and the Phase 1 round-trip invariant
(`tests/test_canonical_roundtrip.py`) remains green byte-for-byte.

## Goal

Ship the Phase 2 production code per the nine accepted capability
specs in
[`prepare-phase-2-ingestion/specs/`](../../changes/prepare-phase-2-ingestion/specs/),
land the per-scenario regression suite and the cross-branch reuse
property test, add the new `ingest-sources` CLI subcommand, and
archive the change so the nine Phase 2 capability specs are adopted
into `openspec/specs/2026-10-04-*/` and listed in `openspec/CURRENT.md`.

What this change ships:

- the additive ports under `pi_platform/ports/ingest/`
  (`pipeline_driver`, `source_adapter`, `chunker`, `context_enricher`,
  `java_parser`, `local_source_inbox_scanner`);
- the core implementations under `pi_platform/core/ingest/`
  (`pipeline_driver`, `local_source_inbox_scanner`);
- the default adapters under `pi_platform/adapters/ingest/`
  (`local_pipeline_driver`, `markdown_chunker`, `html_chunker`,
  `plain_text_chunker`, `layered_context_enricher`);
- the per-family adapters under
  `pi_platform/adapters/{fs,markdown,html,pdf,openapi,java,openspec}/`,
  including the out-of-process `tree-sitter-java` subprocess owned
  by `pi_platform/adapters/java/parser_subprocess.py`;
- the SPDX-tracked `dependency-inventory.json` entries for the
  Java parser library (the design candidate is `tree-sitter-java`
  Apache-2.0 invoked out-of-process; PDF and OpenAPI adapters stay
  optional and are skipped unless their dependencies are added to
  the inventory with an SPDX identifier);
- the new regression suites
  (`tests/test_platform_phase2.py`,
  `tests/test_content_address_cross_branch.py`) and the
  `ingest-sources` CLI subcommand;
- the new Wiki nodes, the parser-selection and inbox-policy ADRs,
  the `openspec/CURRENT.md` adoption row for the nine Phase 2
  capabilities, and the flip of plan-change tasks 45–60 from `[ ]`
  to `[x]`.

Out of scope for this change (future phases):

- the runtime DB (Phase 3 task 62 `RuntimeStore`);
- the sharded knowledge graph (Phase 3 task 66);
- the dense ANN index (Phase 4 task 71);
- the reranker (Phase 4 task 74);
- the local LLM port (Phase 5 task 80);
- the MCP server that exposes Phase 2 entities (Phase 6 task 85);
- the OKF Wiki materialisation (Phase 9 task 112).

Phase 2 only contracts the cache key (SHA-256), the cross-branch
reuse semantics, and the port surfaces. Phase 3 owns the
implementation of `RuntimeStore` and `Graph`.

## Affected capabilities

This change implements the nine Phase 2 capability specs in
[`prepare-phase-2-ingestion/specs/2026-10-04-*/`](../../changes/prepare-phase-2-ingestion/specs/)
and lists them in `openspec/CURRENT.md` on archive. No accepted
Phase 1 capability spec is modified or retired; the five Phase 1
specs are unchanged and continue to pass strict validation.

| Capability | Architecture sections | Phase 2 task(s) | Spec delta path |
|---|---|---|---|
| `ingestion-pipeline-driver` | §18 | 45, 56 | [`2026-10-04-ingestion-pipeline-driver/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-ingestion-pipeline-driver/spec.md) |
| `structured-code-intelligence` | §14 | 51, 58 | [`2026-10-04-structured-code-intelligence/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-structured-code-intelligence/spec.md) |
| `jar-dependency-intelligence` | §15 | 52, 53, 58 | [`2026-10-04-jar-dependency-intelligence/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-jar-dependency-intelligence/spec.md) |
| `document-source-adapters` | §3, §8.2 | 48, 58 | [`2026-10-04-document-source-adapters/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-document-source-adapters/spec.md) |
| `openspec-change-adapter` | §53 | 50, 58 | [`2026-10-04-openspec-change-adapter/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-openspec-change-adapter/spec.md) |
| `local-source-inbox` | §9, §9.2 | 49, 56 | [`2026-10-04-local-source-inbox/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-local-source-inbox/spec.md) |
| `content-addressed-processing` | §13 | 47, 57 | [`2026-10-04-content-addressed-processing/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-content-addressed-processing/spec.md) |
| `semantic-structural-chunking` | §19, §20, §21 | 54, 58 | [`2026-10-04-semantic-structural-chunking/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-semantic-structural-chunking/spec.md) |
| `context-enrichment` | §22, §54, §55 | 55, 58 | [`2026-10-04-context-enrichment/spec.md`](../../changes/prepare-phase-2-ingestion/specs/2026-10-04-context-enrichment/spec.md) |

Cross-phase task responsibility (boundary with later phases):

- the `RuntimeStore` (Phase 3 task 62), the `Graph` (Phase 3 task
  66) and the `SparseIndex` / `DenseIndex` / `FullTextIndex`
  (Phase 3 tasks 63-65) are out of scope. Phase 2 emits the
  content-addressed records and writes them through the Phase 3
  `RuntimeStorePort` interface that already exists in the Phase 1
  surface (or its documented placeholder);
- the MCP server that exposes the entities (Phase 6 task 85) is
  out of scope. Phase 2 produces the entity catalogue; the MCP
  server is Phase 6;
- the Wiki materialisation (Phase 9 task 112) is out of scope.
  Phase 2 only updates the canonical Wiki pages and
  `openspec/CURRENT.md`; the OKF Wiki materialisation is Phase 9.

## Compatibility / migration impact

This change is additive at every public contract surface. No
accepted Phase 1 capability spec is modified. No Phase 1 value type
(`Chunk`, `ContextualChunk`, `Entity`, `Relation`, `Evidence`,
`Metadata`, `Source`, `ProjectVersion`, `WorkingTreeOverlay`) is
modified; the Phase 1 round-trip invariant
`tests/test_canonical_roundtrip.py` MUST continue to pass byte-for-
byte after this change lands. The Phase 1 CLI subcommands
(`init-project`, `hydrate`, `materialise`, `license-gate`,
`okf-validate`, `version-identity`, `wal-recover`, `health`) are
unchanged; this change adds exactly one new subcommand,
`ingest-sources`, and does not modify the existing ones.

New dependencies:

- one Java parser library enters the inventory
  (`tree-sitter-java` MIT, out-of-process subprocess), gated
  on a documented SPDX identifier in
  `distribution/licenses/dependency-inventory.json` and a green
  Phase 1 `license-gate` run before the adapter is registered;
- optional PDF / OpenAPI libraries (`pdfplumber` MIT or `pypdf`
  BSD-3-Clause; `openapi-schema-validator` Apache-2.0 or `prance`
  BSD-3-Clause) are added only if the corresponding adapter
  ships in this change and its dependency passes `LicenseGate`. PDF
  and OpenAPI adapters are not part of the nine Phase 2 specs, so
  they are out of scope and their dependencies do NOT land in this
  change. The adapter file paths
  (`pi_platform/adapters/pdf/`, `pi_platform/adapters/openapi/`) are
  documented in `design.md` as planned Phase 2+ slots and are not
  populated by this change;
- the Python 3.11 platform source language decision recorded in
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  still holds. No new platform-level language dependency is
  introduced; the Java parser library is invoked as an out-of-
  process subprocess from a Python adapter.

OpenSpec conventions:

- the change folder uses lowercase kebab-case without a date
  prefix (`implement-phase-2-ingestion`);
- the nine Phase 2 spec deltas remain under
  `openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-*/`
  until the archive step moves them to
  `openspec/specs/2026-10-04-*/` and renames the change folder to
  `openspec/changes/archive/2026-10-04-prepare-phase-2-ingestion/`
  per the OpenSpec experimental workflow;
- the archive step archives this implementation change to
  `openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`;
- `openspec/CURRENT.md` is updated to list the nine Phase 2
  capabilities under "Project product capabilities" once the
  archive promotes the deltas.

## Related knowledge

- `kb://architecture.platform-overview` — extended with the Phase 2
  module map (`pi_platform/core/ingest/`,
  `pi_platform/ports/ingest/`, `pi_platform/adapters/ingest/`,
  `pi_platform/adapters/java/`, `pi_platform/adapters/openspec/`,
  `pi_platform/adapters/markdown/`, `pi_platform/adapters/html/`).
- `kb://architecture.system-overview` — extended with the Phase 2
  ingestion pipeline reference.
- `kb://glossary.platform` — extended with `PipelineDriver`,
  `SourceAdapter`, `Chunker`, `ContextEnricher`,
  `LocalSourceInboxScanner`, `SourcePromotionPolicy`
  (`LOCAL_ONLY`, `REFERENCE`, `SNAPSHOT`), `ContentAddress`
  (cross-branch reuse), `JavaParserSubprocess`.
- `kb://glossary.domain` — cross-linked to the platform vocabulary.
- `kb://project.implementation-roadmap` — Phase 2 row flipped from
  `planned` to `complete` on archive.
- `kb://project.project-map` — Phase 2 module folders added under
  "Main source areas".
- `kb://modules.ingest` — new Wiki module map (Phase 2 surface).
- `kb://interfaces.source-adapters`,
  `kb://interfaces.chunker`, `kb://interfaces.enrichment` — new
  Wiki interface nodes.
- `kb://adr.phase-2-parser-selection` — new ADR recording the
  `tree-sitter-java` MIT out-of-process subprocess choice
  and the rejected alternatives (`javalang` MIT,
  `javaparser` Apache-2.0, native `javap`/`jdeps`).
- `kb://adr.phase-2-inbox-policy-default` — new ADR locking the
  default inbox policy to `LOCAL_ONLY` and the override
  resolution rule (longest matching glob wins; ties broken by sort
  ascending).
- `kb://adr.platform-source-language` — unchanged; the Phase 2
  Java parser is an out-of-process subprocess from a Python
  adapter, not a new platform-level language dependency.
- `kb://adr.canonical-runtime-separation` — unchanged; the Phase 2
  pipeline respects invariants #1-#4.
- `kb://adr.license-governance-default` — every new dependency
  has an SPDX identifier in
  `distribution/licenses/dependency-inventory.json` and passes
  `LicenseGate` before the adapter is registered.