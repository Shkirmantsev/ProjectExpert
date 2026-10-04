# semantic-structural-chunking Specification delta

Covers architecture sections §19 (Semantic and Structural Chunking),
§20 (Hierarchical Knowledge) and §21 (Chunk Model). Defines the
`Chunker` strategy that selects structural boundaries per content
family and preserves the parent-link invariant validated by
`tests/test_canonical_roundtrip.py`.

The Phase 1 `canonical-knowledge-schema` capability defines the
`Chunk` value type with `parentId`/`childIds` fields; this spec
defines the chunker that emits those fields per content family.

## ADDED Requirements

### Requirement: Chunker port

The platform MUST expose a `ChunkerPort` in
`pi_platform/ports/ingest/chunker.py`. Every content-type chunker
MUST implement this port and MUST accept the `Document` and `Section`
records produced by a `SourceAdapter` plus the SHA-256 hex digest
of the source bytes. The chunker MUST return a `Sequence[Chunk]`
ordered by document order and MUST populate every `Chunk.parentId`
and `Chunk.childIds` so the hierarchy invariant
(`Document > Section > Chunk`) is preserved.

#### Scenario: ChunkerPort returns an ordered Chunk list

Given a `Document` with two `Section` records `s-1` and `s-2` and a
chunker invoked on the document
Then the chunker returns a `Sequence[Chunk]` whose order matches the
document order
And every chunk carries a non-null `parentId` referring to either
`Document.id` or `Section.id`
And every `Section`'s `chunks` array is populated by reference (the
chunk's `id` appears in `Section.chunks[*].id`).

### Requirement: chunker selection by content family

The platform MUST select the chunker strategy from a documented
registry:

- `MarkdownChunker` — splits on Markdown headings; one `Chunk` per
  `Section` body when the section is short enough (<= 4 KiB), else
  splits on paragraph boundaries with `parentId` referring to the
  enclosing section;
- `HtmlChunker` — splits on `<h1>`-`<h6>`, `<section>`, `<article>`
  boundaries; `parentId` refers to the enclosing section element;
- `JavaChunker` (delegated to `structured-code-intelligence`) —
  one `Chunk` per top-level class declaration; child chunks per
  method or constructor declaration; `parentId` links the method
  chunk to the class chunk; class chunk links to the enclosing
  compilation unit `Document`;
- `OpenSpecChunker` (delegated to `openspec-change-adapter`) —
  one `Chunk` per `## Requirement` block; `parentId` links the
  requirement chunk to the `Specification` chunk;
- `RequirementIdChunker` — splits on requirement identifiers such as
  `REQ-001`, `SHALL-002`, `MUST-003`; `parentId` links the requirement
  chunk to the enclosing section;
- `ProtocolMessageChunker` — one `Chunk` per protocol message
  definition; `parentId` links the message chunk to the enclosing
  protocol document section;
- `TableChunker` — one `Chunk` per Markdown / HTML / CSV table; the
  table's header row plus a content fingerprint are preserved;
- `ArchitectureUnitChunker` — one `Chunk` per architecture unit
  (ADR, component, module, layer); `parentId` links the chunk to
  the enclosing `Document` and `childIds` link to dependent units;
- `PlainTextChunker` (default fallback) — splits on paragraph
  boundaries when no structural cue exists.

The platform MUST raise `configuration_error` when a content family
has no registered chunker and MUST NOT default to `PlainTextChunker`
silently when a structural chunker is expected.

#### Scenario: MarkdownChunker splits on headings

Given a Markdown document with one `## Section A` heading and two
paragraphs under it
When the `MarkdownChunker` is invoked
Then the chunker returns one `Chunk` per paragraph
And both chunks carry `parentId=<section-A-id>`
And both chunks carry `metadata.section="Section A"`.

#### Scenario: JavaChunker splits classes and methods

Given a Java source file with one class `Foo` containing two methods
`bar` and `baz`
When the `JavaChunker` is invoked
Then the chunker returns one class-level `Chunk` labelled `Foo` with
`parentId=<document-id>`
And two method-level chunks labelled `bar` and `baz` with
`parentId=<foo-chunk-id>` and `childIds=[]` on the class chunk
expanded to include the two method chunk ids.

### Requirement: parent-link invariant

The `ChunkerPort` MUST emit a `Chunk.parentId` for every chunk and
MUST populate `Chunk.childIds` on every non-leaf chunk. The invariant
MUST hold after a canonical round trip so two equivalent chunk lists
serialise to byte-identical canonical files. The Phase 1 round-trip
test in `tests/test_canonical_roundtrip.py` MUST continue to pass
after Phase 2 introduces the chunkers.

#### Scenario: round-trip preserves parent links

Given a chunk list produced by any chunker with non-empty
`parentId`/`childIds` fields
When the chunk list is serialised to canonical JSON and parsed back
Then the parsed chunk list carries the same `parentId`/`childIds`
values
And the chunk hierarchy `Document > Section > Chunk` is preserved.

### Requirement: chunk size policy

The chunker MUST respect the documented chunk size budget
(`project-context.yaml:ingest.chunking.maxChunkBytes`, default
4 KiB) and the documented minimum chunk size (default 256 bytes).
Chunks smaller than the minimum MUST be merged with the next chunk
in document order; chunks larger than the maximum MUST be split at
the nearest structural boundary below the maximum. The chunker MUST
record in operational log entries when a split or merge occurs and
the chunk's `metadata` MUST carry the policy decision.

#### Scenario: oversized chunk is split at structural boundary

Given a section whose text exceeds the maximum chunk size and
contains two paragraph boundaries
When the chunker is invoked
Then the chunker emits two chunks sized at or below the maximum
And each chunk's `metadata.mergeOrSplit` records the split decision
and the boundary used.

### Requirement: chunker stable identifiers

The chunker's `Chunk.id` MUST be the SHA-256 hex digest of the
canonical JSON serialization of the chunk's `rawText` concatenated
with the chunk's `sourceReference` and `parentId` so that the chunk
identifier is stable across runs and across Git branches. Two
chunkers MUST NOT produce the same identifier for different content.

#### Scenario: identical content produces identical chunk id

Given two `MarkdownChunker` runs over the same Markdown file on
different Git branches
When the chunker emits a chunk for the same paragraph
Then both runs produce the same `Chunk.id`
And the runtime cache records a single entry under that id.

## Phase 2 task coverage

The change lists Phase 2 task 54 (semantic/structural chunker
selecting boundaries per §19) and the
`semantic-structural-chunking` slice of task 58 (Phase 2 spec
scenarios) and task 59 (focused regression tests per chunker).

Out of scope:

- the embedding model that consumes the chunks (Phase 4 task 70);
- the dense ANN index over the chunks (Phase 4 task 71);
- the reranker that consumes the chunks (Phase 4 task 74).