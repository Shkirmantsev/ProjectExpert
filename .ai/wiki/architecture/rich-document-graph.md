---
id: architecture.rich-document-graph
title: Rich document graph as an additive canonical submodel
kind: architecture
status: active
summary: Additive ProjectExpert-neutral document graph (DocumentRevision, Page, DocumentElement, SourceAnchor, AssetRef, TableGrid, IngestionCheckpoint) projected into Document/Section/Chunk with page-level provenance and resumable batched PDF ingestion.
sourceRefs:
  - pi_platform/core/canonical/document_graph.py
  - pi_platform/core/canonical/value_types.py
  - pi_platform/adapters/pdf/docling_pdf_adapter.py
  - pi_platform/adapters/pdf/prescan.py
  - pi_platform/adapters/pdf/ocr_policy.py
  - pi_platform/adapters/pdf/assets.py
  - pi_platform/adapters/pdf/docling_chunker.py
  - openspec/specs/2026-10-16-rich-document-graph/spec.md
  - openspec/specs/2026-10-16-resumable-document-ingestion/spec.md
  - adr.0024-rich-document-graph-as-additive-submodel
maintenance:
  mode: authored
related:
  - adr.0024-rich-document-graph-as-additive-submodel
  - interfaces.document-graph-store
  - interfaces.ingestion-job-store
  - interfaces.source-adapters
  - modules.ingest
---

# Rich document graph as an additive canonical submodel

The v0.8 refinement adds a neutral rich-document submodel in `pi_platform/core/canonical/document_graph.py` so PDF and structured documents preserve page geometry, tables, figures, formulas, OCR provenance, and per-element source anchors without breaking the existing `Document` / `Section` / `Chunk` contracts.

## Core types

- `DocumentRevision` — deterministic `revision_id = sha256(file bytes)`, `source_id`, `strategy_version`, `page_count`, `language`.
- `Page` — page number, dimensions, `native_text_present`, `ocr_used`, `language_hint`.
- `DocumentElement` & `ElementKind` — `HEADING`, `PARAGRAPH`, `LIST`, `TABLE`, `FIGURE`, `FORMULA` with deterministic `element_id` and non-authoritative `semantic_key`.
- `SourceAnchor` — attached to `Chunk.anchors` (`revision_id`, `page`, `element_id`, `bbox`, `line`, `asset_id`).
- `TableGrid` — canonical row/column grid plus repeated-header Markdown serialization when split.
- `AssetRef` — content-addressed figure/asset record stored in local CAS (`FigureAssetAdapter`) with `MENTIONS`, `CAPTIONED_BY`, `ON_PAGE`, `IN_SECTION` relations.
- `IngestionCheckpoint` & `IngestionState` — resumable page-window state persisted via `IngestionJobStorePort`.

[ADR 0024](../adr/0024-rich-document-graph-as-additive-submodel.md) ·
[DocumentGraphStorePort](../interfaces/document-graph-store.md) ·
[IngestionJobStorePort](../interfaces/ingestion-job-store.md)
