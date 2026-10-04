# Context impact — implement-phase-2-ingestion

## Knowledge to create

This change creates the following Wiki nodes on disk:

- `.ai/wiki/modules/ingest.md` — the Phase 2 ingestion module map
  (`pi_platform/core/ingest/`, `pi_platform/ports/ingest/`,
  `pi_platform/adapters/ingest/`, `pi_platform/adapters/java/`,
  `pi_platform/adapters/openspec/`, `pi_platform/adapters/markdown/`,
  `pi_platform/adapters/html/`, plus the planned PDF and OpenAPI
  slots). `kind: modules`, `status: active`.
- `.ai/wiki/interfaces/source-adapters.md` — the `SourceAdapter`
  port and the `SourceAdapterRegistry`. `kind: interfaces`,
  `status: active`.
- `.ai/wiki/interfaces/chunker.md` — the `Chunker` port and the
  family-specific strategies (`MarkdownChunker`, `HtmlChunker`,
  `PlainTextChunker`, `JavaChunker` delegated to
  `JavaStructuredAdapter`, `OpenSpecChunker` delegated to
  `OpenSpecChangeAdapter`). `kind: interfaces`, `status: active`.
- `.ai/wiki/interfaces/enrichment.md` — the `ContextEnricher` port
  and the three-layer strategy. `kind: interfaces`, `status: active`.
- `.ai/wiki/adr/0006-phase-2-parser-selection.md` — ADR recording
  the Java parser library selection. The design candidate is
  `tree-sitter-java` (MIT) invoked as an out-of-process
  subprocess from `pi_platform/adapters/java/parser_subprocess.py`;
  the ADR records the rationale and the rejected alternatives
  (`javalang` MIT, `javaparser` Apache-2.0, native
  `javap`/`jdeps` shell-out). `kind: adr`, `status: accepted`.
- `.ai/wiki/adr/0007-phase-2-inbox-policy-default.md` — ADR
  locking the local source inbox default policy to `LOCAL_ONLY`
  and the override resolution rule (longest matching glob wins;
  ties broken by sort ascending by glob string). `kind: adr`,
  `status: accepted`.

## Knowledge to update

The Wiki updates performed by this change:

- `.ai/wiki/architecture/platform-overview.md` — extend the Phase 1
  module map with the Phase 2 module map (`ingest`,
  `ports/ingest`, `adapters/ingest`, `adapters/java`,
  `adapters/openspec`, `adapters/markdown`, `adapters/html`,
  plus the planned `adapters/pdf` and `adapters/openapi` slots).
  Reference the new `modules/ingest.md` node.
- `.ai/wiki/architecture/system-overview.md` — extend the
  "Principal components" section with the Phase 2 ingestion
  pipeline reference and a link to the new `modules/ingest.md`
  node.
- `.ai/wiki/glossary/platform.md` — add Phase 2 vocabulary entries:
  `PipelineDriver`, `SourceAdapter`, `Chunker`, `ContextEnricher`,
  `LocalSourceInboxScanner`, `SourcePromotionPolicy` (`LOCAL_ONLY`,
  `REFERENCE`, `SNAPSHOT`), `ContentAddress` (cross-branch reuse),
  `JavaParserSubprocess`. Status is `active`.
- `.ai/wiki/glossary/domain.md` — cross-link to the platform
  vocabulary for the new entries.
- `.ai/wiki/project/project-map.md` — add the new module folders
  under "Main source areas" with status `active`.
- `.ai/wiki/project/implementation-roadmap.md` — flip the Phase 2
  row from `planned` to `complete` once the archive lands.
- `.ai/wiki/INDEX.md` — add the new Wiki modules, interfaces and
  ADRs.
- `openspec/CURRENT.md` — add the nine Phase 2 capabilities under
  "Project product capabilities" once the archive promotes the
  deltas to `openspec/specs/2026-10-04-*/`.
- `openspec/changes/plan-v0-8-platform-architecture/tasks.md` —
  flip tasks 45-60 to `[x]` after the production code lands and
  `python harness.py check` is green. Tasks 61-123 stay `[ ]`.

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
  ADR is unchanged in this change; this change adds the
  `tree-sitter-java` subprocess without modifying the ADR text.
- `.ai/wiki/adr/0003-license-governance-default.md` — review and
  confirm the new `tree-sitter-java` MIT dependency is
  SPDX-tracked in
  `distribution/licenses/dependency-inventory.json` and passes
  `LicenseGate` before the adapter is registered.

## Spec / validator patch (pre-flight)

The OpenSpec CLI v1.4.0 strict validator (introduced since the
Phase 1 archive) requires `MUST` or `SHALL` on the first
non-blank, non-metadata line of every requirement body. The
Phase 1 archive predates this rule; ten Phase 1 requirements and
four Phase 2 requirements in
[`prepare-phase-2-ingestion/specs/`](../../changes/prepare-phase-2-ingestion/specs/)
have `MUST` / `SHALL` in their bodies but not on the first line.

`scripts/fix_spec_shall_must.py` adds the keyword to the first
line of every failing requirement in both the canonical spec
files (`openspec/specs/2026-10-04-*/spec.md`) and the delta
copies in `openspec/changes/plan-v0-8-platform-architecture/specs/`
and `openspec/changes/prepare-phase-2-ingestion/specs/`. The
patch preserves the original requirement body and adds a single
normative clause to the first paragraph. The patch is run
**before** any Phase 2 production code lands so the strict
validator is green at every subsequent step.

The 14 patched requirements:

| Capability | Requirement | File |
|---|---|---|
| `bidirectional-canonical-runtime-sync` | hydrate loads canonical knowledge into runtime | `openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md` + plan delta |
| `bidirectional-canonical-runtime-sync` | materialise writes runtime back to canonical | same |
| `canonical-knowledge-schema` | deterministic canonical serialization | `openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md` + plan delta |
| `canonical-knowledge-schema` | canonical object content addressing | same |
| `git-version-aware-runtime` | content-addressed processing reuse | `openspec/specs/2026-10-04-git-version-aware-runtime/spec.md` + plan delta |
| `license-governance` | review-required licenses must be explicitly accepted | `openspec/specs/2026-10-04-license-governance/spec.md` + plan delta |
| `license-governance` | restricted and non-commercial licenses are denied by default | same |
| `license-governance` | model licenses are tracked separately | same |
| `project-knowledge-repository-layout` | runtime working knowledge cache location | `openspec/specs/2026-10-04-project-knowledge-repository-layout/spec.md` + plan delta |
| `project-knowledge-repository-layout` | per-target runtime cache root resolution | same |
| `content-addressed-processing` | cross-branch cache reuse | `openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-content-addressed-processing/spec.md` |
| `content-addressed-processing` | cache eviction by source identity | same |
| `context-enrichment` | optional small LLM layer | `openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-context-enrichment/spec.md` |
| `jar-dependency-intelligence` | license pass-through | `openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-jar-dependency-intelligence/spec.md` |

The patch is idempotent. Running it a second time is a no-op
because the script checks for `MUST` / `SHALL` on the first line
before applying.

## Affected implementation

Modules/paths populated by this change:

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
- `pi_platform/adapters/pdf/` — planned Phase 2+ slot; the file
  path is reserved by the design baseline but no code is added in
  this change (the `pdfplumber` / `pypdf` dependency is not in
  the inventory);
- `pi_platform/adapters/openapi/` — planned Phase 2+ slot; the
  file path is reserved by the design baseline but no code is
  added in this change (the `openapi-schema-validator` /
  `prance` dependency is not in the inventory);
- `pi_platform/adapters/java/` — new `JavaParserPort` default
  adapter (`tree-sitter-java` out-of-process subprocess),
  `JavaStructuredAdapter`, `JarAdapter`, `MavenAdapter`,
  `GradleAdapter`;
- `pi_platform/adapters/openspec/` — new `OpenSpecChangeAdapter`;
- `pi_platform/adapters/fs/local_source_adapter.py` — new default
  adapter for Markdown / HTML / plain text;
- `pi_platform/cli/main.py` — extends the CLI with the
  `ingest-sources` subcommand;
- `tests/test_platform_phase2.py` — new Phase 2 regression suite;
- `tests/test_content_address_cross_branch.py` — new
  property-based cross-branch reuse test;
- `distribution/licenses/dependency-inventory.json` — new entry
  for `tree-sitter-java` MIT (only); PDF / OpenAPI
  libraries are NOT added in this change.

Primary symbols/interfaces introduced by this change:

- `pi_platform.ports.ingest.pipeline_driver.PipelineDriverPort`,
  `PipelineReport`, `StageOutcome`, `CancellationToken`,
  `StageContext`, `StageError`, `StageErrorCategory`;
- `pi_platform.ports.ingest.source_adapter.SourceAdapterPort`,
  `SourceContentFamily`, `SourceAdapterRegistry`,
  `SourceAdapterError`;
- `pi_platform.ports.ingest.chunker.ChunkerPort`,
  `ChunkerRegistry`;
- `pi_platform.ports.ingest.context_enricher.ContextEnricherPort`,
  `EnrichmentLayer`;
- `pi_platform.ports.ingest.java_parser.JavaParserPort`,
  `JavaParseRequest`, `JavaParseResult`, `JavaParserError`,
  `JavaParserMissing`, `JavaParserTimeout`,
  `JavaParserVersionMismatch`, `JavaParserCorruptOutput`;
- `pi_platform.ports.ingest.local_source_inbox_scanner
  .LocalSourceInboxScannerPort`, `SourcePromotionPolicy`,
  `LocalSourceInboxError`.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md` —
  remains accepted and unaffected. Phase 2 respects the decision
  by keeping harness core skills separated from the Phase 7
  agent integration packaging work.
- `adr/0002-canonical-runtime-separation.md` — remains accepted
  and unaffected. Phase 2 specs respect invariants #1–#4
  (canonical vs runtime, Git as source of truth, bidirectional
  sync, deterministic serialization).
- `adr/0003-license-governance-default.md` — remains accepted and
  unaffected. The new `tree-sitter-java` MIT dependency
  is SPDX-tracked in
  `distribution/licenses/dependency-inventory.json` and passes
  `LicenseGate` before the adapter is registered.
- `adr/0004-ports-and-adapters-extension-style.md` — remains
  accepted and unaffected. Phase 2 adds ports under
  `pi_platform/ports/ingest/` and adapters under
  `pi_platform/adapters/<family>/`.
- `adr/0005-platform-source-language.md` — remains accepted and
  unaffected. Phase 2 keeps the Python 3.11 default; the Java
  parser library is invoked as an out-of-process subprocess
  from a Python adapter rather than as a new platform-level
  language dependency.
- new `adr/0006-phase-2-parser-selection.md` — accepted; records
  the `tree-sitter-java` (MIT) choice and the rejected
  alternatives.
- new `adr/0007-phase-2-inbox-policy-default.md` — accepted;
  records the `LOCAL_ONLY` default and the override resolution
  rule.

## Acceptance criteria

- [ ] Relevant Wiki pages reflect shipped implementation. All
  updates above are additive and link back to the v0.8
  architecture baseline.
- [ ] Generated local context index was refreshed (`python
  harness.py wiki-init`).
- [ ] Links and stable knowledge IDs validate (`python harness.py
  wiki-validate` returns `ok: true`).
- [ ] Spec/implementation mismatches are resolved or explicitly
  documented. The nine Phase 2 specs describe the shipped
  platform behaviour against the v0.8 baseline with no conflict.
- [ ] `python harness.py check` returns `Harness core checks:
  PASS`.
- [ ] `openspec validate implement-phase-2-ingestion --type
  change --strict` returns valid before archive.
- [ ] `python harness.py wiki-validate` returns `{"ok": true,
  ...}`.
- [ ] `python3 scripts/artifact_manifest.py verify` returns
  `Artifact manifest: PASS`.
- [ ] `python -m pi_platform.cli license-gate` passes (no
  unapproved dependencies).
- [ ] `python -m unittest tests.test_platform_phase1 -v` is green
  (Phase 1 regression must not break).
- [ ] `python -m unittest tests.test_platform_phase2 -v` is green
  (Phase 2 regression).
- [ ] `python -m unittest tests.test_content_address_cross_branch
  -v` is green.
- [ ] `python -m unittest tests.test_canonical_roundtrip -v` is
  green (parent-link and content-address invariants).

The implementation corrects the upstream Java dependency license to MIT, records
additive policy/extensions metadata, and documents the retained Phase 1 content-address
helper naming mismatch. See design implementation reconciliation and parser ADR.
