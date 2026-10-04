# Tasks — implement-phase-2-ingestion

This tasks file mirrors the Phase 2 tasks 45-60 from the canonical
[`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md)
and is the implementation checklist for this change. Each task
entry lists the Python module / port / adapter being created, the
verification command, and the touched
`pi_platform.ports.*` or `pi_platform.adapters.*` paths. The
authoritative behavioural contract is the nine Phase 2 capability
specs in [`specs/`](specs). The archive step at the end of this
change promotes the nine deltas to
`openspec/specs/2026-10-04-*/` and flips plan-change tasks 45-60
from `[ ]` to `[x]`.

Verification commands referenced below:

- `python -m unittest tests.<module> -v` — focused regression
  tests;
- `openspec validate implement-phase-2-ingestion --type change
  --strict` — change validation (must pass before archive);
- `python harness.py check` — full harness core gate
  (license-gate, openspec-check, wiki-validate,
  artifact-manifest);
- `python -m pi_platform.cli license-gate` — Phase 1 license
  gate; the new `tree-sitter-java` MIT entry MUST pass.

## Pre-flight (before any code lands)

- [x] 0.1. Run `python3 scripts/fix_spec_shall_must.py` to add
  `MUST` / `SHALL` to the first line of the 10 Phase 1
  requirements and 4 Phase 2 requirements whose bodies contain
  the keyword but not on the first line. Re-run until the
  script reports no further fixes.
- [x] 0.2. Run `python harness.py check` and confirm `Harness
  core checks: PASS`. Regenerate `ARTIFACT_MANIFEST.sha256` via
  `python3 scripts/artifact_manifest.py generate` after any new
  file lands.
- [x] 0.3. Run `openspec validate --all --strict` and confirm
  `Totals: N passed, 0 failed` for every spec and change.

## Phase 2 — Ingestion (this change)

### 2.1 — PipelineDriver and orchestration (task 45)

- [x] 45. Implement `pi_platform.ports.ingest.PipelineDriver` —
  the §18 ingestion pipeline coordinator (parsers → chunking →
  enrichment → graph/vector/metadata → runtime store) with
  explicit stage boundaries and stage error handling.
  → `pi_platform/ports/ingest/pipeline_driver.py` (new port:
  `PipelineDriverPort`, `PipelineReport`, `StageOutcome`,
  `StageContext`, `CancellationToken`, `StageError`,
  `StageErrorCategory`),
  `pi_platform/core/ingest/pipeline_driver.py` (new core),
  `pi_platform/adapters/ingest/local_pipeline_driver.py` (new
  default adapter: `LocalPipelineDriver`).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.PipelineDriverTests -v`
  - `openspec validate implement-phase-2-ingestion --type
    change --strict`
  - `python harness.py check`.

### 2.2 — Git adapter decision (task 46)

- [x] 46. Record the `platform.adapters.git.LibGit2OrCliAdapter`
  final choice (default CLI for portability; document the
  decision in the change's `design.md`). No new libgit2
  dependency is added by this change; the Phase 1
  `pi_platform/adapters/git/cli_adapter.py` remains the default.
  → `pi_platform/adapters/git/cli_adapter.py` (unchanged),
  `tests/test_platform_phase2.GitAdapterTests` (new test class
  that exercises the existing CLI adapter through the Phase 1
  `GitPort`).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.GitAdapterTests -v`
  - `python harness.py check`.

### 2.3 — Content addressing (task 47)

- [x] 47. Implement the property-based cross-branch reuse test
  for the Phase 1 SHA-256 cache key contract.
  → `tests/test_content_address_cross_branch.py` (new property
  test). The `content_address` helper from Phase 1 already
  exists at
  `pi_platform/core/canonical/content_address.py`; this change
  does NOT modify that helper.
  Verification:
  - `python -m unittest
    tests.test_content_address_cross_branch -v`
  - the existing Phase 1
    `python -m unittest tests.test_canonical_roundtrip -v` MUST
    continue to pass byte-for-byte.

### 2.4 — Document source adapters (task 48)

- [x] 48. Implement document source adapters: Markdown, HTML
  and plain text. Each adapter implements a `SourceAdapter`
  port returning `Document + Section[]`. PDF, OpenAPI and
  office adapters are out of scope for this change (the
  `pdfplumber` and `openapi-schema-validator` dependencies are
  not added to
  `distribution/licenses/dependency-inventory.json`).
  → `pi_platform/ports/ingest/source_adapter.py` (new port:
  `SourceAdapterPort`, `SourceContentFamily`,
  `SourceAdapterRegistry`, `SourceAdapterError`),
  `pi_platform/adapters/fs/local_source_adapter.py` (new
  default adapter, Markdown + HTML + plain text),
  `pi_platform/adapters/markdown/markdown_adapter.py` (new,
  shared with `OpenSpecChangeAdapter`),
  `pi_platform/adapters/html/html_adapter.py` (new, stdlib
  `html.parser`).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.SourceAdapterTests -v`
  - `python harness.py check`.

### 2.5 — Local source inbox scanner (task 49)

- [x] 49. Implement the local source inbox scanner
  (`LocalSourceInboxScanner`) honouring `LOCAL_ONLY`,
  `REFERENCE` and `SNAPSHOT` policies from §9.
  → `pi_platform/ports/ingest/local_source_inbox_scanner.py`
  (new port: `LocalSourceInboxScannerPort`,
  `SourcePromotionPolicy` enum, `LocalSourceInboxError`),
  `pi_platform/core/ingest/local_source_inbox_scanner.py` (new
  core).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.LocalSourceInboxScannerTests -v`
  - `python -m unittest
    tests.test_platform_phase2.LocalSourceInboxScannerSpecTests
    -v`
  - `openspec validate implement-phase-2-ingestion --type
    change --strict`.

### 2.6 — OpenSpec change adapter (task 50)

- [x] 50. Implement the OpenSpec adapter that reads
  `openspec/specs/` and `openspec/changes/` and produces
  `Requirement`, `Specification`, `OpenSpecChange` entities
  plus `SATISFIES`, `PART_OF`, `IMPLEMENTED_BY` relations.
  → `pi_platform/adapters/openspec/openspec_change_adapter.py`
  (new adapter), reusing the Phase 1 OKF helper and the shared
  `MarkdownAdapter` from task 48.
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.OpenSpecChangeAdapterTests -v`
  - `python harness.py check`.

### 2.7 — Java structured adapter (task 51)

- [x] 51. Implement `pi_platform.ports.ingest.JavaParserPort`
  and `pi_platform.adapters.java.JavaStructuredAdapter` for
  Maven modules, packages, classes, interfaces, methods,
  constructors, inheritance, annotations, calls, JPA mappings,
  configuration, tests. The default parser library is
  `tree-sitter-java` (MIT) invoked as an out-of-process
  subprocess; the adapter falls back to degraded mode when the
  binary is missing.
  → `pi_platform/ports/ingest/java_parser.py` (new port:
  `JavaParserPort`, `JavaParseRequest`, `JavaParseResult`,
  `JavaParserError` and subtypes),
  `pi_platform/adapters/java/parser_subprocess.py` (new
  default adapter: `TreeSitterJavaSubprocess`),
  `pi_platform/adapters/java/java_structured_adapter.py` (new
  adapter).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.JavaStructuredAdapterTests -v`
  - the Phase 1 license gate
    `python -m pi_platform.cli license-gate` MUST pass with
    the new `tree-sitter-java` SPDX entry in
    `distribution/licenses/dependency-inventory.json`.
  - `python harness.py check`.

### 2.8 — JAR adapter (task 52)

- [x] 52. Implement `JarAdapter` for artifact coordinates,
  versions, packages, classes, interfaces, signatures,
  annotations, inherited types, modules, resources, source-JAR
  content, public APIs, dependency relationships. The adapter
  uses Python stdlib `zipfile` only; no third-party Java
  parsing library is required.
  → `pi_platform/adapters/java/jar_adapter.py` (new adapter).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.JarAdapterTests -v`
  - `python -m pi_platform.cli license-gate` MUST pass.

### 2.9 — Maven and Gradle adapters (task 53)

- [x] 53. Implement Gradle and `pom.xml` dependency-graph
  extraction (`MavenAdapter`, `GradleAdapter`). Both adapters
  use Python stdlib XML / text parsing only; no third-party
  library is required.
  → `pi_platform/adapters/java/maven_adapter.py` (new),
  `pi_platform/adapters/java/gradle_adapter.py` (new).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.MavenGradleAdapterTests -v`
  - `python -m pi_platform.cli license-gate` MUST pass.

### 2.10 — Semantic / structural chunker (task 54)

- [x] 54. Implement semantic / structural chunker selecting
  boundaries by document section / heading / Java class /
  Java method / OpenSpec element / requirement / protocol
  message / table / architecture unit. Chunks retain parent
  links.
  → `pi_platform/ports/ingest/chunker.py` (new port:
  `ChunkerPort`, `ChunkerRegistry`),
  `pi_platform/adapters/ingest/markdown_chunker.py` (new),
  `pi_platform/adapters/ingest/html_chunker.py` (new),
  `pi_platform/adapters/ingest/plain_text_chunker.py` (new),
  plus the Java / OpenSpec chunkers delegated to
  `JavaStructuredAdapter` and `OpenSpecChangeAdapter`.
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.ChunkerTests -v`
  - the Phase 1 `tests/test_canonical_roundtrip.py` MUST
    continue to pass byte-for-byte (parent-link invariant).

### 2.11 — Context enrichment (task 55)

- [x] 55. Implement three-layer context enrichment
  (deterministic metadata + domain rules + optional small LLM)
  producing `ContextualChunk` records. The optional small LLM
  layer is disabled by default and stubbed in this change (the
  Phase 5 `LocalLLMPort` placeholder provides the binding).
  → `pi_platform/ports/ingest/context_enricher.py` (new port:
  `ContextEnricherPort`, `EnrichmentLayer` enum),
  `pi_platform/adapters/ingest/layered_context_enricher.py`
  (new default adapter: `LayeredContextEnricher`).
  Verification:
  - `python -m unittest
    tests.test_platform_phase2.ContextEnricherTests -v`
  - the Phase 1 `tests/test_canonical_roundtrip.py` MUST
    continue to pass byte-for-byte.

### 2.12 — Spec scenarios for inbox, content-address, chunking (tasks 56–58)

- [x] 56. Implement the `local-source-inbox` spec scenarios
  (covered by
  `tests/test_platform_phase2.LocalSourceInboxScannerSpecTests`).
- [x] 57. Implement the `content-addressed-processing` spec
  scenarios (covered by
  `tests/test_content_address_cross_branch.py` and
  `tests/test_platform_phase2.ContentAddressedProcessingTests`).
- [x] 58. Implement the `semantic-structural-chunking`,
  `context-enrichment`, `document-source-adapters`,
  `openspec-change-adapter`, `structured-code-intelligence`,
  `jar-dependency-intelligence` spec scenarios (covered by the
  corresponding `*Tests` classes in
  `tests/test_platform_phase2.py`).

Verification for the slice (tasks 56–58):

  - `python -m unittest tests.test_platform_phase2 -v`
  - `python -m unittest tests.test_content_address_cross_branch
    -v`
  - `python -m unittest tests.test_canonical_roundtrip -v`
    (Phase 1 round-trip test MUST continue to pass).

### 2.13 — Focused regression tests per adapter and per chunker (task 59)

- [x] 59. Add focused regression tests per adapter and per
  chunker. One test class per scenario named after the scenario,
  mirroring the Phase 1 convention in
  `tests/test_platform_phase1.py`. Coverage matrix:
  - `PipelineDriverTests`, `GitAdapterTests`,
    `ContentAddressedProcessingTests`,
    `ContentAddressCrossBranchTests`,
    `SourceAdapterTests`,
    `LocalSourceInboxScannerTests`,
    `LocalSourceInboxScannerSpecTests`,
    `OpenSpecChangeAdapterTests`,
    `JavaStructuredAdapterTests`, `JarAdapterTests`,
    `MavenGradleAdapterTests`, `ChunkerTests`,
    `ContextEnricherTests`;
  - the Phase 1 `tests/test_canonical_roundtrip.py` MUST
    continue to pass byte-for-byte (parent-link invariant and
    content-address invariant);
  - the property-based cross-branch reuse test
    `tests/test_content_address_cross_branch.py` (task 47)
    covers `Chunk`, `Entity`, `Relation` with 100 random seeds
    per value type.

Verification:

  - `python -m unittest tests.test_platform_phase2 -v`
  - `python -m unittest tests.test_content_address_cross_branch
    -v`
  - `python -m unittest tests.test_canonical_roundtrip -v`
  - `python harness.py check` MUST pass.

### 2.14 — CLI surface extension (task 60, part 1)

- [x] 60a. Extend `pi_platform/cli/main.py` with the
  `ingest-sources` subcommand that wires the default
  `LocalPipelineDriver` and `LocalSourceInboxScanner`. Do NOT
  modify the existing subcommands (`init-project`, `hydrate`,
  `materialise`, `license-gate`, `okf-validate`,
  `version-identity`, `wal-recover`, `health`).
  Verification:
  - `python -m pi_platform.cli --help` lists `ingest-sources`.
  - `python -m pi_platform.cli ingest-sources --help` exits
    zero.

### 2.15 — Container / launcher update (task 60, part 2)

- [x] 60b. Update `Containerfile` to install the new Python
  packages. The Java parser subprocess is NOT bundled into the
  container image; the adapter falls back to degraded mode if
  the binary is absent. The PDF / OpenAPI adapters are not
  populated in this change, so their dependencies do NOT land
  in the Containerfile.

### 2.16 — Wiki / harness maintenance (task 60, part 3)

- [x] 60c. Create
  `.ai/wiki/modules/ingest.md`,
  `.ai/wiki/interfaces/source-adapters.md`,
  `.ai/wiki/interfaces/chunker.md`,
  `.ai/wiki/interfaces/enrichment.md`,
  `.ai/wiki/adr/0006-phase-2-parser-selection.md`,
  `.ai/wiki/adr/0007-phase-2-inbox-policy-default.md`.
- [x] 60d. Update
  `.ai/wiki/architecture/platform-overview.md`,
  `.ai/wiki/architecture/system-overview.md`,
  `.ai/wiki/glossary/platform.md`,
  `.ai/wiki/glossary/domain.md`,
  `.ai/wiki/project/project-map.md`,
  `.ai/wiki/project/implementation-roadmap.md`,
  `.ai/wiki/INDEX.md`.
- [x] 60e. Run `python harness.py wiki-init` to refresh the
  local FTS index, then `python harness.py wiki-validate` to
  confirm `ok: true`.

### 2.17 — openspec/CURRENT.md adoption (task 60, part 4)

- [x] 60f. Add the nine Phase 2 capabilities under
  "Project product capabilities" in
  `openspec/CURRENT.md`, in date order. Each entry links to the
  new spec under
  `openspec/specs/2026-10-04-*/spec.md` (after the archive step
  promotes the deltas).

### 2.18 — Verification gates (task 60, part 5)

- [x] 60g. Run all verification gates and confirm PASS / valid:
  - `python harness.py check` →
    `Harness core checks: PASS`
  - `openspec validate implement-phase-2-ingestion --type
    change --strict` →
    `Change 'implement-phase-2-ingestion' is valid`
  - `python harness.py wiki-validate` →
    `{"ok": true, ...}`
  - `python3 scripts/artifact_manifest.py generate` then
    `python3 scripts/artifact_manifest.py verify` →
    `Artifact manifest: PASS`
  - `python -m pi_platform.cli license-gate` → no unapproved
    dependencies
  - `python -m unittest tests.test_platform_phase1 -v` →
    green
  - `python -m unittest tests.test_platform_phase2 -v` →
    green
  - `python -m unittest tests.test_content_address_cross_branch
    -v` → green
  - `python -m unittest tests.test_canonical_roundtrip -v` →
    green

### 2.19 — Archive (task 60, part 6)

- [x] 60h. Run `openspec archive implement-phase-2-ingestion
  -y`. This promotes the nine deltas to
  `openspec/specs/2026-10-04-*/`, archives the implementation
  change under
  `openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`,
  and archives the prepare change under
  `openspec/changes/archive/2026-10-04-prepare-phase-2-ingestion/`.

### 2.20 — Plan task flip (task 60, part 7)

- [x] 60i. Edit
  `openspec/changes/plan-v0-8-platform-architecture/tasks.md`
  and flip tasks 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55,
  56, 57, 58, 59, 60 from `[ ]` to `[x]`. Tasks 61-123
  (Phase 3-10) stay `[ ]`. Add a short inline note per task
  citing the implementing commit or the on-disk file path so
  the future Phase 3 agent can verify without re-reading the
  archive.

### 2.21 — Final harness check (task 60, part 8)

- [x] 60j. Run `python harness.py wiki-init`,
  `python harness.py check` and `python harness.py
  openspec-check`. All three MUST PASS.

## Out-of-scope tasks (this change)

The tasks below belong to later phases and are NOT executed by
this change. They are listed here only so the implementation
work knows where to draw the line.

- the runtime DB rebuild for storage — Phase 3 task 62
  (`RuntimeStore`);
- the sharded knowledge graph — Phase 3 task 66 (`Graph`);
- the dense ANN index over the chunks — Phase 4 task 71
  (`HybridRetrieval`);
- the reranker over the chunks — Phase 4 task 74
  (`RerankerPort`);
- the local LLM port — Phase 5 task 80 (`LocalLLMPort`);
- the MCP server exposing the pipeline report and entities —
  Phase 6 task 85 (`McpServer`);
- the Wiki materialisation of the pipeline entities — Phase 9
  task 112 (`OKF wiki profile`).

## Verification of this implementation change

- [x] `python harness.py check` returns `Harness core checks:
  PASS`.
- [x] `openspec validate implement-phase-2-ingestion --type
  change --strict` returns `Change 'implement-phase-2-ingestion'
  is valid`.
- [x] `python harness.py wiki-validate` returns
  `{"ok": true, ...}`.
- [x] `python3 scripts/artifact_manifest.py verify` returns
  `Artifact manifest: PASS`.
- [x] `python -m pi_platform.cli license-gate` passes.
- [x] `python -m unittest tests.test_platform_phase1 -v` is
  green.
- [x] `python -m unittest tests.test_platform_phase2 -v` is
  green.
- [x] `python -m unittest
  tests.test_content_address_cross_branch -v` is green.
- [x] `python -m unittest tests.test_canonical_roundtrip -v`
  is green.
- [x] The `plan-v0-8-platform-architecture/tasks.md` tasks
  45-60 are `[x]` (flipped by this change).
- [x] `openspec/specs/2026-10-04-*/` contains the nine Phase 2
  capability folders (after archive).
- [x] `openspec/CURRENT.md` lists the nine new capabilities
  under "Project product capabilities" (after archive).
- [x] `openspec/changes/archive/2026-10-04-implement-phase-2-
  ingestion/` exists (after archive).
- [x] `openspec/changes/archive/2026-10-04-prepare-phase-2-
  ingestion/` exists (after archive).

## Close-out evidence

101 focused tests pass; the full pre-archive harness passes with local MCP socket
access, strict OpenSpec validation passes, Wiki validation reports 26 documents,
and the dependency license gate passes. The wheel builds, installs, and runs ingestion
without optional parser/YAML packages. Additional real-parser/JDK integration tests
cover Java structure, source-JAR evidence, bytecode signatures, retries and cancellation.
Archive adoption is followed by a fresh full harness and manifest verification.
