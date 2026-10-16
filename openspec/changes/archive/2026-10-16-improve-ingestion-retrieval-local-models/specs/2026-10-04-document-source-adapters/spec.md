# 2026-10-04-document-source-adapters Specification delta

Covers plan §3.1, §21, §21.1, §21.2, §21.3, §21.4, §21.5,
§21.6.

## ADDED Requirements

### Requirement: Docling-based PDF source adapter

The platform MUST expose a `DoclingPdfAdapter` that
implements the existing `SourceAdapterPort` and binds the
`SourceContentFamily.PDF` family. The adapter MUST
delegate to Docling only at the adapter boundary; Docling
types MUST NOT appear in the core.

The old `PLANNED_ADAPTERS.pdfplumber` reference MUST be
replaced by the Docling-based PDF family in
`pi_platform/ports/ingest/source_adapter.py`.

#### Scenario: PDF source family binds to the new adapter

Given a target project with `SourceContentFamily.PDF`
sources
When the platform schedules ingestion
Then the new `DoclingPdfAdapter` is the active adapter
And the old `pdfplumber` reference is no longer in
`PLANNED_ADAPTERS`.

#### Scenario: Docling types do not leak into the core

Given the `DoclingPdfAdapter`
When the platform calls the adapter and ingests a
sample PDF
Then the canonical artifacts contain only
ProjectExpert-neutral types
And no Docling type appears in the canonical store.

### Requirement: PDF ingestion is resumable

The `DoclingPdfAdapter` MUST run the prescan →
batched parse → job checkpoint → selective OCR →
tables / figures / assets pipeline defined in the
`resumable-document-ingestion` delta. The adapter MUST
honour the `IngestionJobStorePort` for state and the
`DocumentGraphStorePort` for canonical knowledge
persistence.

#### Scenario: ingestion resumes after a crash

Given an ingestion that has committed pages 1–416
When the process crashes at page 417
Then the next ingestion run starts at page 417
And pages 1–416 are not re-parsed.

## MODIFIED Requirements

None. The existing document-source-adapters
`Requirements` are extended additively; their bodies
are not rewritten.
