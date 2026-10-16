# resumable-document-ingestion Specification delta

Covers plan §3.1, §21, §21.1, §21.2, §21.3, §21.4, §21.5,
§21.6, §22.

## Purpose

Define a resumable, batched, selectively-OCR'd PDF /
document ingestion pipeline behind the existing
`SourceAdapterPort` and the new `IngestionJobStorePort`,
`DocumentGraphStorePort`, and `OcrEnginePort`. The pipeline
must (a) skip work when the exact revision + ingestion
strategy already exist, (b) parse in bounded page windows
with neighbour context, (c) commit each batch
transactionally, (d) resume from the next page after a
crash, (e) prefer the native text layer over OCR, and
(f) treat tables and figures as first-class evidence with
asset CAS, captions, and graph relations.

## ADDED Requirements

### Requirement: prescan and short-circuit

The platform MUST execute a cheap prescan before any
expensive parse: hash the file, read the page count, read
the document metadata, sample the native text layer,
resolve the `revision_id`, and check `IngestionJobStorePort`
for a `COMPLETED` job with the same `revision_id` and
`strategy_version`. If such a job exists, the platform
MUST skip the expensive parse and return the existing
canonical artefacts unchanged.

#### Scenario: already-ingested revision is skipped

Given a PDF whose `revision_id` and `strategy_version`
match a `COMPLETED` job in `IngestionJobStorePort`
When the platform schedules a new ingestion
Then the prescan returns `SKIP` and the existing
canonical knowledge is not re-parsed.

#### Scenario: changed bytes create a new revision

Given a PDF whose bytes differ from the last ingested
revision
When the platform schedules a new ingestion
Then the prescan returns a new `revision_id` and the
full pipeline runs.

### Requirement: batched parse with page windows

The platform MUST parse the document in bounded page
windows of size `page_batch_size` (default 32) with
`boundary_context_pages` (default 1) neighbour pages as
read-only context. Each batch MUST commit to the
`DocumentGraphStorePort` transactionally. The platform
MUST persist only the owned page window; the neighbour
pages are not re-persisted.

#### Scenario: parse progress is committed per batch

Given a 600-page PDF and `page_batch_size: 32`
When the platform ingests the document
Then 19 batches are committed transactionally
And the platform never holds the entire 600-page
document in memory.

#### Scenario: crash at page 417 does not invalidate prior batches

Given an ingestion that has committed pages 1–416
When the process crashes at page 417
Then `IngestionJobStorePort` records the job as
`FAILED_RETRYABLE` with `next_page = 417`
And pages 1–416 remain in the canonical store
And a resume starts at page 417 without re-parsing
pages 1–416.

### Requirement: persistent ingestion job model

The platform MUST define `IngestionJobStorePort` with the
states `PENDING | RUNNING | PAUSED | FAILED_RETRYABLE |
FAILED_PERMANENT | COMPLETED | CANCELLED` and the
required fields `job_id`, `source_id`, `revision_id`,
`strategy_version`, `state`, `next_page`,
`completed_ranges`, `failed_range`, `error`,
`started_at`, `updated_at`.

The SQLite adapter MUST live in `runtime.db` and be
logically decoupled from the existing
`RuntimeStorePort` (plan §22).

#### Scenario: ingestion job state transitions

Given a freshly created job in `PENDING`
When the platform claims the job
Then the state becomes `RUNNING`
And `next_page` advances as each batch commits
And the state becomes `COMPLETED` once all pages are
processed.

### Requirement: selective OCR

The platform MUST run OCR only when needed. The OCR
engine is an adapter behind `OcrEnginePort`. The default
candidate is Tesseract; the optional fallback is
PaddleOCR; both are subject to the License Gate and are
pinned in `distribution/licenses/model-licenses.json`.

The platform MUST prefer the native text layer when
usable; OCR is used for image / bitmap regions or for
full pages when no native text exists.

#### Scenario: native-text pages are not OCRed

Given a PDF with a usable native text layer
When the platform ingests the document
Then `ocr_used = false` on every page
And no OCR engine is invoked.

#### Scenario: image-only pages are OCRed

Given a PDF page with no native text layer
When the platform ingests the document
Then `ocr_used = true` on that page
And the OCR engine returns text that participates in
the chunking and retrieval pipeline.

### Requirement: tables and figures as first-class evidence

Tables MUST be persisted in three views: structured
cells / rows / columns as the canonical structure; a
text / Markdown serialisation as the retrieval view; and
source provenance / caption / page geometry. When a
table is split, the header MUST be repeated.

Figures MUST be persisted as `AssetRef` records with
`page`, `bbox`, `caption`, `OCR_text` (if present),
nearby explanatory elements, and graph relations
`MENTIONS`, `CAPTIONED_BY`, `ON_PAGE`, `IN_SECTION`.
Image bytes MUST go to the local CAS by default.

#### Scenario: split table repeats header

Given a table that is split into two chunks
When the platform ingests the table
Then the second chunk's serialised Markdown repeats
the header row.

#### Scenario: figure chunk can resolve to original asset

Given a chunk that mentions a figure
When the platform retrieves the chunk
Then the chunk's `anchors` include the figure's
`asset_id` and `page`
And the CAS holds the figure bytes under that
`asset_id`.

## MODIFIED Requirements

None. The existing document-source-adapters and
ingestion-pipeline-driver `Requirements` are extended
additively (see their deltas) but their bodies are not
rewritten.
