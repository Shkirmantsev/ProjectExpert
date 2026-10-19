# real-docling-pdf-adapter-and-hybrid-chunker Specification delta

Covers plan §45, §46, §47, §48, §49, §50, §71, §96 (PR 10 of §79).

## Purpose

Replace the synthesised Docling PDF stub with a real Docling
`DocumentConverter` and a real `HybridChunker` aligned to the active
embedding model tokenizer. Vendor types MUST NOT leak past the
adapter boundary. Page provenance, tables, figures, table-header
repetition and selective OCR MUST be preserved end to end.

## ADDED Requirements

### Requirement: real DocumentConverter

The platform MUST use the real `docling.document_converter.DocumentConverter`
to convert supported document inputs. The stub synthesised
`DoclingDocument` MUST NOT be present in any production code path.

#### Scenario: real DocumentConverter parses a PDF (verifies: real DocumentConverter)

Given a native-text PDF input
When the adapter processes the source
Then a real `DocumentConverter` is invoked
And the resulting document graph contains one element per Docling
structural unit
And the persisted document graph is the platform neutral type, not a
Docling type

### Requirement: vendor boundary isolation

All Docling vendor types MUST be mapped at the adapter boundary into
the platform's neutral document graph (DocumentRevision, Page,
DocumentElement, TableGrid, Figure, AssetRef, IngestionCheckpoint).
No Docling type MAY be referenced by name in any module outside
`pi_platform/adapters/pdf/`.

#### Scenario: vendor types do not leak past the adapter boundary (verifies: vendor boundary isolation)

Given the platform neutral canonical module
`pi_platform/core/canonical`
When a static scan of every Python module under that directory runs
Then no import statement references any submodule of the
`docling` package
And no docstring or annotation in the canonical module mentions a
Docling type by name

### Requirement: real HybridChunker with model-aligned tokenizer

The chunker MUST be the real `docling.chunking.HybridChunker`
configured with a Hugging Face tokenizer aligned with the active
embedding model identifier. The tokenizer alignment MUST follow the
official Docling guidance for the active model.

#### Scenario: HybridChunker aligns with active model tokenizer (verifies: real HybridChunker with model-aligned tokenizer)

Given the active embedding model is EmbeddingGemma 2 512d
When a document is chunked
Then the chunker uses the EmbeddingGemma 2 tokenizer
And the resulting chunks respect the tokenizer's token budget
And the chunker is the real `docling.chunking.HybridChunker`, not a
local re-implementation

### Requirement: model-independent document graph

The persisted document graph MUST remain model-independent. Switching
the embedding model MUST NOT require rewriting the canonical
document graph. If model-specific token splitting is required, the
split MUST live in a runtime projection linked back to the stable
canonical element or chunk.

#### Scenario: switching embedding model does not rewrite the document graph (verifies: model-independent document graph)

Given a parsed document graph for a PDF
When the operator switches the embedding model from EmbeddingGemma 2
to Qwen3-Embedding-0.6B
Then the persisted document graph is unchanged
And only runtime segments or vector records differ

### Requirement: optional EmbeddingSegment projection

When the active embedding model has a different tokenizer than the
document graph expects, the platform MUST introduce an
`EmbeddingSegment` runtime projection carrying segment identifier,
canonical chunk identifier, embedding profile identity, text,
token count and ordinal. The projection MUST index segments and
resolve them back to canonical chunks before context assembly.

#### Scenario: segments resolve back to canonical chunks (verifies: optional EmbeddingSegment projection)

Given the active embedding model has a different token budget than
the canonical chunker used during ingestion
When the platform indexes a new document
Then one EmbeddingSegment is recorded per chunk
And each segment carries the canonical chunk identifier and profile
identity
And retrieval resolves every hit back to its canonical chunk before
context assembly

### Requirement: selective OCR and resource bounding

The adapter MUST honour the existing selective OCR policy and MUST
support page batching, memory bounding and resume after failure.
Each page MUST carry provenance (page number, source family,
source path) and table headers MUST be repeated across chunks.

#### Scenario: table header is repeated across chunks (verifies: selective OCR and resource bounding)

Given a multi-page PDF with a table
When the adapter chunks the document
Then the table header text is repeated in every chunk that
contains a row of the table

#### Scenario: page provenance is preserved (verifies: selective OCR and resource bounding)

Given a 100-page PDF
When the adapter finishes ingestion
Then every document element carries the source page number and the
source family

#### Scenario: resume after failure continues from the last checkpoint (verifies: selective OCR and resource bounding)

Given the adapter failed at page 42 of 100 during ingestion
When the operator restarts ingestion
Then the adapter resumes at page 42 or later
And the pages before the failure remain valid

### Requirement: licenses inventoried

The platform MUST list Docling and any model asset downloaded for
OCR or layout in the dependency license inventory with the correct
SPDX identifier. The platform MUST NOT assume the Docling package
license automatically covers downloaded model weights.

#### Scenario: Docling and OCR assets are listed with SPDX identifiers (verifies: licenses inventoried)

Given the operator runs the license inventory scan
When the scan reports the document processing dependencies
Then the `docling` and `docling-core` packages appear with their
correct SPDX identifier
And every model asset downloaded for OCR or layout appears as a
distinct inventory entry with its own SPDX identifier
And no record claims the Docling package license automatically
covers model weights
