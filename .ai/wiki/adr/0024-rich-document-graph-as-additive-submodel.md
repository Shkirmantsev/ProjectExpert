---
id: adr.0024-rich-document-graph-as-additive-submodel
title: Rich document graph as an additive submodel
kind: adr
status: accepted
date: 2026-10-15
summary: PDF and Office documents get a neutral additive rich document graph (DocumentRevision, Page, DocumentElement, SourceAnchor, AssetRef, TableGrid, IngestionCheckpoint) layered on top of the existing canonical model. The generic public surface (Document / Section / Chunk / Entity / Relation / Evidence) is unchanged; the rich submodel is projected into it. Docling types must not leak past the adapter boundary.
related:
  - adr.0004-ports-and-adapters-extension-style
  - adr.0008-embedded-storage-selection
  - interfaces.source-adapters
  - modules.runtime-store
  - modules.ingest
sourceRefs:
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#3.2
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#19
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#20
  - ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md#21
  - openspec/specs/2026-10-16-rich-document-graph/spec.md
  - openspec/specs/2026-10-16-resumable-document-ingestion/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-document-source-adapters/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-canonical-knowledge-schema/spec.md
  - openspec/changes/archive/2026-10-16-improve-ingestion-retrieval-local-models/specs/2026-10-04-ingestion-pipeline-driver/spec.md
  - pi_platform/core/canonical/document_graph.py
  - pi_platform/adapters/pdf/docling_pdf_adapter.py
  - pi_platform/adapters/pdf/docling_chunker.py
  - pi_platform/ports/runtime/document_graph_store.py
  - pi_platform/ports/ingest/ingestion_job_store.py
maintenance:
  mode: authored
---

# ADR 0024 — Rich document graph as an additive submodel

## Context

The v0.8 canonical model
(`Source`, `Document`, `Section`, `Chunk`, `Entity`, `Relation`,
`Evidence`) is sufficient for Markdown and source code but
insufficient for PDF and Office documents. It loses page
geometry, reading order, tables, figures, captions, formulas,
page-level OCR provenance, and binary asset references.

The plan (§3.2) calls for an additive rich document graph that
captures this structure without replacing the existing public
model. The v0.8 ingestion pipeline already flattens imported
PDFs directly to sections and chunks, which is the source of
the gap.

A second consideration: the existing `SourceContentFamily.PDF`
is declared in the source adapter port but the
`pi_platform/adapters/pdf/` package is empty (only
`__init__.py`). The old `PLANNED_ADAPTERS` entry referenced a
`pdfplumber` plan; the v0.8 refinement supersedes that with a
Docling-based adapter that is production-shaped and STUB-only
until the real `docling` binding is wired in a follow-up.

## Decision

Add an additive neutral rich document graph in
`pi_platform/core/canonical/document_graph.py`:

- `DocumentRevision` — a specific byte-content version of a
  source, identified by `revision_id`
- `Page` — a single page within a `DocumentRevision`
- `DocumentElement` — a discriminated union of `Heading`,
  `Paragraph`, `List`, `Table`, `Figure`, `Formula`
- `ElementKind` — the enum of element kinds
- `SourceAnchor` — an exact pointer to a page element
- `AssetRef` — a binary asset reference (image, attached file)
- `TableGrid` — a structured table with `headers`, `rows`,
  and a Markdown serialisation
- `IngestionCheckpoint` — the resumable state of a single
  ingestion run
- `IngestionState` — the job state enum
  (`PENDING | RUNNING | PAUSED | FAILED_RETRYABLE |
  FAILED_PERMANENT | COMPLETED | CANCELLED`)

The `Chunk` value type gains an additive `anchors:
Sequence[SourceAnchor]` field. Legacy chunks (canonical
knowledge schema v1) have an empty anchor list and continue to
deserialise and participate in retrieval unchanged.

`KNOWLEDGE_SCHEMA_VERSION` is bumped from `"0.7.0"` to
`"0.8.0"`. The migration is additive: v1 records remain valid;
new fields default to empty.

The Docling PDF adapter
(`pi_platform/adapters/pdf/docling_pdf_adapter.py`) is
production-shaped: it implements `SourceAdapterPort` for the
PDF family, runs a page-windowed batched parse
(`DEFAULT_PAGE_BATCH_SIZE=32`,
`DEFAULT_BOUNDARY_CONTEXT_PAGES=1`), commits per batch to the
ingestion job store, and projects the rich document graph into
the existing generic public model
(`Document` / `Section` / `Chunk`).

The Docling types live only inside the adapter module
(`_DoclingDocument`, `_DoclingTextItem`, `_DoclingTableItem`,
`_DoclingFigureItem` are private to the file). The
`DoclingMapper` is the only place where Docling-side structure
is decoded; the rest of the platform sees only the neutral
canonical types.

The Docling HybridChunker
(`pi_platform/adapters/pdf/docling_chunker.py`) is the
production STUB for the PDF family chunker: it implements
`ChunkerPort` and delegates to `PlainTextChunker` so the PDF
family reuses the existing chunker pipeline. The real
`docling.HybridChunker` binding is a follow-up: swap the
internal chunker without changing the public surface.

Selective OCR (plan §21.4) is owned by
`SelectiveOcrPolicy` in `pi_platform/ports/ingest/ocr_engine.py`:
native_text_present → no OCR; already_ocr_used → no OCR;
no native text → OCR with the candidate engine (Tesseract
default, PaddleOCR fallback). The `TesseractOcrAdapter` is the
production STUB; the real `pytesseract` binding ships in a
follow-up.

Figures and binary assets are first-class:
`FigureAssetAdapter` writes image bytes to the local CAS
under `.project-intelligence-cache/assets/<byte_hash>` and
records an `AssetRef` in the `DocumentGraphStorePort` so the
retrieval pipeline can join the figure to the chunk that
mentions it.

## Determinism

`revision_id = sha256(file bytes)` is computed by the
prescan. `element_id = sha256(revision_id | page | element
kind | canonical(geometry) | content hash | ordinal)[:32]`
is computed by `DoclingMapper`. The `semantic_key` is a
non-authoritative cross-revision key
(`heading_path / element_kind / local_ordinal`) that lets the
platform identify a moved or edited section across revisions
without replacing the exact hash identity.

A crash at page 417 does not invalidate completed batches.
The next call resumes at `next_page` and re-parses only the
owned page window. The `IngestionJobStorePort` records
completed ranges in JSON-encoded form and merges overlapping
ranges on each `mark_batch_done` call.

## Schema version bump

The bump from `0.7.0` to `0.8.0` is additive. The migration
`migration_v2_add_document_graph_tables(db)` and
`migration_v2_add_ingestion_jobs_table(db)` are
`CREATE TABLE IF NOT EXISTS` and idempotent. Existing
`runtime_entries` rows are untouched.

## Consequences

Positive:

- PDF and Office documents retain page geometry, reading
  order, tables, figures, captions, formulas, OCR
  provenance, and binary asset references.
- The generic public surface (`Document` / `Section` /
  `Chunk` / `Entity` / `Relation` / `Evidence`) is unchanged;
  the rich submodel is projected into it.
- Docling types do not leak past the adapter boundary; the
  core knows only ProjectExpert-neutral types.
- 600-page documents are processed in bounded page windows
  with neighbour context; the platform never holds the entire
  document in memory.
- A crash at page 417 does not invalidate completed batches;
  the next call resumes from the last completed range.
- The `IngestionJobStorePort` is the durable record of
  ingestion progress; `find_completed` short-circuits
  repeated runs.
- The Docling HybridChunker (when the real binding lands)
  composes hierarchical document boundaries with
  tokenizer-aware splits without changing the existing
  chunker pipeline.

Negative:

- The Docling adapter, the HybridChunker, and the
  Tesseract OCR engine are STUBs in this commit. The real
  bindings ship in follow-ups that add the `documents`
  optional dependency group to `pyproject.toml` and
  `distribution/licenses/model-licenses.json`.
- The `pi_platform/adapters/pdf/` package now contains four
  production-shaped STUB modules. The shape is correct; the
  third-party dependency is the only thing missing.
- A schema version bump requires a knowledge-schema
  migration; legacy records continue to work, but the
  migration is part of the v2 → v3 → … evolution.

## Rollback

Disable the PDF family via the `SourceAdapterRegistry`:
`registry.unregister(SourceContentFamily.PDF)`. The platform
falls back to the legacy "PDF declared but no adapter"
behaviour. The schema migration is reversible: drop the new
tables and decrement `KNOWLEDGE_SCHEMA_VERSION` to `"0.7.0"`.
No canonical records are rewritten.
