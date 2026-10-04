# Design — implement-phase-2-ingestion

## Current state

The Phase 1 foundation is shipped and green:

- the five accepted Phase 1 capability specs live under
  `openspec/specs/2026-10-04-*/` (`project-knowledge-repository-layout`,
  `canonical-knowledge-schema`, `git-version-aware-runtime`,
  `bidirectional-canonical-runtime-sync`, `license-governance`);
- the `pi_platform/` Python 3.11 package is in place with the
  Phase 1 `core/{canonical,git,sync,licensing}` subpackages, the
  `ports/__init__.py` aggregate, the `adapters/{fs,git}` default
  adapters, the `runtime/` working knowledge cache scaffolding and
  the `cli/` entry point exposing `init-project`, `hydrate`,
  `materialise`, `license-gate`, `okf-validate`, `version-identity`,
  `wal-recover` and `health`;
- the 155-test regression suite and the `python harness.py check`
  gate are green (after a small strict-validator MUST/SHALL patch
  applied by `scripts/fix_spec_shall_must.py` and recorded in
  `context-impact.md`);
- the nine Phase 2 capability specs are proposed and validated
  under `openspec/changes/prepare-phase-2-ingestion/specs/2026-10-04-*/`
  and mirrored under
  `openspec/changes/implement-phase-2-ingestion/specs/2026-10-04-*/`
  (copied verbatim so the implementation change carries the same
  delta set during archive).

The repository does not yet contain any Phase 2 production code
under `pi_platform/ingest/`, `pi_platform/ports/ingest/`,
`pi_platform/core/ingest/`, `pi_platform/adapters/ingest/`,
`pi_platform/adapters/java/`, `pi_platform/adapters/openspec/`,
`pi_platform/adapters/markdown/`, `pi_platform/adapters/html/`,
`pi_platform/adapters/pdf/`, `pi_platform/adapters/openapi/` or
`pi_platform/adapters/fs/local_source_adapter.py`. No Java parser
library has been added to
`distribution/licenses/dependency-inventory.json`. The Phase 2 task
list (`plan-v0-8-platform-architecture/tasks.md` rows 45–60) is
still `[ ]`.

The Phase 1 round-trip invariant
`tests/test_canonical_roundtrip.py` is the canonical guard against
schema breakage. It MUST remain green byte-for-byte after this
change lands.

## Proposed design

This change implements the Phase 2 production surface documented in
the design baseline at
[`openspec/changes/prepare-phase-2-ingestion/design.md`](../../changes/prepare-phase-2-ingestion/design.md).
The design below records the concrete module skeleton (file paths,
class names, exception hierarchy, lock-acquisition pattern) and the
per-test file list that the change creates. The semantic design
(parsers, chunker strategy, context-enricher layers, inbox scanner
policy, OpenSpec change adapter, parser library rationale,
cross-branch reuse test) is unchanged from
`prepare-phase-2-ingestion/design.md`; this document does NOT
duplicate that rationale.

### Module skeleton

```
pi_platform/ports/ingest/
  pipeline_driver.py        # PipelineDriverPort, PipelineReport,
                           # StageOutcome, CancellationToken,
                           # StageContext
  source_adapter.py         # SourceAdapterPort, SourceContentFamily,
                           # SourceAdapterRegistry
  chunker.py                # ChunkerPort, ChunkerRegistry
  context_enricher.py       # ContextEnricherPort, EnrichmentLayer
  java_parser.py            # JavaParserPort
  local_source_inbox_scanner.py
                           # LocalSourceInboxScannerPort,
                           # SourcePromotionPolicy (LOCAL_ONLY,
                           # REFERENCE, SNAPSHOT)

pi_platform/core/ingest/
  pipeline_driver.py        # core coordinator (no runtime DB)
  local_source_inbox_scanner.py
                           # core scanner honouring the policy

pi_platform/adapters/ingest/
  local_pipeline_driver.py
                           # default PipelineDriverPort impl
  markdown_chunker.py       # MarkdownChunker
  html_chunker.py           # HtmlChunker
  plain_text_chunker.py     # PlainTextChunker (paragraph fallback)
  layered_context_enricher.py
                           # default 3-layer ContextEnricherPort impl

pi_platform/adapters/fs/
  local_source_adapter.py  # default SourceAdapterPort impl
                           # (Markdown / HTML / plain text)

pi_platform/adapters/markdown/
  markdown_adapter.py       # shared with OpenSpecChangeAdapter

pi_platform/adapters/html/
  html_adapter.py           # HTML SourceAdapter (stdlib html.parser)

pi_platform/adapters/pdf/
  pdf_adapter.py            # planned Phase 2+ slot; not populated

pi_platform/adapters/openapi/
  openapi_adapter.py        # planned Phase 2+ slot; not populated

pi_platform/adapters/java/
  parser_subprocess.py      # default JavaParserPort impl
                           # (tree-sitter-java MIT
                           # out-of-process subprocess)
  java_structured_adapter.py
                           # SourceAdapter for Java source code
  jar_adapter.py            # SourceAdapter for JAR artifacts
  maven_adapter.py          # SourceAdapter for pom.xml
  gradle_adapter.py         # SourceAdapter for build.gradle(.kts)

pi_platform/adapters/openspec/
  openspec_change_adapter.py
                           # SourceAdapter for openspec/ + emits
                           # Requirement, Specification,
                           # OpenSpecChange entities plus SATISFIES,
                           # PART_OF, IMPLEMENTED_BY relations
```

### Class / port / exception summary

| Path | Primary symbols |
|---|---|
| `pi_platform/ports/ingest/pipeline_driver.py` | `PipelineDriverPort`, `PipelineReport`, `StageOutcome`, `StageContext`, `CancellationToken`, `StageError`, `StageErrorCategory` (`transient` / `permanent` / `configuration_error` / `cancelled`) |
| `pi_platform/ports/ingest/source_adapter.py` | `SourceAdapterPort`, `SourceContentFamily` enum (`MARKDOWN` / `HTML` / `PLAIN_TEXT` / `JAVA_SOURCE` / `JAR` / `MAVEN_POM` / `GRADLE_BUILD` / `OPENAPI` / `OPENSPEC` / `PDF` / `OFFICE`), `SourceAdapterRegistry` |
| `pi_platform/ports/ingest/chunker.py` | `ChunkerPort`, `ChunkerRegistry` |
| `pi_platform/ports/ingest/context_enricher.py` | `ContextEnricherPort`, `EnrichmentLayer` (`DETERMINISTIC` / `DOMAIN_RULE` / `OPTIONAL_LLM`) |
| `pi_platform/ports/ingest/java_parser.py` | `JavaParserPort`, `JavaParseRequest`, `JavaParseResult` |
| `pi_platform/ports/ingest/local_source_inbox_scanner.py` | `LocalSourceInboxScannerPort`, `SourcePromotionPolicy` enum (`LOCAL_ONLY` / `REFERENCE` / `SNAPSHOT`) |
| `pi_platform/core/ingest/pipeline_driver.py` | `LocalPipelineDriver` (re-exported through the port) |
| `pi_platform/core/ingest/local_source_inbox_scanner.py` | `LocalSourceInboxScanner` (re-exported through the port) |
| `pi_platform/adapters/java/parser_subprocess.py` | `TreeSitterJavaSubprocess` (default `JavaParserPort` impl), `JavaParserLifecycle` (start / version / cleanup), `JavaParserTimeout` (60 s) |
| `pi_platform/adapters/ingest/local_pipeline_driver.py` | `LocalPipelineDriver` (default `PipelineDriverPort` impl) |
| `pi_platform/adapters/ingest/layered_context_enricher.py` | `LayeredContextEnricher` (default `ContextEnricherPort` impl) |
| `pi_platform/adapters/fs/local_source_adapter.py` | `LocalSourceAdapter` (default `SourceAdapterPort` impl for Markdown / HTML / plain text) |
| `pi_platform/adapters/openspec/openspec_change_adapter.py` | `OpenSpecChangeAdapter` (SourceAdapter + entity emit) |

Exception hierarchy:

- `StageError` (parent) — `transient`, `permanent`,
  `configuration_error`, `cancelled`;
- `JavaParserError` (parent) — `JavaParserMissing`,
  `JavaParserTimeout`, `JavaParserVersionMismatch`,
  `JavaParserCorruptOutput`;
- `LocalSourceInboxError` (parent) — `UnknownSource`,
  `PromotionDenied`, `InvalidPolicy`;
- `SourceAdapterError` (parent) — `UnsupportedFamily`,
  `AdapterMissing`, `AdapterCorruptOutput`.

### Stage sequence and per-stage idempotency

The `PipelineDriver` runs the five documented stages in order:

1. **Parse** — `SourceAdapterRegistry.resolve(source)` returns the
   registered `SourceAdapter`; the adapter produces
   `Document + Section[]` plus the unchanged `Source` whose
   `contentHash` is the SHA-256 hex digest of the source bytes;
2. **Chunk** — `ChunkerRegistry.resolve(content_family)` returns the
   registered `Chunker`; the chunker produces `Sequence[Chunk]` with
   `parentId`/`childIds` populated;
3. **Enrich** — `ContextEnricherRegistry.resolve(content_family)`
   returns the registered `ContextEnricher`; the enricher produces
   `Sequence[ContextualChunk]` with the three-layer metadata;
4. **Emit** — the driver emits `Entity`, `Relation` and `Evidence`
   records (the Phase 3 `GraphPort` interface exists as a Phase 1
   placeholder; this change does NOT implement the graph but
   produces the records through the documented port surface);
5. **Store** — the driver hands `Chunk`, `ContextualChunk`, `Entity`,
   `Relation`, `Evidence` records to the runtime cache through the
   Phase 1 `RuntimeCachePort` interface (a Phase 1 placeholder).
   Stage 5 is the cross-branch-reuse cache lookup; it MUST check
   the cache by content address before invoking the next stage.

Per-stage idempotency: every stage's output is keyed by its
SHA-256 hex digest. The driver checks the runtime cache for the
content address before invoking a stage and reuses the cached
artefact when present. The chunk `parentId`/`childIds` invariant
is validated by the Phase 1 round-trip test; the new cross-branch
reuse test extends the invariant to the cache.

Stage error handling:

- `transient` errors retry up to 3 times with exponential back-off
  bounded by a per-stage timeout (default 60 s, configurable per
  stage);
- `permanent` errors abort the source (mark
  `KnowledgeState.UNKNOWN`) and continue with the next source;
- `configuration_error` errors abort the entire pipeline and refuse
  to process the next source. The driver MUST surface the
  configuration error in the `PipelineReport` so the operator can
  inspect it;
- `cancelled` errors are raised when the `CancellationToken` is
  set; the driver MUST flush in-progress chunk records before
  returning.

### SourceAdapter registry and per-family adapters

`SourceAdapterRegistry` lives in
`pi_platform/ports/ingest/source_adapter.py` and maps
`SourceContentFamily` to a registered `SourceAdapterPort`
implementation. The default registrations are:

- `MARKDOWN` → `MarkdownAdapter`
- `HTML` → `HtmlAdapter`
- `PLAIN_TEXT` → `LocalSourceAdapter` (fallback)
- `JAVA_SOURCE` → `JavaStructuredAdapter`
- `JAR` → `JarAdapter`
- `MAVEN_POM` → `MavenAdapter`
- `GRADLE_BUILD` → `GradleAdapter`
- `OPENSPEC` → `OpenSpecChangeAdapter`
- `PDF` / `OPENAPI` / `OFFICE` → none (not populated in this
  change; the registry returns `AdapterMissing` for these families)

Every adapter that depends on a third-party library MUST declare
the dependency in
`distribution/licenses/dependency-inventory.json` with an SPDX
identifier and pass the Phase 1 `license-gate` before the adapter
is registered. The Phase 1 `LicenseGate` rejects activation when
the SPDX entry is missing or marked `review-required` without an
acceptance token.

### Chunker strategies

`ChunkerRegistry` lives in `pi_platform/ports/ingest/chunker.py` and
maps `SourceContentFamily` to the registered `ChunkerPort`
implementation. The default strategies:

- `MARKDOWN` → `MarkdownChunker` — splits on heading hierarchy;
  paragraphs below 4 KiB become one chunk; oversized paragraphs
  split at the nearest sentence boundary;
- `HTML` → `HtmlChunker` — splits on `<h1>`-`<h6>`, `<section>`,
  `<article>` boundaries;
- `PLAIN_TEXT` → `PlainTextChunker` — paragraph-boundary fallback;
- `JAVA_SOURCE` → delegated to `JavaStructuredAdapter` (one
  class-level chunk, one method-level chunk per method);
- `OPENSPEC` → delegated to `OpenSpecChangeAdapter` (one chunk per
  `## Requirement` block).

The chunker contract:

- every `Chunk` has a `parentId` and (for non-leaf chunks) a
  non-empty `childIds`;
- `Chunk.id` is the SHA-256 hex digest of `rawText` +
  `sourceReference` + `parentId` so identifiers are stable across
  branches;
- the parent-link invariant is validated by
  `tests/test_canonical_roundtrip.py`; the Phase 1 round-trip test
  remains the canonical guard against hierarchy regressions.

### ContextEnricher three-layer strategy

`ContextEnricherPort` lives in
`pi_platform/ports/ingest/context_enricher.py`. The default
`LayeredContextEnricher` adapter lives in
`pi_platform/adapters/ingest/layered_context_enricher.py` and
implements the three documented layers:

1. **Deterministic metadata layer** — fills every §23 field whose
   value can be derived from the source bytes (documentId, version,
   language, section, module, className, requirementId, validFrom,
   validTo, gitCommit, sourcePath, page, line, contentHash). This
   layer NEVER invents authoritative identifiers, versions, dates
   or security classifications (§22.3 contract);
2. **Domain-rule layer** — applies the
   `project-context.yaml:ingest.domainRules` list to the
   deterministic `Metadata`. Each rule is a YAML entry mapping a
   path glob or content-family cue to deterministic metadata
   augmentations. The default rules ship with this change
   (e.g. `path: pi_platform/adapters/java/** → businessDomain =
   STRUCTURED_CODE_INTELLIGENCE, system = PI_PLATFORM`);
3. **Optional small LLM layer** — disabled by default; when
   enabled, binds to the Phase 5 `LocalLLMPort` placeholder and
   emits a `pi_assumption` block carrying candidate entities and
   relations. The layer NEVER authoritatively populates any field
   covered by the deterministic layer; LLM-suggested values are
   tagged `KnowledgeState.ASSUMPTION`. The LLM layer is stubbed
   in this change; the Phase 5 implementation provides the
   binding.

The `ContextualChunk` round-trip is validated by the Phase 1
`tests/test_canonical_roundtrip.py`. The new
`tests/test_content_address_cross_branch.py` extends the
property-based assertion to two enricher runs over the same
chunk.

### LocalSourceInboxScanner and policy contract

`LocalSourceInboxScanner` lives in
`pi_platform/core/ingest/local_source_inbox_scanner.py` and
implements the documented `LOCAL_ONLY` / `REFERENCE` / `SNAPSHOT`
policy:

- `LOCAL_ONLY` — parse and index locally; never commit the source
  bytes or a canonical snapshot;
- `REFERENCE` — parse and index locally; persist only the
  provenance / reference metadata;
- `SNAPSHOT` — parse and index locally; normalise the source into
  an approved canonical representation and copy it into
  `project-knowledge/sources/<source-id>/`.

The default `project-context.yaml` sets the inbox default to
`LOCAL_ONLY` and documents the per-path override map. The new
`adr.0007-phase-2-inbox-policy-default` locks the default
(`LOCAL_ONLY`) and the override resolution rule (longest matching
glob wins; ties broken by sort ascending by glob string).

The scanner records the policy in `Source.metadata` so downstream
stages (chunking, enrichment, graph emission) can branch on the
policy without re-reading `project-context.yaml`. The
deleted-file invalidation flow marks derived chunks as
`KnowledgeState.STALE` per §55 freshness contract.

### OpenSpecChangeAdapter

`OpenSpecChangeAdapter` lives in
`pi_platform/adapters/openspec/openspec_change_adapter.py`. The
adapter reads `openspec/specs/` and `openspec/changes/` and
produces the §16 entity catalogue (`Requirement`, `Specification`,
`OpenSpecChange`, `ArchitectureDecision`, `Component`) plus the
`SATISFIES`, `PART_OF`, `IMPLEMENTED_BY`, `DOCUMENTED_BY` relations.

The adapter delegates Markdown parsing to the shared
`MarkdownAdapter` (no duplication) and YAML parsing to the Phase 1
`canonical.okf` frontmatter helper (no duplication). The adapter
emits the §53 traceability chain
`Business Requirement → OpenSpec Change → Specification → Architecture
Decision → Component → Implementation → Test` and surfaces missing
implementation / test nodes as `KnowledgeState.ASSUMPTION` entities
linked by a `PENDING` relation.

The archive subtree under `openspec/changes/archive/` is skipped
from the active `OpenSpecChange` list; archived spec deltas appear
with `status="archived"` so the Wiki can link to the historical
spec.

### Structured code and JAR dependency intelligence

Java parser library selection (the design candidate from
`prepare-phase-2-ingestion/design.md` is unchanged):

- `tree-sitter-java` (MIT) is invoked as an out-of-process
  subprocess from
  `pi_platform/adapters/java/parser_subprocess.py`;
- the subprocess lifecycle (start, version, cleanup, error
  recovery, 60 s timeout) is owned by `parser_subprocess.py`. The
  subprocess is process-local; the adapter keeps one subprocess per
  project version and restarts it on version change;
- the rejected alternatives (`javalang` MIT, `javaparser`
  Apache-2.0, native `javap`/`jdeps` shell-out) are documented in
  `adr.0006-phase-2-parser-selection.md`;
- the dependency is recorded in
  `distribution/licenses/dependency-inventory.json` with the SPDX
  identifier `Apache-2.0` and passes `LicenseGate` before the
  adapter is registered. If the parser binary is missing and
  `project-context.yaml:javaParser.required=true`, the adapter
  raises `JavaParserMissing` (a `configuration_error` category in
  the PipelineDriver stage error classification).

Adapter lifecycle ownership:

- `JavaStructuredAdapter` (class / method / annotation / JPA /
  test extraction) is owned by the
  `structured-code-intelligence` capability;
- `JarAdapter` (JAR coordinates + classes + signatures + inherited
  types + resources + public APIs) is owned by the
  `jar-dependency-intelligence` capability;
- `MavenAdapter` (`pom.xml` dependency graph) and `GradleAdapter`
  (`build.gradle(.kts)` dependency graph) are owned by the
  `jar-dependency-intelligence` capability;
- the parser subprocess lifecycle (start, version, cleanup, error
  recovery) is owned by
  `pi_platform/adapters/java/parser_subprocess.py`.

If the `tree-sitter-java` binary is unavailable at test time
(typical for CI without the `tree-sitter` system package), the
adapter falls back to a pure-Python "degraded mode" that records
`KnowledgeState.ASSUMPTION` for the parse results and emits the
metadata-only fields. The degraded mode is exercised in
`tests/test_platform_phase2.JavaStructuredAdapterTests`.

### Content-addressed processing cross-branch reuse test

`pi_platform.core.canonical.content_address.content_address(...)`
already exists (Phase 1). The Phase 2 capability
`content-addressed-processing` extends the contract to runtime
cache reuse across branches and adds the property-based
cross-branch reuse test in
`tests/test_content_address_cross_branch.py`.

The test:

- generates 100 random `Chunk`, `Entity` and `Relation` instances
  per value type with shuffled insertion order;
- simulates two Git branches by computing the same artefact's
  content address twice in independent random contexts;
- asserts that the two content addresses are equal and the
  runtime cache reports a single cache hit;
- asserts that the Phase 1 round-trip test
  `tests/test_canonical_roundtrip.py` continues to pass
  byte-for-byte (the cross-branch test imports the Phase 1
  round-trip test as a guard).

The implementation change ships the test alongside the Phase 2
chunker and enricher adapters so a green run of the cross-branch
test is the canonical guard against the regressions §13
documents.

### Per-test file list

The new regression suite is split into two files:

- `tests/test_platform_phase2.py` — one test class per scenario
  named after the scenario, mirroring the Phase 1
  `tests/test_platform_phase1.py` convention. Coverage matrix
  (from `prepare-phase-2-ingestion/tasks.md`):

  | Test class | Capability / scenario |
  |---|---|
  | `PipelineDriverTests` | `ingestion-pipeline-driver` (5 stages) |
  | `GitAdapterTests` | `git-version-aware-runtime` (Phase 1) plus `libgit2-or-cli` decision (Phase 2 task 46) |
  | `ContentAddressedProcessingTests` | `content-addressed-processing` |
  | `ContentAddressCrossBranchTests` | cross-branch reuse property test wrapper (also covered by `tests/test_content_address_cross_branch.py`) |
  | `SourceAdapterTests` | `document-source-adapters` |
  | `LocalSourceInboxScannerTests` | `local-source-inbox` core behaviour |
  | `LocalSourceInboxScannerSpecTests` | `local-source-inbox` spec scenarios |
  | `OpenSpecChangeAdapterTests` | `openspec-change-adapter` |
  | `JavaStructuredAdapterTests` | `structured-code-intelligence` |
  | `JarAdapterTests` | `jar-dependency-intelligence` JAR extraction |
  | `MavenGradleAdapterTests` | `jar-dependency-intelligence` Maven/Gradle |
  | `ChunkerTests` | `semantic-structural-chunking` |
  | `ContextEnricherTests` | `context-enrichment` |

- `tests/test_content_address_cross_branch.py` — the
  property-based cross-branch reuse test (task 47 / 57).

### CLI surface

The Phase 1 `python -m pi_platform.cli` subcommands
(`init-project`, `hydrate`, `materialise`, `license-gate`,
`okf-validate`, `version-identity`, `wal-recover`, `health`) are
unchanged. This change adds exactly one new subcommand,
`ingest-sources`, that wires the default `LocalPipelineDriver` and
`LocalSourceInboxScanner`:

```
python -m pi_platform.cli ingest-sources \
    --target <path> [--policy LOCAL_ONLY|REFERENCE|SNAPSHOT] \
    [--source <path> ...] [--recursive] [--dry-run]
```

The subcommand is registered in
`pi_platform/cli/main.py` alongside the existing subcommands and
exits non-zero when the PipelineDriver reports a
`configuration_error`.

### Container / launcher

`Containerfile` is updated to install the new Python packages
that are part of this change. The Java parser subprocess is
intentionally NOT bundled into the container image: the parser
binary is fetched at runtime if `project-context.yaml` configures
it, and the adapter falls back to degraded mode if the binary is
absent. The PDF / OpenAPI adapters are not populated in this
change, so their dependencies do NOT land in the Containerfile.

## Affected modules / interfaces

| Module / path | Phase | Touched by |
|---|---|---|
| `pi_platform/ports/ingest/` (new) | 2 | PipelineDriver, SourceAdapter, Chunker, ContextEnricher, JavaParser, LocalSourceInboxScanner ports |
| `pi_platform/core/ingest/` (new) | 2 | PipelineDriver, LocalSourceInboxScanner core implementations |
| `pi_platform/adapters/ingest/` (new) | 2 | LocalPipelineDriver, MarkdownChunker, HtmlChunker, PlainTextChunker, LayeredContextEnricher default adapters |
| `pi_platform/adapters/fs/local_source_adapter.py` (new) | 2 | default Markdown / HTML / plain text SourceAdapter |
| `pi_platform/adapters/markdown/markdown_adapter.py` (new) | 2 | shared Markdown parser |
| `pi_platform/adapters/html/html_adapter.py` (new) | 2 | HTML SourceAdapter (stdlib html.parser) |
| `pi_platform/adapters/pdf/pdf_adapter.py` (planned, not populated) | 2+ | PDF SourceAdapter (Phase 2+) |
| `pi_platform/adapters/openapi/openapi_adapter.py` (planned, not populated) | 2+ | OpenAPI SourceAdapter (Phase 2+) |
| `pi_platform/adapters/java/` (new) | 2 | `parser_subprocess`, `java_structured_adapter`, `jar_adapter`, `maven_adapter`, `gradle_adapter` |
| `pi_platform/adapters/openspec/openspec_change_adapter.py` (new) | 2 | OpenSpec Change Adapter |
| `pi_platform/cli/main.py` (extend) | 2 | add `ingest-sources` subcommand |
| `tests/test_platform_phase2.py` (new) | 2 | per-adapter / per-chunker / per-enricher regression suite |
| `tests/test_content_address_cross_branch.py` (new) | 2 | property-based cross-branch reuse test |
| `distribution/licenses/dependency-inventory.json` (extend) | 2 | SPDX-tracked entry for `tree-sitter-java` MIT (only); PDF / OpenAPI libs not added |
| `openspec/CURRENT.md` (extend) | 2 | add the nine Phase 2 capabilities under "Project product capabilities" |
| `openspec/changes/plan-v0-8-platform-architecture/tasks.md` (extend) | 2 | flip tasks 45-60 to `[x]` (this change performs the flip in the plan change before archive) |
| `.ai/wiki/modules/ingest.md` (new) | 2 | Phase 2 module map |
| `.ai/wiki/interfaces/source-adapters.md` (new) | 2 | SourceAdapter port + registry |
| `.ai/wiki/interfaces/chunker.md` (new) | 2 | Chunker port + per-family strategies |
| `.ai/wiki/interfaces/enrichment.md` (new) | 2 | ContextEnricher port + three-layer strategy |
| `.ai/wiki/adr/0006-phase-2-parser-selection.md` (new) | 2 | ADR recording the `tree-sitter-java` choice |
| `.ai/wiki/adr/0007-phase-2-inbox-policy-default.md` (new) | 2 | ADR locking the default policy |
| `.ai/wiki/architecture/platform-overview.md` (update) | 2 | Phase 2 module map |
| `.ai/wiki/architecture/system-overview.md` (update) | 2 | Phase 2 ingestion pipeline reference |
| `.ai/wiki/glossary/platform.md` (update) | 2 | new vocabulary |
| `.ai/wiki/glossary/domain.md` (update) | 2 | cross-links |
| `.ai/wiki/project/project-map.md` (update) | 2 | new module folders |
| `.ai/wiki/project/implementation-roadmap.md` (update) | 2 | flip Phase 2 row |
| `.ai/wiki/INDEX.md` (update) | 2 | new entries |
| `Containerfile` (extend, only if Phase 2 dependencies land) | 2 | install new Python packages whose SPDX entry passes LicenseGate |

The Phase 1 ports in `pi_platform/ports/__init__.py` stay
language-neutral; no new port acquires a Java-runtime dependency.
Java-specific parsing is supplied as an adapter under
`pi_platform/adapters/java/`.

## Data / persistence / concurrency impact

### Data flow

The `PipelineDriver` is a pure coordinator: it does not own a
runtime DB. Data flows:

```
Source → SourceAdapter → (Document, Section[])
         ↓
       Chunker → Sequence[Chunk]
         ↓
       ContextEnricher → Sequence[ContextualChunk]
         ↓
       Graph emission (Phase 3 GraphPort placeholder) → Entity/Relation/Evidence
         ↓
       RuntimeStore write (Phase 3 RuntimeStorePort placeholder) → cached at content address
```

The runtime cache is owned by the Phase 3 `RuntimeStore`. Phase 2
only contracts the cache key (SHA-256 hex digest of the canonical
JSON) and the cross-branch reuse semantics through a Phase 1
`RuntimeCachePort` interface (a placeholder that this change wires
to an in-memory map for testing; the Phase 3 implementation
provides the persistent index).

### Persistence

- canonical knowledge still lives under `project-knowledge/` per
  the Phase 1 `project-knowledge-repository-layout` spec;
- `SourcePromotionPolicy.SNAPSHOT` sources land in
  `project-knowledge/sources/<source-id>/`;
- the runtime cache lives under `.project-intelligence-cache/` and
  is owned by the Phase 3 `RuntimeStore` (out of scope here);
- the per-project advisory file lock from
  `pi_platform/core/sync/project_lock.py` is reused by the Phase 2
  driver; no new lock primitive is introduced.

### Concurrency

- the driver serialises ingestion per target project via the
  Phase 1 advisory file lock;
- multiple drivers MAY run in parallel against different target
  projects;
- the parser subprocess (`tree-sitter-java`) is process-local and
  does not share state with other invocations; the adapter keeps
  one subprocess per project version and restarts it on version
  change.

### Cancellation

- the driver observes a `CancellationToken` passed at construction;
- the token is propagated to every stage through the same
  `StageContext`;
- cancellation flushes in-progress chunk records before returning
  and records a stage-error event with category `cancelled`.

## Compatibility and migration

- the Phase 1 round-trip test in `tests/test_canonical_roundtrip.py`
  MUST continue to pass after Phase 2 introduces the chunkers,
  enrichers and adapters (no schema breakage);
- the Phase 1 license gate MUST pass after the new dependency
  inventory entries (Java parser only; PDF / OpenAPI libraries
  not added in this change) land in
  `distribution/licenses/dependency-inventory.json`;
- the Phase 1 CLI (`init-project`, `hydrate`, `materialise`,
  `license-gate`, `okf-validate`, `version-identity`, `wal-recover`,
  `health`) is unchanged; Phase 2 adds a new `ingest-sources` CLI
  command but does not modify the existing ones;
- `openspec/CURRENT.md` is updated by this change to list the nine
  Phase 2 capabilities under "Project product capabilities";
- `plan-v0-8-platform-architecture/tasks.md` rows 45-60 are
  flipped to `[x]` by this change after the production code lands
  and `python harness.py check` is green.

No backward-compatibility flag is needed because the public
contracts (`Chunk`, `ContextualChunk`, `Entity`, `Relation`,
`Evidence`, `Metadata`) are unchanged from Phase 1. The new ports
(`SourceAdapter`, `Chunker`, `ContextEnricher`, `PipelineDriver`,
`JavaParser`, `LocalSourceInboxScanner`) are additive.

## Risks and rollback

Risks:

- choosing the wrong Java parser library could lock in a poor
  Java-syntax coverage. Mitigated by the
  `tree-sitter-java` design candidate documented in
  `adr.0006-phase-2-parser-selection.md` and the documented
  alternatives (`javalang`, `javaparser`, native `javap`/`jdeps`).
  The adapter falls back to degraded mode when the parser binary
  is missing so the pipeline never silently drops Java sources;
- accepting a GPL-family parser library by mistake would break the
  Phase 1 permissive license policy. Mitigated by requiring every
  new dependency to be SPDX-tracked and pass `LicenseGate` before
  the adapter is registered. The Phase 1
  `LicenseGateTests.test_gate_fails_on_unknown_license` and
  `test_gate_review_without_token_blocks_build` tests guard the
  inventory;
- the `tree-sitter-java` subprocess path must be present at
  runtime; missing the binary aborts the pipeline for Java
  sources. Mitigated by the §14 scenario `missing parser binary
  fails closed` (recorded as a `configuration_error` in
  `PipelineDriver.report`) and the degraded-mode fallback in the
  adapter;
- the `LocalSourceInboxScanner` deleting-source flow may
  prematurely mark `SNAPSHOT` sources as stale. Mitigated by the
  explicit rule that the canonical snapshot under
  `project-knowledge/sources/` is removed only by an explicit
  operator action;
- the cross-branch reuse test could over-cache and miss
  `Metadata`-only updates. Mitigated by the spec that
  `contentHash` is computed from the body without `metadata`,
  `entityIds`, `parentId`, `childIds`, and the metadata-only
  update path goes through the Phase 1 reconcile flow;
- the strict OpenSpec validator (CLI v1.4.0+) requires `MUST` or
  `SHALL` on the first non-blank, non-metadata line of every
  requirement body. The pre-flight patch recorded in
  `context-impact.md` adds the missing keyword to 10 Phase 1
  requirement first-lines (canonical + delta copies) and 4
  Phase 2 requirement first-lines so the strict validator passes
  for every current spec and change.

Rollback:

- after archive, the implementation change reverts cleanly with
  a single `git revert <commit>` that includes the archive
  promotion, the plan flip and the Wiki edits;
- the `prepare-phase-2-ingestion` change is archived alongside
  this change; re-archiving it back to active is safe because it
  has no production code, only the nine Phase 2 spec deltas;
- `openspec/CURRENT.md` reverts by removing the nine Phase 2
  capability rows;
- `plan-v0-8-platform-architecture/tasks.md` reverts by flipping
  tasks 45-60 back to `[ ]`;
- the Phase 1 public contracts are unchanged and the new ports
  / adapters are additive, so the rollback does not corrupt any
  external state. The Phase 1 round-trip test must remain green
  at every step.

## Implementation reconciliation and observed mismatches

The partial handoff had registered Java stubs, discarded section bodies, no emit/store
records and no cache short-circuit. This implementation completes those paths.
Sections retain body seed chunks; the final structural chunker returns new immutable
chunks. SourceParseResult includes the unchanged source and entity/relation/evidence
records. Document IDs equal source IDs. Metadata gains optional policy and extensions;
empty additions are omitted by canonical serialization, preserving existing Phase 1
bytes. This is an additive model extension, replacing the earlier claim that every
Metadata field remained unchanged.

The parser is a one-shot Python worker, not a persistent-per-project subprocess.
Pinned tree-sitter-java 0.23.5 and binding 0.25.2 are MIT, verified from release license
and installed distribution metadata; the earlier Apache-2.0 attribution was incorrect.
Both dependencies are inventoried and gated before registration. The default container
keeps the optional Java packages absent; derived images can install the java extra.
A missing optional parser yields metadata-only assumptions; required mode fails closed.

Phase 1's accepted text calls content_address the metadata-independent chunk helper,
but observed Phase 1 code/tests use chunk_content_address for that projection and
content_address for plain canonical mappings. Phase 2 preserves those helpers and
uses chunk_content_address for body reuse, SHA-256 canonical JSON for other records.
The original accepted Phase 1 text is retained; this discrepancy is explicit here and
in the ingestion Wiki rather than concealed by changing historical requirements.
Source-specific completion keys include URI, source bytes, metadata and pipeline
configuration. Body reuse cannot suppress metadata or provenance updates. Position
is included in structural IDs to distinguish repeated equal paragraphs in one section.
Minimum-byte merging never crosses a structural parent boundary and cannot enlarge a
chunk beyond the maximum; an isolated/terminal structural fragment may remain smaller.

The plan's task 48 lists PDF/office implementation, while this bounded change expressly
excludes PDF/OpenAPI/office libraries. The delivered task-48 document subset is Markdown,
HTML and plain text; those remaining adapters are recorded as later Phase 2+ work in
that checklist rather than claimed to exist. Runtime DB, vector embedding, sharded
storage and provider bindings remain later-phase work. The optional LLM layer requires
an explicit local binding and permission instead of emitting a fake provider result.
