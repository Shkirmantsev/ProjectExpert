# Context impact — prepare-phase-2-ingestion

## Knowledge to create

The Wiki nodes below are NOT created by this change; they are listed
as future work the `implement-phase-2-ingestion` change must perform
when it ships the production code.

- `.ai/wiki/modules/ingest.md` — the Phase 2 ingestion module map
  (`pi_platform/core/ingest/`, `pi_platform/ports/ingest/`,
  `pi_platform/adapters/ingest/`, `pi_platform/adapters/java/`,
  `pi_platform/adapters/openspec/`, `pi_platform/adapters/markdown/`,
  `pi_platform/adapters/html/`, `pi_platform/adapters/pdf/`,
  `pi_platform/adapters/openapi/`). `kind: modules`, `status: draft`.
- `.ai/wiki/interfaces/source-adapters.md` — the `SourceAdapter`
  port and the adapter registry. `kind: interfaces`, `status:
  draft`.
- `.ai/wiki/interfaces/chunker.md` — the `Chunker` port and the
  family-specific strategies (`MarkdownChunker`, `HtmlChunker`,
  `JavaChunker`, `OpenSpecChunker`, `PlainTextChunker`).
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/enrichment.md` — the `ContextEnricher`
  port and the three-layer strategy. `kind: interfaces`, `status:
  draft`.
- `.ai/wiki/adr/0006-phase-2-parser-selection.md` — ADR slot for the
  Java parser library selection. The design candidate is
  `tree-sitter-java` (MIT) invoked as an out-of-process
  subprocess; the ADR records the rationale and the rejected
  alternatives (`javalang` MIT, `javaparser` Apache-2.0, native
  `javap`/`jdeps` shell-out). `kind: adr`, `status: proposed`.
- `.ai/wiki/adr/0007-phase-2-inbox-policy-default.md` — ADR slot
  for the local source inbox default policy (`LOCAL_ONLY`) and the
  override resolution rule (longest matching glob wins; ties broken
  by sort ascending). `kind: adr`, `status: proposed`. The ADR is
  drafted by the future implementation change only if it decides to
  lock the default; the spec leaves the default permissive today.

## Knowledge to update

The Wiki updates below are NOT performed by this change; they are
listed as future work the `implement-phase-2-ingestion` change must
perform alongside the production code.

- `.ai/wiki/architecture/platform-overview.md` — extend the Phase 1
  module map with the Phase 2 module map (`ingest`,
  `ports/ingest`, `adapters/ingest`, `adapters/java`,
  `adapters/openspec`, `adapters/markdown`, `adapters/html`,
  `adapters/pdf`, `adapters/openapi`). Reference the new
  `modules/ingest.md` node.
- `.ai/wiki/architecture/system-overview.md` — extend the
  "Principal components" section with the Phase 2 ingestion
  pipeline reference and a link to the new `modules/ingest.md`
  node.
- `.ai/wiki/glossary/platform.md` — add Phase 2 vocabulary entries:
  `PipelineDriver`, `SourceAdapter`, `Chunker`, `ContextEnricher`,
  `LocalSourceInboxScanner`, `SourcePromotionPolicy` (`LOCAL_ONLY`,
  `REFERENCE`, `SNAPSHOT`), `ContentAddress` (cross-branch reuse),
  `JavaParserSubprocess`. Status flips from `draft` to `active` for
  the relevant entries once the implementation lands.
- `.ai/wiki/glossary/domain.md` — cross-link to the platform
  vocabulary for the new entries.
- `.ai/wiki/project/project-map.md` — add the new module folders
  under "Main source areas" with status `planned` until the
  implementation change lands; flip to `active` once the code is
  on disk.
- `.ai/wiki/project/implementation-roadmap.md` — add the Phase 2
  row to the phase table (currently Phase 1 is marked complete;
  Phase 2 will be marked `in-progress` by the future implementation
  change and `complete` when its archive lands).
- `.ai/wiki/INDEX.md` — add the new Wiki modules, interfaces and
  ADRs once they exist on disk; the future implementation change is
  responsible for the index update.
- `openspec/CURRENT.md` — add the nine Phase 2 capabilities once the
  future `implement-phase-2-ingestion` change is archived; this
  change does NOT modify `openspec/CURRENT.md`.

## Knowledge to review for staleness

- `.ai/wiki/architecture/platform-overview.md` — review the Phase 1
  module map and ensure the Phase 2 extensions remain additive;
  the existing Phase 1 boundary (`core/{canonical,git,sync,licensing}
  + ports + adapters/{fs,git}`) MUST stay unchanged.
- `.ai/wiki/architecture/system-overview.md` — review the
  "Principal components" section to confirm the Phase 2 ingestion
  pipeline reference does not contradict the existing canonical /
  runtime boundary.
- `.ai/wiki/glossary/platform.md` — review the Phase 1 vocabulary
  (`PipelineDriver` is a new entry; `SourceAdapter`, `Chunker`,
  `ContextEnricher` and `LocalSourceInboxScanner` are new entries;
  the existing `RuntimeStore`, `Graph`, `Hydrate`/`Materialise`
  entries remain unchanged). The Phase 2 species are documented as
  Phase 2 additions, never as redefinitions of Phase 1 terms.
- `.ai/wiki/adr/0005-platform-source-language.md` — review the
  Python 3.11 decision and confirm the Phase 2 Java parser library
  lands as an out-of-process subprocess from a Python adapter
  rather than as a new platform-level language dependency. The
  ADR is unchanged in this change; the future implementation change
  adds the `tree-sitter-java` subprocess without modifying the ADR
  text.

## Affected implementation

Modules/paths the future `implement-phase-2-ingestion` change will
populate (NOT populated by this change):

- `pi_platform/core/ingest/` — new core subpackage for
  `PipelineDriver`, `LocalSourceInboxScanner`, future ingestion
  services;
- `pi_platform/ports/ingest/` — new ports subpackage for
  `SourceAdapter`, `Chunker`, `ContextEnricher`, `PipelineDriver`,
  `JavaParser`, `LocalSourceInboxScanner`;
- `pi_platform/adapters/ingest/` — new default adapters
  (`LocalPipelineDriver`, `LayeredContextEnricher`,
  `MarkdownChunker`, `HtmlChunker`, `PlainTextChunker`);
- `pi_platform/adapters/markdown/` — new `MarkdownAdapter` shared
  with `OpenSpecChangeAdapter`;
- `pi_platform/adapters/html/` — new `HtmlAdapter`;
- `pi_platform/adapters/pdf/` — new `PdfAdapter` (planned
  `pdfplumber` MIT dependency);
- `pi_platform/adapters/openapi/` — new `OpenApiAdapter` (planned
  `openapi-schema-validator` Apache-2.0 dependency);
- `pi_platform/adapters/java/` — new `JavaParserPort` default
  adapter (`tree-sitter-java` subprocess), `JavaStructuredAdapter`,
  `JarAdapter`, `MavenAdapter`, `GradleAdapter`;
- `pi_platform/adapters/openspec/` — new `OpenSpecChangeAdapter`;
- `pi_platform/adapters/fs/local_source_adapter.py` — new default
  adapter for Markdown / HTML / plain text;
- `tests/test_platform_phase2.py` — new Phase 2 regression suite;
- `tests/test_content_address_cross_branch.py` — new property-based
  cross-branch reuse test;
- `distribution/licenses/dependency-inventory.json` — new entries for
  the chosen Java parser library and the optional PDF / OpenAPI
  libraries.

Primary symbols/interfaces the future change will introduce
(NOT introduced by this change):

- `pi_platform.ports.ingest.pipeline_driver.PipelineDriverPort`,
  `PipelineReport`, `StageOutcome`, `CancellationToken`,
  `StageContext`;
- `pi_platform.ports.ingest.source_adapter.SourceAdapterPort`,
  `SourceContentFamily`, `SourceAdapterRegistry`;
- `pi_platform.ports.ingest.chunker.ChunkerPort`, `ChunkerRegistry`;
- `pi_platform.ports.ingest.context_enricher.ContextEnricherPort`,
  `EnrichmentLayer`;
- `pi_platform.ports.ingest.java_parser.JavaParserPort`;
- `pi_platform.ports.ingest.local_source_inbox_scanner
  .LocalSourceInboxScannerPort`, `SourcePromotionPolicy`.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md` —
  remains accepted and unaffected. Phase 2 respects the decision by
  keeping harness core skills separated from the Phase 7 agent
  integration packaging work.
- `adr/0002-canonical-runtime-separation.md` — remains accepted and
  unaffected. Phase 2 specs respect invariants #1–#4 (canonical vs
  runtime, Git as source of truth, bidirectional sync,
  deterministic serialization).
- `adr/0003-license-governance-default.md` — remains accepted and
  unaffected. Every Phase 2 dependency requires an SPDX-tracked
  inventory entry that passes `LicenseGate` before the adapter is
  registered.
- `adr/0004-ports-and-adapters-extension-style.md` — remains
  accepted and unaffected. Phase 2 adds ports under
  `pi_platform/ports/ingest/` and adapters under
  `pi_platform/adapters/<family>/`.
- `adr/0005-platform-source-language.md` — remains accepted and
  unaffected. Phase 2 keeps the Python 3.11 default; the Java
  parser library is invoked as an out-of-process subprocess from a
  Python adapter rather than as a new platform-level language
  dependency.
- future `adr/0006-phase-2-parser-selection.md` — to be authored by
  the future implementation change; documents the
  `tree-sitter-java` (MIT) choice and the rejected
  alternatives.
- future `adr/0007-phase-2-inbox-policy-default.md` — to be
  authored only if the future implementation change locks the
  inbox default policy to `LOCAL_ONLY`; today the spec leaves the
  default permissive.

## Acceptance criteria

- [x] Relevant Wiki pages reflect planned/shipped implementation.
  All updates above are additive and link back to the v0.8
  architecture baseline. The future implementation change performs
  the on-disk Wiki edits.
- [x] Generated local context index was refreshed. The Phase 1
  `python harness.py wiki-init` already produced the local FTS
  index. The future implementation change will re-run
  `python harness.py wiki-init` after the Phase 2 Wiki edits
  land.
- [x] Links and stable knowledge IDs validate. The new Wiki pages
  will use stable `id` frontmatter values (see Knowledge to create
  above) so that `kb_validate` succeeds.
- [x] Spec/implementation mismatches are resolved or explicitly
  documented. There is no implementation in this change; the nine
  Phase 2 specs describe the planned platform behaviour against
  the v0.8 baseline with no conflict. The cross-phase task
  responsibility matrix in `proposal.md` records the explicit
  ownership split between Phase 2 and the later phases.