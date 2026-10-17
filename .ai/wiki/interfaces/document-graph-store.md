---
id: interfaces.document-graph-store
title: DocumentGraphStorePort contract
kind: interfaces
status: active
summary: Persistence port and SQLite adapter for the additive rich-document submodel (document_revisions, pages, document_elements, assets, table_cells, table_payloads, chunk_anchors).
sourceRefs:
  - pi_platform/ports/runtime/document_graph_store.py
  - pi_platform/adapters/runtime/sqlite_document_graph_store.py
  - pi_platform/core/canonical/document_graph.py
  - openspec/specs/2026-10-16-rich-document-graph/spec.md
  - adr.0024-rich-document-graph-as-additive-submodel
maintenance:
  mode: authored
related:
  - architecture.rich-document-graph
  - interfaces.ingestion-job-store
  - interfaces.runtime-store
  - modules.runtime-store
---

# DocumentGraphStorePort contract

`DocumentGraphStorePort` (`pi_platform/ports/runtime/document_graph_store.py`) and `SqliteDocumentGraphStore` (`pi_platform/adapters/runtime/sqlite_document_graph_store.py`) persist the additive rich-document graph tables (`document_revisions`, `pages`, `document_elements`, `assets`, `table_cells`, `table_payloads`, `chunk_anchors`) in SQLite without altering existing `runtime_entries` rows.

## Operations

- `put_revision` / `get_revision`
- `put_page` / `list_pages`
- `put_element` / `list_elements`
- `put_table` / `get_table`
- `put_asset` / `get_asset` / `list_assets_for_revision`
- `put_chunk_anchors` / `get_chunk_anchors`
- `commit_page_batch` — transactional batch commit used by resumable PDF ingestion.

[Rich document graph](../architecture/rich-document-graph.md) ·
[IngestionJobStorePort](ingestion-job-store.md) ·
[ADR 0024](../adr/0024-rich-document-graph-as-additive-submodel.md)
