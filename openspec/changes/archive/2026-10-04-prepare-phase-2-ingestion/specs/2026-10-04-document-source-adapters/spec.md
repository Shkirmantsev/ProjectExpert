# document-source-adapters Specification delta

Covers architecture section §3 (Supported Knowledge Sources), §8.2
(Enrich Runtime Knowledge) and §13 (Content-Addressed Processing).
Defines the `SourceAdapter` port that every content-type adapter
implements, plus the language-neutral default `LocalSourceAdapter`
family.

The Phase 1 `canonical-knowledge-schema`, `git-version-aware-runtime`,
`bidirectional-canonical-runtime-sync` and `license-governance`
capabilities provide the `Source`, `Document`, `Section`, `Chunk`,
`Entity`, `Relation`, `Evidence`, `Metadata` and `ProjectVersion`
value types that this spec builds on.

## ADDED Requirements

### Requirement: SourceAdapter port

The platform MUST expose a `SourceAdapter` port in
`pi_platform/ports/ingest/source_adapter.py`. Every content-type
adapter MUST implement this port. The port MUST accept a `Source`
plus the Phase 1 `ProjectVersion` and `WorkingTreeOverlay` and MUST
return:

- a `Document` carrying the document id, title and ordered `Section`
  records;
- the `Source` value type unchanged (the adapter may extend its
  `metadata` map but MUST NOT mutate the `id`, `uri`, `family` or
  `contentHash` fields);
- the SHA-256 hex digest of the source bytes (the `Source.contentHash`)
  for the runtime cache key.

The adapter MUST be language-neutral at the boundary. Any library the
adapter depends on MUST be SPDX-tracked and pass the Phase 1 license
gate; libraries live as adapter-internal dependencies, not as ports.

#### Scenario: SourceAdapter returns Document + Section[]

Given a `Source` referencing a Markdown document with two `#` level-1
headings
When any `SourceAdapter` is invoked against the source
Then the adapter returns one `Document` whose `id` equals the
`Source.id`
And the `Document.sections` array contains one `Section` per heading
in document order
And the adapter returns the `Source` unchanged in its
`id`/`uri`/`family`/`contentHash` fields
And the returned `Document.metadata.contentHash` equals the
`Source.contentHash`.

### Requirement: LocalSourceAdapter default

The platform MUST ship a `LocalSourceAdapter` in
`pi_platform/adapters/fs/local_source_adapter.py` that handles the
plain-text content family (Markdown, HTML, plain text). The default
adapter MUST:

- read the source bytes from the local filesystem through the
  Phase 1 `LocalFilesystemAdapter` so the adapter does not introduce a
  separate I/O contract;
- delegate Markdown extraction to a `MarkdownAdapter` so the Markdown
  parsing is shared with `openspec-change-adapter` (no duplication);
- delegate HTML extraction to an `HtmlAdapter` that emits the same
  `Document + Section[]` shape;
- emit `Section` records whose `level` follows the source's heading
  depth (Markdown `#` → level 1, `##` → level 2, etc.) and whose
  `parentId` follows the heading hierarchy.

#### Scenario: MarkdownAdapter produces heading-aware sections

Given a Markdown source with `# Title`, `## Section A`, `## Section B`
and a paragraph under each section
When the `LocalSourceAdapter` is invoked
Then the adapter returns a `Document` with `title="Title"`
And the `Document.sections` array contains three `Section` records:
`Title` (level 1, no parent), `Section A` (level 2, parentId=title)
and `Section B` (level 2, parentId=title).

#### Scenario: LocalSourceAdapter returns plain-text sections

Given a plain-text source with no Markdown or HTML markers
When the `LocalSourceAdapter` is invoked
Then the adapter returns a `Document` whose single `Section`
carries `heading=""`, `level=0` and the full source text as the
section body
And no other adapter is invoked.

### Requirement: Source content family registry

The platform MUST expose a `SourceContentFamily` enum with the
documented families:

- `markdown`, `html`, `plain_text` (handled by `LocalSourceAdapter`);
- `pdf` (handled by the planned `PdfAdapter`);
- `openapi` (handled by `OpenApiAdapter`);
- `java_source`, `java_bytecode` (delegated to
  `structured-code-intelligence` and `jar-dependency-intelligence`);
- `maven_pom`, `gradle_build` (delegated to
  `jar-dependency-intelligence`);
- `openspec_spec`, `openspec_change`, `adr` (delegated to
  `openspec-change-adapter`);
- `local_inbox` (delegated to `local-source-inbox`).

The platform MUST expose a `SourceAdapterRegistry` that maps each
family to the registered adapter and raises `configuration_error`
when a source's family has no registered adapter.

#### Scenario: registry raises on unknown family

Given a `Source` with `family="unsupported_xyz"`
When the registry is asked to resolve the adapter
Then the registry raises `configuration_error` naming the missing
family
And the driver refuses to continue with the next source
consistent with the `ingestion-pipeline-driver` error contract.

### Requirement: planned content-type adapters

The platform MUST document the planned adapters in
[`design.md`](../../design.md) so the future
`implement-phase-2-ingestion` change can implement them behind the
language-neutral `SourceAdapter` port:

- `PdfAdapter` for `pdf` — planned dependency: `pdfplumber` (MIT) or
  `pypdf` (BSD-3-Clause). The license must pass the Phase 1 license
  gate; SPDX identifier recorded in
  `distribution/licenses/dependency-inventory.json` before activation;
- `OpenApiAdapter` for `openapi` — planned dependency: `openapi-
  schema-validator` (Apache-2.0) or `prance` (BSD-3-Clause). The
  adapter parses OpenAPI 3.x documents and emits `Api`, `Endpoint`
  and `Parameter` entities plus `EXPOSES`, `PARAMETER` relations;
- the office-document adapter (`docx`, `xlsx`, `pptx`) — planned
  dependency: `python-docx` (MIT), `openpyxl` (MIT), `python-pptx`
  (MIT). The license must pass the Phase 1 license gate.

The design records each adapter's port binding, dependency licence
and lifecycle ownership. No office or PDF library is bundled by this
spec; the libraries are added by the future
`implement-phase-2-ingestion` change after each SPDX-tracked
inventory entry passes `LicenseGate`.

#### Scenario: planned PdfAdapter is documented

Given a `Source` with `family="pdf"`
And a registry that has no `PdfAdapter` registered
When the operator queries the planned adapter list
Then the registry returns the documented list including `PdfAdapter`
with dependency `pdfplumber` MIT (or `pypdf` BSD-3-Clause)
And the registry does not auto-install the dependency
And the registry log entry records the planned SPDX identifier.

### Requirement: Source license contract

Every adapter MUST declare its dependency SPDX identifiers in
`distribution/licenses/dependency-inventory.json` before the
`SourceAdapterRegistry` registers it. An adapter whose dependencies
do not pass `LicenseGate` MUST NOT be activated, and the
`init-project` CLI MUST report the missing entry on the next run.

#### Scenario: missing SPDX blocks adapter activation

Given a `PdfAdapter` whose dependency `pdfplumber` is not present in
`distribution/licenses/dependency-inventory.json`
When `LicenseGate.run(...)` runs during `init-project`
Then the gate returns `(False, [finding])` with `decision="review"`
And the activation step refuses to register `PdfAdapter`.

## Phase 2 task coverage

The change lists Phase 2 task 48 (document source adapters: Markdown,
HTML, plain text, PDF, supported office documents) and the
`document-source-adapters` slice of task 58 (Phase 2 spec scenarios)
and task 59 (focused regression tests per adapter).

Out of scope:

- the `PdfAdapter`, `OpenApiAdapter` and office-document adapter
  implementations — these land in the future
  `implement-phase-2-ingestion` change;
- the Java adapters — these land under
  `structured-code-intelligence` and `jar-dependency-intelligence`;
- the OpenSpec adapters — these land under `openspec-change-adapter`.