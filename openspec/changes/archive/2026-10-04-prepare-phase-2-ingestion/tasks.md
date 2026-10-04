# Tasks — prepare-phase-2-ingestion

This tasks file mirrors the Phase 2 tasks 45–59 from the canonical
[`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md).
The tasks below are the future implementation work; they will be
executed by the future `implement-phase-2-ingestion` change. This
change ships zero production code.

The 9 Phase 2 capability specs under
[`specs/`](specs) are the authoritative behavioural contract for
the implementation work. The future change depends on the 9 specs
being accepted into `openspec/specs/2026-10-04-*/` before tasks 45–
59 can be marked `[x]`; until then they stay `[ ]` in both the
plan change and the future implementation change.

Verification commands referenced below:

- `python -m unittest tests.<module> -v` — focused regression tests;
- `openspec validate prepare-phase-2-ingestion --type change` (this
  change), `openspec validate implement-phase-2-ingestion --type
  change` (future change), `openspec validate --all --strict`
  (canonical harness check);
- `python harness.py check` — full harness core gate
  (license-gate, openspec-check, wiki-validate, artifact-manifest).

## Phase 2 — Ingestion (preparation only)

### 2.1 — PipelineDriver and orchestration (task 45)

- [ ] 45. Implement `platform.ingest.PipelineDriver` (§18) — the
  ingestion pipeline coordinator (parsers → chunking → enrichment →
  graph/vector/metadata → runtime store) with explicit stage
  boundaries and stage error handling.
  → `pi_platform/ports/ingest/pipeline_driver.py` (new port),
  `pi_platform/core/ingest/pipeline_driver.py` (new core),
  `pi_platform/adapters/ingest/local_pipeline_driver.py` (new
  default adapter).
  Verification:
  - `python -m unittest tests.test_platform_phase2.PipelineDriverTests -v`
  - `openspec validate implement-phase-2-ingestion --type change`
  - `python harness.py check`.

### 2.2 — Git adapter (task 46)

- [ ] 46. Implement `platform.adapters.git.LibGit2OrCliAdapter`
  final choice (default CLI for portability; document the
  decision).
  → `pi_platform/adapters/git/libgit2_adapter.py` (new, behind the
  Phase 1 `GitPort`) plus an ADR that records the choice (likely
  keeping the Phase 1 CLI adapter as default and adding libgit2 as
  optional).
  Verification:
  - `python -m unittest tests.test_platform_phase2.GitAdapterTests -v`
  - `openspec validate implement-phase-2-ingestion --type change`
  - `python harness.py check`.

### 2.3 — Content addressing (task 47)

- [ ] 47. Implement `platform.core.canonical.ContentAddress`
  final contract (SHA-256 cache reuse across branches) plus a
  property-based cross-branch reuse test.
  → `tests/test_content_address_cross_branch.py` (new property test);
  the `content_address` helper from Phase 1 already exists at
  `pi_platform/core/canonical/content_address.py`.
  Verification:
  - `python -m unittest tests.test_content_address_cross_branch -v`
  - the existing Phase 1
    `python -m unittest tests.test_canonical_roundtrip -v` MUST
    continue to pass byte-for-byte.

### 2.4 — Document source adapters (task 48)

- [ ] 48. Implement document source adapters: Markdown, HTML, plain
  text, supported office documents. Each adapter implements a
  `SourceAdapter` port returning `Document + Section[]`.
  → `pi_platform/ports/ingest/source_adapter.py` (new port),
  `pi_platform/adapters/fs/local_source_adapter.py` (new default
  adapter, Markdown + HTML + plain text),
  `pi_platform/adapters/markdown/markdown_adapter.py` (new, shared
  with `OpenSpecChangeAdapter`),
  `pi_platform/adapters/html/html_adapter.py` (new),
  `pi_platform/adapters/pdf/pdf_adapter.py` (new, planned
  `pdfplumber` MIT dependency), plus the office-document adapter
  set behind the same port.
  Verification:
  - `python -m unittest tests.test_platform_phase2.SourceAdapterTests -v`
  - `openspec validate implement-phase-2-ingestion --type change`
  - `python harness.py check`.

### 2.5 — Local source inbox scanner (task 49)

- [ ] 49. Implement the local source inbox scanner
  (`LocalSourceInboxScanner`) honouring `LOCAL_ONLY`, `REFERENCE`
  and `SNAPSHOT` policies from §9.
  → `pi_platform/ports/ingest/local_source_inbox_scanner.py` (new
  port), `pi_platform/core/ingest/local_source_inbox_scanner.py`
  (new core).
  Verification:
  - `python -m unittest tests.test_platform_phase2.LocalSourceInboxScannerTests -v`
  - `openspec validate implement-phase-2-ingestion --type change`.

### 2.6 — OpenSpec change adapter (task 50)

- [ ] 50. Implement the OpenSpec adapter that reads
  `openspec/specs/` and `openspec/changes/` and produces
  `Requirement`, `Specification`, `OpenSpecChange` entities plus
  `SATISFIES`, `PART_OF`, `IMPLEMENTED_BY` relations.
  → `pi_platform/adapters/openspec/openspec_change_adapter.py`
  (new adapter), reusing the Phase 1 OKF helper and the shared
  `MarkdownAdapter` from task 48.
  Verification:
  - `python -m unittest tests.test_platform_phase2.OpenSpecChangeAdapterTests -v`
  - `openspec validate implement-phase-2-ingestion --type change`.

### 2.7 — Java structured adapter (task 51)

- [ ] 51. Implement `platform.ingest.JavaStructuredAdapter` for
  Maven modules, packages, classes, interfaces, methods,
  constructors, inheritance, annotations, calls, JPA mappings,
  configuration, tests. Use a documented Java parser library
  whose license passes the license gate.
  → `pi_platform/ports/ingest/java_parser.py` (new port),
  `pi_platform/adapters/java/parser_subprocess.py` (new default
  adapter, out-of-process `tree-sitter-java` MIT),
  `pi_platform/adapters/java/java_structured_adapter.py` (new
  adapter).
  Verification:
  - `python -m unittest tests.test_platform_phase2.JavaStructuredAdapterTests -v`
  - the Phase 1 license gate `python -m pi_platform.cli license-gate`
    MUST pass with the new `tree-sitter-java` SPDX entry in
    `distribution/licenses/dependency-inventory.json`.

### 2.8 — JAR adapter (task 52)

- [ ] 52. Implement `platform.ingest.JarAdapter` for artifact
  coordinates, versions, packages, classes, interfaces,
  signatures, annotations, inherited types, modules, resources,
  source-JAR content, public APIs, dependency relationships.
  → `pi_platform/adapters/java/jar_adapter.py` (new adapter).
  Verification:
  - `python -m unittest tests.test_platform_phase2.JarAdapterTests -v`
  - the Phase 1 license gate MUST pass.

### 2.9 — Maven and Gradle adapters (task 53)

- [ ] 53. Implement Gradle and `pom.xml` dependency-graph
  extraction (`platform.ingest.MavenAdapter`,
  `platform.ingest.GradleAdapter`).
  → `pi_platform/adapters/java/maven_adapter.py` (new),
  `pi_platform/adapters/java/gradle_adapter.py` (new).
  Verification:
  - `python -m unittest tests.test_platform_phase2.MavenGradleAdapterTests -v`
  - the Phase 1 license gate MUST pass.

### 2.10 — Semantic / structural chunker (task 54)

- [ ] 54. Implement semantic/structural chunker selecting boundaries
  by document section / heading / Java class / Java method /
  OpenSpec element / requirement / protocol message / table /
  architecture unit. Chunks retain parent links.
  → `pi_platform/ports/ingest/chunker.py` (new port),
  `pi_platform/adapters/ingest/markdown_chunker.py` (new),
  `pi_platform/adapters/ingest/html_chunker.py` (new),
  `pi_platform/adapters/ingest/plain_text_chunker.py` (new),
  plus the Java / requirement protocol chunkers under
  `pi_platform/adapters/ingest/` (delegated to
  `structured-code-intelligence` and `openspec-change-adapter`).
  Verification:
  - `python -m unittest tests.test_platform_phase2.ChunkerTests -v`
  - the Phase 1 `tests/test_canonical_roundtrip.py` MUST continue to
    pass byte-for-byte (parent-link invariant).

### 2.11 — Context enrichment (task 55)

- [ ] 55. Implement three-layer context enrichment (deterministic
  metadata + domain rules + optional small LLM) producing
  `ContextualChunk` records.
  → `pi_platform/ports/ingest/context_enricher.py` (new port),
  `pi_platform/adapters/ingest/layered_context_enricher.py` (new
  default adapter).
  Verification:
  - `python -m unittest tests.test_platform_phase2.ContextEnricherTests -v`
  - the Phase 1 `tests/test_canonical_roundtrip.py` MUST continue to
    pass byte-for-byte.

### 2.12 — Spec scenarios for inbox, content-address, chunking (tasks 56–58)

- [ ] 56. Implement the `local-source-inbox` spec scenarios (added
  in this change's `affected capabilities` table).
  → covered by `tests/test_platform_phase2.LocalSourceInboxScannerTests`
  and `LocalSourceInboxScannerSpecTests`.
- [ ] 57. Implement the `content-addressed-processing` spec
  scenarios (added in this change's table).
  → covered by `tests/test_content_address_cross_branch.py`
  (property-based) and
  `tests/test_platform_phase2.ContentAddressedProcessingTests`.
- [ ] 58. Implement the `semantic-structural-chunking`,
  `context-enrichment`, `document-source-adapters`,
  `openspec-change-adapter`, `structured-code-intelligence`,
  `jar-dependency-intelligence` spec scenarios as Phase 2.
  → covered by the corresponding `*Tests` classes in
  `tests/test_platform_phase2.py`.

Verification for the slice (tasks 56–58):

  - `python -m unittest tests.test_platform_phase2 -v`
  - `python -m unittest tests.test_content_address_cross_branch -v`
  - `python -m unittest tests.test_canonical_roundtrip -v` (Phase 1
    round-trip test MUST continue to pass).

### 2.13 — Focused regression tests per adapter and per chunker (task 59)

- [ ] 59. Add focused regression tests per adapter and per chunker.
  → one test class per scenario named after the scenario, mirroring
  the Phase 1 convention in `tests/test_platform_phase1.py`. Coverage
  matrix:
  - `PipelineDriverTests`, `GitAdapterTests`,
    `ContentAddressedProcessingTests`,
    `SourceAdapterTests`, `LocalSourceInboxScannerTests`,
    `OpenSpecChangeAdapterTests`, `JavaStructuredAdapterTests`,
    `JarAdapterTests`, `MavenGradleAdapterTests`, `ChunkerTests`,
    `ContextEnricherTests`, `LocalSourceInboxScannerSpecTests`,
    `ContentAddressCrossBranchTests`;
  - the Phase 1 `tests/test_canonical_roundtrip.py` MUST continue to
    pass byte-for-byte (parent-link invariant and content-address
    invariant);
  - the property-based cross-branch reuse test
    `tests/test_content_address_cross_branch.py` (task 47) covers
    `Chunk`, `Entity`, `Relation` with 100 random seeds per value
    type.

Verification:

  - `python -m unittest tests.test_platform_phase2 -v`
  - `python -m unittest tests.test_content_address_cross_branch -v`
  - `python -m unittest tests.test_canonical_roundtrip -v`
  - `python harness.py check` MUST pass.

### 2.14 — Wiki / harness maintenance (task 60)

- [ ] 60. Update Wiki (new `modules/ingest`, `interfaces/source-
  adapters`, `interfaces/chunker`, `interfaces/enrichment`),
  archive the Phase 2 change, update `openspec/CURRENT.md`.
  → `.ai/wiki/modules/ingest.md` (new),
  `.ai/wiki/interfaces/source-adapters.md` (new),
  `.ai/wiki/interfaces/chunker.md` (new),
  `.ai/wiki/interfaces/enrichment.md` (new),
  `.ai/wiki/architecture/platform-overview.md` (Phase 2 module
  map), `.ai/wiki/glossary/platform.md` (`PipelineDriver`,
  `SourceAdapter`, `LocalSourceInboxScanner`, `ContextEnricher`),
  `.ai/wiki/INDEX.md` (new entries), `openspec/CURRENT.md` (the nine
  Phase 2 capabilities added), archive `implement-phase-2-ingestion`
  under `archive/2026-10-04-implement-phase-2-ingestion/`.

Verification for the slice (task 60):

  - `python harness.py wiki-validate` MUST pass;
  - `python harness.py openspec-check` MUST pass;
  - `python harness.py check` MUST pass.

## Out-of-scope tasks (this change)

The tasks below belong to later phases and are NOT executed by the
future `implement-phase-2-ingestion` change. They are listed here
only so the future implementation work knows where to draw the line.

- the runtime DB rebuild for storage — Phase 3 task 62 (`RuntimeStore`);
- the sharded knowledge graph — Phase 3 task 66 (`Graph`);
- the dense ANN index over the chunks — Phase 4 task 71
  (`HybridRetrieval`);
- the reranker over the chunks — Phase 4 task 74 (`RerankerPort`);
- the local LLM port — Phase 5 task 80 (`LocalLLMPort`);
- the MCP server exposing the pipeline report and entities — Phase 6
  task 85 (`McpServer`);
- the Wiki materialisation of the pipeline entities — Phase 9 task
  112 (`OKF wiki profile`).

## Verification of this preparation change

- [ ] `python harness.py check` returns `Harness core checks: PASS`.
- [ ] `openspec validate prepare-phase-2-ingestion --type change`
  returns `Change 'prepare-phase-2-ingestion' is valid`.
- [ ] `python harness.py wiki-validate` returns `{"ok": true, ...}`.
- [ ] `python3 scripts/artifact_manifest.py verify` returns
  `Artifact manifest: PASS`.
- [ ] No production code under `pi_platform/ingest/`,
  `pi_platform/adapters/ingest/`, `pi_platform/adapters/java/`,
  `pi_platform/adapters/openspec/`, `pi_platform/adapters/markdown/`
  or `pi_platform/adapters/html/` is added by this change.
- [ ] The `plan-v0-8-platform-architecture/tasks.md` tasks 45–59 are
  still `[ ]` (not flipped by this change).

## Preparation close-out

The proposal and all nine deltas were completed and validated before implementation.
Production execution of the checklist above is tracked in implement-phase-2-ingestion;
unchecked production items here do not assert a second implementation. Both changes
are archived together, with preparation using --skip-specs after implementation adoption.
