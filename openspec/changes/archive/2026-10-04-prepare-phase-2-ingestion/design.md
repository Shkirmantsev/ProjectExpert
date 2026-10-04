# Design — prepare-phase-2-ingestion

## Current state

The repository contains the v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)),
the Phase 1 foundation change archived at
[`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`](../../archive/2026-10-04-implement-phase-1-foundation/),
the active `plan-v0-8-platform-architecture` change that owns the
Phase 2–10 task ordering, and the five Phase 1 capabilities under
`openspec/specs/2026-10-04-*/`:

- `project-knowledge-repository-layout`
- `canonical-knowledge-schema`
- `git-version-aware-runtime`
- `bidirectional-canonical-runtime-sync`
- `license-governance`

The Phase 1 product source tree is in place at `pi_platform/` with
the `core/{canonical,git,sync,licensing}` subpackages, the
`ports/__init__.py` aggregate, the `adapters/{fs,git}` default
adapters, the `runtime/` working knowledge cache scaffolding and
the `cli/` entry point exposing `init-project`, `hydrate`,
`materialise`, `license-gate`, `okf-validate`, `version-identity`,
`wal-recover` and `health`. The 155-test regression suite and the
`python harness.py check` gate are green.

The repository does not yet contain any Phase 2 production code
under `pi_platform/ingest/`, `pi_platform/ports/ingest/`,
`pi_platform/adapters/ingest/` or `pi_platform/adapters/java/`. No
Java parser library has been added to
`distribution/licenses/dependency-inventory.json`. The Phase 2 task
list (`tasks.md` rows 45–59) is still `[ ]` in the planning change.

## Proposed design

This change is a planning artifact: it ships no production code.
The design below describes the technical approach the future
`implement-phase-2-ingestion` change will implement, expressed as
module boundaries, port contracts, adapter composition, data flow,
concurrency, compatibility and risks. The design records the parser
library selection rationale and the cross-branch reuse test so the
implementation work has unambiguous technical contracts.

### PipelineDriver coordinator (§18)

The `PipelineDriver` lives in `pi_platform/core/ingest/
pipeline_driver.py` and exposes a `PipelineDriverPort` abstract
class in `pi_platform/ports/ingest/pipeline_driver.py`. The default
`LocalPipelineDriver` adapter lives in
`pi_platform/adapters/ingest/local_pipeline_driver.py`.

Stage boundaries:

1. **Parse** — `SourceAdapterRegistry.resolve(source)` returns the
   registered `SourceAdapter`; the adapter produces `Document +
   Section[]` and the unchanged `Source`;
2. **Chunk** — `ChunkerRegistry.resolve(content_family)` returns the
   registered `Chunker`; the chunker produces `Sequence[Chunk]` with
   `parentId`/`childIds` populated;
3. **Enrich** — `ContextEnricherRegistry.resolve(content_family)`
   returns the registered `ContextEnricher`; the enricher produces
   `Sequence[ContextualChunk]` with the three-layer metadata;
4. **Emit** — the driver emits `Entity`, `Relation` and `Evidence`
   records to the Phase 3 `GraphPort` (out of scope here; Phase 3
   task 66 owns the graph implementation);
5. **Store** — the driver hands `Chunk`, `ContextualChunk`, `Entity`,
   `Relation`, `Evidence` records to the Phase 3 `RuntimeStorePort`
   (out of scope here; Phase 3 task 62 owns the runtime DB).

Stage error handling:

- the driver classifies exceptions as `transient`,
  `permanent`, `configuration_error` per the spec;
- `transient` errors retry up to 3 times with exponential back-off
  bounded by a per-stage timeout;
- `permanent` errors abort the source (mark
  `KnowledgeState.UNKNOWN`) and continue with the next source;
- `configuration_error` errors abort the entire pipeline and refuse
  to process the next source.

Per-stage idempotency:

- every stage's output is keyed by its SHA-256 hex digest;
- the driver checks the runtime cache for the content address before
  invoking a stage and reuses the cached artefact when present;
- the chunk `parentId`/`childIds` invariant is validated by the
  Phase 1 round-trip test so a re-run produces a byte-identical
  canonical chunk body.

Cancel propagation:

- the driver observes a `CancellationToken` passed at construction;
- the token is propagated to every stage through the same
  `StageContext`;
- cancellation flushes in-progress chunk records before returning
  and records a stage-error event with category `cancelled`.

### SourceAdapter port (§3 / §8.2)

`SourceAdapterPort` lives in
`pi_platform/ports/ingest/source_adapter.py`. Every content-type
adapter implements the port. The port returns
`(Document, Source)` plus the SHA-256 hex digest of the source bytes
as `Source.contentHash`. The port is language-neutral; any
library the adapter depends on is supplied as an adapter-internal
dependency and must be SPDX-tracked.

Default adapters shipped by the future implementation change:

- `LocalSourceAdapter` in
  `pi_platform/adapters/fs/local_source_adapter.py` (Markdown, HTML,
  plain text);
- `MarkdownAdapter` in
  `pi_platform/adapters/markdown/markdown_adapter.py` — shared with
  `OpenSpecChangeAdapter` so the Markdown parsing logic is not
  duplicated;
- `HtmlAdapter` in `pi_platform/adapters/markdown/html_adapter.py`
  (or `pi_platform/adapters/html/html_adapter.py` — the future
  change may collapse the markdown+html adapters into one module
  package);
- `PdfAdapter` in `pi_platform/adapters/pdf/pdf_adapter.py` —
  planned dependency `pdfplumber` (MIT) or `pypdf` (BSD-3-Clause);
- `OpenApiAdapter` in
  `pi_platform/adapters/openapi/openapi_adapter.py` — planned
  dependency `openapi-schema-validator` (Apache-2.0);
- `JavaStructuredAdapter` in
  `pi_platform/adapters/java/java_structured_adapter.py` — owned by
  the `structured-code-intelligence` capability;
- `JarAdapter` in `pi_platform/adapters/java/jar_adapter.py` —
  owned by the `jar-dependency-intelligence` capability;
- `MavenAdapter` in
  `pi_platform/adapters/java/maven_adapter.py` — owned by the
  `jar-dependency-intelligence` capability;
- `GradleAdapter` in
  `pi_platform/adapters/java/gradle_adapter.py` — owned by the
  `jar-dependency-intelligence` capability;
- `OpenSpecChangeAdapter` in
  `pi_platform/adapters/openspec/openspec_change_adapter.py` —
  owned by the `openspec-change-adapter` capability.

Dependency licenses (planned):

| Adapter | Dependency | License | LicenseGate action |
|---|---|---|---|
| `LocalSourceAdapter` | (stdlib only) | n/a | n/a |
| `MarkdownAdapter` | (stdlib only) | n/a | n/a |
| `HtmlAdapter` | `beautifulsoup4` (or stdlib `html.parser`) | MIT | allow |
| `PdfAdapter` | `pdfplumber` | MIT | allow |
| `PdfAdapter` (alt) | `pypdf` | BSD-3-Clause | allow |
| `OpenApiAdapter` | `openapi-schema-validator` | Apache-2.0 | allow |
| `OpenApiAdapter` (alt) | `prance` | BSD-3-Clause | allow |
| `JavaStructuredAdapter` | `tree-sitter-java` (out-of-process) | Apache-2.0 | allow |
| `JavaStructuredAdapter` (alt) | `javalang` (embedded) | MIT | allow |
| `JarAdapter` | stdlib `zipfile` + `javatools` (Apache-2.0) | Apache-2.0 | allow |
| `OpenSpecChangeAdapter` | (stdlib + Phase 1 OKF) | n/a | n/a |

Every dependency above must be added to
`distribution/licenses/dependency-inventory.json` with an SPDX
identifier before the adapter is registered. The Phase 1
`LicenseGate` blocks activation when the SPDX entry is missing or
marked `review-required` without an acceptance token.

### Chunker strategy (§19 / §20 / §21)

`ChunkerPort` lives in `pi_platform/ports/ingest/chunker.py`. The
chunker registry maps `SourceContentFamily` to the registered
`Chunker` strategy. The default strategies are:

- `MarkdownChunker` — splits on heading hierarchy; paragraphs
  below 4 KiB become one chunk; oversized paragraphs split at the
  nearest sentence boundary;
- `HtmlChunker` — splits on `<h1>`-`<h6>`, `<section>`, `<article>`
  boundaries;
- `JavaChunker` — delegated to `structured-code-intelligence`; one
  class-level chunk, one method-level chunk per method;
- `OpenSpecChunker` — delegated to `openspec-change-adapter`; one
  chunk per `## Requirement` block;
- `PlainTextChunker` — paragraph-boundary fallback.

The chunker contract:

- every `Chunk` has a `parentId` and (for non-leaf chunks) a
  non-empty `childIds`;
- `Chunk.id` is the SHA-256 hex digest of `rawText` +
  `sourceReference` + `parentId` so identifiers are stable across
  branches;
- the parent-link invariant is validated by
  `tests/test_canonical_roundtrip.py`; the Phase 1 round-trip test
  remains the canonical guard against hierarchy regressions.

### ContextEnricher three-layer strategy (§22 / §54 / §55)

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
   augmentations. The default rules ship with the future
   implementation change (e.g. `path psb/packing/** → businessDomain =
   PACKING, system = PSB`);
3. **Optional small LLM layer** — disabled by default; when
   enabled, binds to the Phase 5 `LocalLLMPort` and emits a
   `pi_assumption` block carrying candidate entities and relations.
   The layer NEVER authoritatively populates any field covered by
   the deterministic layer; LLM-suggested values are tagged
   `KnowledgeState.ASSUMPTION`.

The `ContextualChunk` round-trip is validated by the Phase 1
`tests/test_canonical_roundtrip.py`. The
`tests/test_content_address_cross_branch.py` test (added by the
future implementation change) extends the property-based assertion
to two enricher runs over the same chunk.

### LocalSourceInboxScanner and policy contract (§9.2)

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
  `project-knowledge/sources/`.

The default `project-context.yaml` will set the inbox default to
`LOCAL_ONLY` and document the per-path override map. The future
ADR `adr.phase-2-inbox-policy-default` will lock the default
(`LOCAL_ONLY`) and the override resolution rule (longest matching
glob wins; ties broken by sort ascending by glob string).

The scanner records the policy in `Source.metadata` so downstream
stages (chunking, enrichment, graph emission) can branch on the
policy without re-reading `project-context.yaml`. The deleted-file
invalidation flow marks derived chunks as `KnowledgeState.STALE` per
§55 freshness contract.

### OpenSpecChangeAdapter (§53)

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

### Structured code and JAR dependency intelligence (§14 / §15)

Java parser library selection:

- the design candidate is **`tree-sitter-java`** (Apache-2.0)
  invoked as an **out-of-process subprocess** from the Python
  adapter. The subprocess is owned by
  `pi_platform/adapters/java/parser_subprocess.py` and shells out
  to the `tree-sitter` CLI binary that ships with the
  `tree-sitter-java` package;
- the alternative is `javalang` (MIT) embedded as an in-process
  Python module, but it does not support the latest Java syntax
  features reliably. The future `ADR.phase-2-parser-selection`
  records the rationale (out-of-process subprocess, Apache-2.0,
  active maintenance, supports the latest Java syntax);
- the chosen dependency is recorded in
  `distribution/licenses/dependency-inventory.json` and passes
  `LicenseGate` before the adapter is registered.

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
  `pi_platform/adapters/java/parser_subprocess.py`. The subprocess
  timeout defaults to 60 s per the spec; the driver retries per the
  §18 error-handling contract.

### Content-addressed processing cross-branch reuse test (§13)

`pi_platform.core.canonical.content_address.content_address(...)`
already exists (Phase 1). The Phase 2 capability
`content-addressed-processing` extends the contract to runtime cache
reuse across branches and adds the property-based cross-branch reuse
test in `tests/test_content_address_cross_branch.py`.

The test:

- generates 100 random `Chunk`, `Entity`, `Relation` instances per
  value type with shuffled insertion order;
- simulates two Git branches by computing the same artefact's
  content address twice in independent random contexts;
- asserts that the two content addresses are equal and the runtime
  cache reports a single cache hit;
- asserts that the Phase 1 round-trip test
  `tests/test_canonical_roundtrip.py` continues to pass byte-for-
  byte.

The future implementation change adds the test alongside the Phase
2 chunker and enricher adapters so a green run of the cross-branch
test is the canonical guard against the regressions §13 documents.

## Affected modules / interfaces

| Module / path | Phase | Touched by |
|---|---|---|
| `pi_platform/ports/ingest/` (new) | 2 | PipelineDriver, SourceAdapter, Chunker, ContextEnricher, JavaParser, LocalSourceInboxScanner ports |
| `pi_platform/adapters/ingest/` (new) | 2 | LocalPipelineDriver, LayeredContextEnricher default adapters |
| `pi_platform/adapters/markdown/`, `pi_platform/adapters/html/` (new) | 2 | MarkdownAdapter, HtmlAdapter shared between LocalSourceAdapter and OpenSpecChangeAdapter |
| `pi_platform/adapters/java/` (new) | 2 | JavaStructuredAdapter, JarAdapter, MavenAdapter, GradleAdapter, parser_subprocess |
| `pi_platform/adapters/openspec/` (new) | 2 | OpenSpecChangeAdapter |
| `pi_platform/adapters/pdf/`, `pi_platform/adapters/openapi/` (planned, not by Phase 2) | 2+ | PdfAdapter, OpenApiAdapter |
| `pi_platform/core/ingest/` (new) | 2 | PipelineDriver, LocalSourceInboxScanner core implementations |
| `tests/test_content_address_cross_branch.py` (new) | 2 | property-based cross-branch reuse test |
| `tests/test_platform_phase2.py` (new) | 2 | per-adapter / per-chunker / per-enricher regression suite |
| `distribution/licenses/dependency-inventory.json` | 2 | SPDX-tracked entries for the chosen Java parser, optional PDF / OpenAPI libraries |
| `openspec/changes/prepare-phase-2-ingestion/` (new) | 0 | this change (planning only) |

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
       Graph emission (Phase 3 GraphPort) → Entity/Relation/Evidence
         ↓
       RuntimeStore write (Phase 3 RuntimeStorePort) → cached at content address
```

The runtime cache is owned by the Phase 3 `RuntimeStore`. Phase 2
only contracts the cache key (SHA-256 hex digest of the canonical
JSON) and the cross-branch reuse semantics.

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
  inventory entries (Java parser, optional PDF / OpenAPI libraries)
  land in `distribution/licenses/dependency-inventory.json`;
- the Phase 1 CLI (`init-project`, `hydrate`, `materialise`,
  `license-gate`, `okf-validate`, `version-identity`, `wal-recover`,
  `health`) is unchanged; Phase 2 MAY add a new
  `ingest-sources` CLI command but does not modify the existing
  ones;
- `openspec/CURRENT.md` is updated by the future
  `implement-phase-2-ingestion` change when the nine Phase 2 specs
  are adopted, not by this change;
- `openspec/CURRENT.md` lists the five Phase 1 capabilities; the
  Phase 2 capabilities will be added by the future implementation
  change.

No backward-compatibility flag is needed because the public
contracts (`Chunk`, `ContextualChunk`, `Entity`, `Relation`,
`Evidence`, `Metadata`) are unchanged from Phase 1. The new ports
(`SourceAdapter`, `Chunker`, `ContextEnricher`, `PipelineDriver`)
are additive.

## Risks and rollback

Risks:

- choosing the wrong Java parser library could lock in a poor
  Java-syntax coverage. Mitigated by documenting the
  `tree-sitter-java` candidate with the alternatives
  (`javalang`, `javaparser`, native `javap`/`jdeps`) and recording
  the rationale in the future `adr.phase-2-parser-selection`;
- accepting a GPL-family parser library by mistake would break the
  Phase 1 permissive license policy. Mitigated by requiring every
  new dependency to be SPDX-tracked and pass `LicenseGate` before
  the adapter is registered, and by running the Phase 1
  `LicenseGateTests.test_gate_fails_on_unknown_license` and
  `test_gate_review_without_token_blocks_build` tests;
- the `tree-sitter-java` subprocess path must be present at
  runtime; missing the binary aborts the pipeline for Java sources.
  Mitigated by the §14 scenario `missing parser binary fails
  closed`;
- the `LocalSourceInboxScanner` deleting-source flow may
  prematurely mark `SNAPSHOT` sources as stale. Mitigated by the
  explicit rule that the canonical snapshot under
  `project-knowledge/sources/` is removed only by an explicit
  operator action;
- the cross-branch reuse test could over-cache and miss
  `Metadata`-only updates. Mitigated by the spec that
  `contentHash` is computed from the body without `metadata`,
  `entityIds`, `parentId`, `childIds`, and the metadata-only
  update path goes through the Phase 1 reconcile flow.

Rollback:

- this change reverts cleanly by deleting
  `openspec/changes/prepare-phase-2-ingestion/` and the
  `.openspec.yaml` registration; the Phase 1 surface is unchanged;
- before the future `implement-phase-2-ingestion` change is
  adopted, there is no runtime artifact to roll back;
- after the future implementation change is adopted, the Phase 2
  code reverts by archiving the implementation change back to a
  Phase-2 pre-state and removing the new dependency inventory
  entries (the LicenseGate rejects activation when entries are
  missing).