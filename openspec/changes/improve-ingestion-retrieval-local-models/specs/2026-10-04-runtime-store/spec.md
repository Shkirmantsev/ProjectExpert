# 2026-10-04-runtime-store Specification delta

Covers plan §16, §17.1, §22.

## ADDED Requirements

### Requirement: additive document graph, ingestion job, and vector record stores

The platform MUST define three additive, focused
ports on top of the existing `RuntimeStorePort`:

- `DocumentGraphStorePort` — for the rich document
  graph (`document_revisions`, `pages`,
  `document_elements`, `assets`, `table_cells`,
  `table_payloads`, `chunk_anchors`);
- `IngestionJobStorePort` — for resumable ingestion
  jobs (`ingestion_jobs`);
- `VectorRecordStorePort` — for embedding vector
  records (`embeddings`).

The SQLite adapters of these three ports MAY share the
same physical `runtime.db` but MUST be logically
decoupled from `RuntimeStorePort`. The existing
`runtime_entries` table MUST NOT be replaced and MUST
remain the home of the existing generic canonical
runtime objects.

#### Scenario: new stores do not affect existing tables

Given a hydrated `runtime.db` with only
`runtime_entries` content
When the platform initialises the new stores
Then the new tables are added
And the existing `runtime_entries` rows are not
rewritten.

#### Scenario: ingestion job survives a crash

Given an ingestion that commits batch 1
When the process crashes
Then the next ingestion run reads the
`IngestionJobStorePort`, finds the job in
`FAILED_RETRYABLE`, and resumes from `next_page`.

### Requirement: ANN index is a disposable derived artefact

The ANN index (USearch) MUST be a disposable derived
artefact under
`.project-intelligence-cache/indexes/<embedding_profile_hash>/`
and MUST be git-ignored. The platform MUST record the
`index_state` table with `embedding_profile_hash`,
`index_schema_version`, `source_generation`, and
`vector_count`. If any compatibility key changes, the
platform MUST rebuild the ANN from
`VectorRecordStorePort` without re-embedding.

#### Scenario: deleting the ANN does not require re-embedding

Given a populated `embeddings` table and a USearch ANN
namespace
When the operator deletes the ANN namespace
Then the platform rebuilds the ANN from
`VectorRecordStorePort` without re-running the
embedding model.

## MODIFIED Requirements

None. The existing runtime-store `Requirements` are
extended additively; their bodies are not rewritten.
