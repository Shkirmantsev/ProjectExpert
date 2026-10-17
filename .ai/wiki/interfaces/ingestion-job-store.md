---
id: interfaces.ingestion-job-store
title: IngestionJobStorePort contract
kind: interfaces
status: active
summary: Resumable ingestion job state machine (PENDING, RUNNING, PAUSED, FAILED_RETRYABLE, FAILED_PERMANENT, COMPLETED, CANCELLED) and SQLite adapter for page-batched document ingestion.
sourceRefs:
  - pi_platform/ports/ingest/ingestion_job_store.py
  - pi_platform/adapters/runtime/sqlite_ingestion_job_store.py
  - pi_platform/core/canonical/document_graph.py
  - openspec/specs/2026-10-16-resumable-document-ingestion/spec.md
  - adr.0024-rich-document-graph-as-additive-submodel
maintenance:
  mode: authored
related:
  - architecture.rich-document-graph
  - interfaces.document-graph-store
  - interfaces.source-adapters
  - modules.ingest
---

# IngestionJobStorePort contract

`IngestionJobStorePort` (`pi_platform/ports/ingest/ingestion_job_store.py`) and `SqliteIngestionJobStore` (`pi_platform/adapters/runtime/sqlite_ingestion_job_store.py`) track per-revision ingestion checkpoints (`IngestionCheckpoint`) across `PENDING | RUNNING | PAUSED | FAILED_RETRYABLE | FAILED_PERMANENT | COMPLETED | CANCELLED`.

## Operations

- `create(checkpoint)` / `get(job_id)`
- `find_completed(source_id, revision_id, strategy_version)` — used by `PdfPrescanAdapter` / `DoclingPdfAdapter` to short-circuit already-ingested revisions.
- `mark_running(job_id)` / `mark_batch_done(job_id, page_range)` / `mark_failed(job_id, page_range, error, retryable)` / `mark_completed(job_id)`.

[Rich document graph](../architecture/rich-document-graph.md) ·
[DocumentGraphStorePort](document-graph-store.md)
