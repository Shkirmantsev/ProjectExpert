# 2026-10-04-semantic-structural-chunking Specification delta

Covers plan §3.3, §8, §8.1, §9.

## ADDED Requirements

### Requirement: additive ChunkerContext fields

`ChunkerContext` MUST gain the additive optional fields
`target_tokens`, `max_tokens`, `min_tokens`,
`tokenizer_id`, and `merge_peers`. The existing
`max_chunk_bytes` field MUST be preserved as a hard
safety limit. Existing chunkers that do not consume the
new fields MUST continue to produce byte-identical
chunks.

#### Scenario: legacy ChunkerContext produces the same chunks

Given a ChunkerContext with only `max_chunk_bytes`
When an existing structural chunker runs
Then the chunker produces the same chunks as before
And no accepted requirement body is violated.

#### Scenario: token-aware ChunkerContext splits oversized chunks

Given a ChunkerContext with
`target_tokens = 768`, `max_tokens = 900`,
`min_tokens = 160`, and a
`tokenizer_id` bound to a real tokenizer
When the chunker encounters a 1500-token section
Then the chunker splits it into two chunks at a
semantic boundary
And each chunk is within the configured token budget.

### Requirement: token budget normalizer composes after structural strategies

The platform MUST expose a `TokenBudgetNormalizer` that
composes after a `SemanticBoundaryStrategy`. The
normalizer MUST:

1. split oversized candidates at token boundaries,
   preserving structure when possible;
2. merge compatible peer candidates when below
   `min_tokens`;
3. never violate `max_chunk_bytes`.

Existing structural chunkers (`PlainTextChunker`,
`RequirementChunker`, `ProtocolChunker`, `TableChunker`,
`ArchitectureChunker`, Java AST chunkers) MUST NOT be
replaced by a single generic model chunker. They MUST
be wrapped by the `TokenBudgetNormalizer` in the
ingestion pipeline driver.

#### Scenario: chunker composition is structural → tokenizer

Given a Markdown document
When the pipeline runs
Then the structural boundaries are produced by
`PlainTextChunker`
And the `TokenBudgetNormalizer` afterwards enforces
the configured token budget
And the result respects both the structural and
token constraints.

#### Scenario: Java code remains AST-based

Given a Java method that exceeds the configured
`max_tokens`
When the pipeline runs
Then the chunker first respects the method boundary
And only if the method itself exceeds the budget does
the normalizer split on statement / block boundaries
And the AST symbol identity is preserved.

### Requirement: Docling HybridChunker for PDF

The platform MUST expose a `DoclingHybridChunker`
adapter that wraps Docling's `HybridChunker` only where
a `DoclingDocument` exists. The adapter MUST implement
the existing `ChunkerPort` so the pipeline driver
needs no special-case code path for PDF. The adapter
MUST NOT be used for Java, OpenSpec, or JAR chunking.

#### Scenario: PDF chunking uses Docling HybridChunker

Given a PDF source ingested through
`DoclingPdfAdapter`
When the platform chunks the document
Then the chunker is `DoclingHybridChunker` (Docling
boundary + tokenizer-aware split)
And the resulting chunks carry
`SourceAnchor` entries for each page element.

## MODIFIED Requirements

None. The existing semantic-structural-chunking
`Requirements` are extended additively; their bodies
are not rewritten.
