# 2026-10-04-ingestion-pipeline-driver Specification delta

Covers plan §21, §22.

## ADDED Requirements

### Requirement: bind the PDF family to the resumable job model

The ingestion pipeline driver MUST bind
`SourceContentFamily.PDF` to the new resumable job
model defined in the `resumable-document-ingestion`
delta. The driver MUST use the
`IngestionJobStorePort` for state and the
`DocumentGraphStorePort` for canonical knowledge
persistence. The driver MUST NOT bypass these stores
to write directly to the underlying SQLite tables.

#### Scenario: PDF family uses the new job model

Given a target project with a PDF source
When the platform schedules ingestion
Then the driver creates a job in
`IngestionJobStorePort` and persists canonical
artefacts through `DocumentGraphStorePort`
And no direct writes to `runtime.db` bypass these
ports.

## MODIFIED Requirements

None. The existing ingestion-pipeline-driver
`Requirements` are extended additively; their bodies
are not rewritten.
