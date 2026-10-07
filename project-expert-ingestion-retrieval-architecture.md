# Project Expert — Document Ingestion, Chunking, Embedding, Retrieval and Host-GPU Architecture

**Status:** proposed architecture / implementation blueprint  
**Validated:** 2026-10-07  
**Target:** local/on-prem/offline-first, Linux + Windows, Python, Docker/Podman-friendly, enterprise-safe permissive dependencies where possible.

## 1. Architectural goals

This module extends the existing Project Expert architecture without changing its core rules:

- OpenSpec remains the normative specification source.
- The Markdown/LLM Wiki remains durable, human-readable derived knowledge.
- Source documents and code are evidence; generated runtime indexes are derived and rebuildable.
- Knowledge is version-aware: Git branch/commit/release and source revision are first-class metadata.
- Durable canonical knowledge is sharded; no single huge index JSON is stored in Git.
- Vector search is only one retrieval channel. Full-text search, metadata filters and graph relations are retained.
- Local/offline operation is the default. Remote model/API access is not required.
- Linux and Windows must use the same logical pipeline.
- Runtime deployment should remain one application container where practical; the host GPU accelerator is an optional host-side companion process, not a required second container.
- Dependencies should preferably use Apache-2.0, MIT, BSD or similarly permissive licenses and permit commercial/enterprise use.

## 2. Recommended concrete stack

| Responsibility | Default tool | License | Notes |
|---|---|---|---|
| PDF/document parsing and layout | **Docling** | MIT | Primary ingestion engine. Produces `DoclingDocument`, layout, text blocks, tables, figures, captions and page provenance. |
| Docling layout model | **Docling Heron** | Apache-2.0 | Default layout analysis model. |
| PDF metadata/page-count/fallback | **pypdf** | BSD-3-Clause | Cheap pre-scan, metadata and page count. Not the primary layout parser. |
| OCR default | **Tesseract** | Apache-2.0 | Deterministic, local, multilingual; package `eng`, `deu`, `rus`, `ukr` traineddata. |
| OCR optional fallback | **PaddleOCR** | Apache-2.0 | For difficult scans/layouts when Tesseract quality is insufficient. Adapter is optional. |
| Structured document chunking | **Docling HybridChunker** | MIT as part of Docling | Structure-aware first, tokenizer-aware second. |
| Code parsing/chunking | **Tree-sitter** + language grammars | MIT | Java and other source-code AST boundaries. |
| Embedding runtime | **SentenceTransformers / Transformers** | Apache-2.0 | Python inference API. |
| Unified multimodal embedding | **google/embeddinggemma-2** | Apache-2.0 | Text/code/image/audio/video in one vector space. Use selectively loaded encoders for low-memory profiles. |
| Alternative text/code embedding | **Qwen/Qwen3-Embedding-0.6B** | Apache-2.0 | Optional separate text/code profile. Never mix its vectors with Gemma vectors in one ANN index. |
| Optional reranker | **Qwen/Qwen3-Reranker-0.6B** | Apache-2.0 | Off by default; run only on a small candidate set. |
| Durable runtime metadata/graph/jobs | **SQLite** | Public domain | Single portable DB file. |
| Lexical search | **SQLite FTS5** | SQLite | BM25 full-text search. |
| Vector ANN index | **USearch** | Apache-2.0 | Embedded HNSW-like vector index; no separate DB service. Index is disposable/rebuildable. |
| Simpler vector fallback | **sqlite-vec** | MIT | Very portable; useful for small/medium stores. Currently pre-v1, so keep behind an adapter. |
| Graph algorithms | **SQLite edge tables** + optional **NetworkX** | NetworkX BSD-3-Clause | No separate graph DB needed initially. |
| Accelerator HTTP API | **FastAPI** | MIT | Host-side embedding/reranking service. |
| Python/runtime bootstrap | **uv** | MIT OR Apache-2.0 | Reproducible host and container Python environments. |

### Licensing rule

Every model and binary must be pinned by exact version/revision and registered in `licenses.lock.yaml`. The repository license of a framework is not sufficient evidence for all models it can download. Model licenses are validated separately before they are added to the approved model registry.

## 3. High-level runtime architecture

```text
                         INPUT SOURCES
          ┌──────────────┬────────────┬──────────────┐
          │              │            │              │
        PDF/DOCX       Markdown      Source code   Images/audio/video
          │              │            │              │
          └──────────────┴──────┬─────┴──────────────┘
                                ▼
                        Source Discovery
                     fingerprint / provenance
                                │
                                ▼
                     Document Ingestion Layer
       ┌────────────────────────┼─────────────────────────┐
       │                        │                         │
    Docling                Tree-sitter              Media adapter
 PDF/layout/tables        source-code AST          optional/future
       │                        │                         │
       └────────────────────────┼─────────────────────────┘
                                ▼
                    Canonical Document Graph
          pages / elements / figures / tables / code nodes
                                │
                  ┌─────────────┴─────────────┐
                  ▼                           ▼
              Chunking                    Graph edges
                  │                           │
                  ▼                           │
              Enrichment                      │
                  │                           │
                  ▼                           │
             Embedding API                    │
                  │                           │
        ┌─────────┴──────────┐                │
        ▼                    ▼                │
 Host GPU Accelerator   Container CPU         │
        │                    │                │
        └─────────┬──────────┘                │
                  ▼                           ▼
            Embedding vectors          SQLite metadata/graph
                  │                           │
                  ▼                           ▼
              USearch ANN               SQLite FTS5/BM25
                  └──────────────┬─────────────┘
                                 ▼
                         Hybrid Retrieval
                   vector + BM25 + metadata + graph
                                 │
                       optional reranking
                                 │
                                 ▼
                         Context Assembler
                                 │
                           MCP / REST / CLI
```

## 4. Canonical document model

Do not make Markdown the only internal truth for imported PDFs. Markdown is a useful render/export format, but page geometry, figures, tables and relationships must survive conversion.

Use a Project Expert neutral schema so the rest of the application is not coupled to Docling types.

### 4.1 Core entities

```text
Source
  └── Revision
       ├── Page
       │    ├── Element: Heading
       │    ├── Element: Paragraph
       │    ├── Element: List
       │    ├── Element: Table
       │    ├── Element: Figure
       │    ├── Element: Formula
       │    └── Asset
       ├── Chunk
       └── Edge
```

Recommended entities:

- `source`: logical source identity and original location.
- `revision`: exact content version, SHA-256, Git/SVN revision if applicable.
- `page`: page number, dimensions, optional rendered image reference.
- `element`: typed block with reading order, bounding box and source provenance.
- `asset`: extracted image/figure crop or other binary object, content-addressed by SHA-256.
- `table`: structured grid plus textual serialization.
- `chunk`: retrieval unit produced from one or more elements.
- `edge`: relationship between any two nodes.
- `embedding`: model ID, model revision, dimension and vector payload/reference.
- `ingestion_job`: resumable processing state.

### 4.2 Deterministic IDs

Use separate logical identity and revision identity:

```text
source_id       = SHA256(normalized_source_uri)
revision_id     = SHA256(file_bytes)
element_id      = SHA256(revision_id + page + type + bbox + content_hash)
chunk_id        = SHA256(strategy_version + ordered_element_ids)
asset_id        = SHA256(asset_bytes)
```

Also keep `semantic_key` for cross-revision comparison, for example:

```text
semantic_key = normalized_heading_path + element_type + local_ordinal
```

The hash ID proves exact identity; `semantic_key` helps detect that a logically equivalent section moved or changed between revisions.

## 5. Exact PDF ingestion pipeline

### 5.1 Stage A — cheap pre-scan

Use `pypdf` before expensive layout/OCR work:

1. Calculate SHA-256 of the file.
2. Read page count and PDF metadata.
3. Sample several pages to estimate whether a usable text layer exists.
4. Create or resume an `ingestion_job`.
5. Skip the file completely if the exact `revision_id` is already indexed with the same ingestion schema version.

### 5.2 Stage B — batched Docling conversion

A 600-page PDF must not be treated as one enormous in-memory transaction.

Default configuration:

```yaml
pdf:
  page_batch_size: 32
  boundary_context_pages: 1
  parser: docling
  heading_hierarchy: true
  table_mode: accurate
```

Docling supports `page_range`, so a 600-page document is processed in resumable windows.

Example persistence windows:

```text
parse pages 1..33      persist 1..32
parse pages 32..65     persist 33..64
parse pages 64..97     persist 65..96
...
```

The extra neighboring page is context only. It is not persisted twice. This helps with structures that cross a page boundary while keeping memory bounded.

Pseudo-code:

```python
for first_page in range(1, page_count + 1, page_batch_size):
    last_page = min(first_page + page_batch_size - 1, page_count)

    parse_from = max(1, first_page - boundary_context_pages)
    parse_to = min(page_count, last_page + boundary_context_pages)

    docling_doc = converter.convert(
        pdf_path,
        page_range=(parse_from, parse_to),
    ).document

    canonicalize_and_persist(
        docling_doc,
        keep_pages=(first_page, last_page),
    )

    mark_batch_done(first_page, last_page)
    del docling_doc
```

The real implementation must commit each batch transactionally. If page 417 fails, pages 1..416 remain complete and the next run resumes from the failed batch.

### 5.3 Stage C — OCR policy

Do **not** blindly OCR every PDF page.

Default mode:

```text
native PDF text available
        │
        ├─ yes → use native text + layout analysis
        │        OCR only bitmap/image regions when needed
        │
        └─ no  → full-page OCR
```

Recommended Docling OCR mode for normal mixed PDFs:

```yaml
ocr:
  engine: tesseract
  mode: pdf_aware_layout_regions
  languages:
    - iso:en
    - iso:de
    - iso:ru
    - iso:uk
```

For a page detected as scan-only or clearly low quality, re-run that page using full-page OCR.

Tesseract is the default because it is Apache-2.0, local and predictable. PaddleOCR is an optional adapter used only when quality tests show that Tesseract is not sufficient for a document class.

### 5.4 Stage D — layout and heading hierarchy

Enable Docling heading hierarchy. It can use PDF bookmarks, numbering and visual style to reconstruct levels such as:

```text
1. Communication
  1.1 TCP Protocol
    1.1.1 Release Message
```

The normalized heading path becomes a first-class field on every subsequent chunk.

### 5.5 Stage E — tables

A table is stored in three representations:

```text
Table node
  ├── structured cells/rows/columns      canonical
  ├── Markdown/text serialization        retrieval/LLM
  └── page/bbox/caption relations        provenance
```

When a large table must be chunked, repeat its header in every chunk. Docling HybridChunker supports repeated table headers.

### 5.6 Stage F — figures, diagrams and pictures

A figure is never reduced to only its OCR text.

Store:

```text
figure_id
original/cropped image asset
page number
bounding box
caption
OCR text inside figure, if any
preceding/following relevant text elements
visual embedding, if enabled
relations to the surrounding section/chunks
```

Recommended relations:

```text
chunk-184  --MENTIONS--> figure-37-1
figure-37-1 --CAPTIONED_BY--> caption-37-1
figure-37-1 --ON_PAGE--> page-37
figure-37-1 --IN_SECTION--> section-4.3
```

For EmbeddingGemma 2, the figure image can receive a visual embedding in the same vector space as text. This enables a text query to retrieve a relevant diagram directly.

### 5.7 Stage G — canonical export

After parsing, generate two forms:

```text
Canonical machine representation: sharded JSONL / structured records
Human/LLM representation: generated Markdown
```

The Markdown is an export/view, not the only canonical store.

For large documents use shards, for example:

```text
knowledge/<source_id>/<revision_id>/
  manifest.yaml
  pages/
    pages-000001-000050.jsonl
    pages-000051-000100.jsonl
    ...
  chunks/
    chunks-000001-005000.jsonl
  markdown/
    section-0001.md
    section-0002.md
  assets-manifest.jsonl
```

Large binary assets, model weights and runtime indexes are not committed to Git by default. Store them in a content-addressed local cache and refer to them by SHA-256 from the manifest.

## 6. Chunking architecture

Chunking is based on semantic/document boundaries first and token limits second.

### 6.1 PDF/Markdown/document text

Use Docling `HybridChunker` with the tokenizer of the selected embedding model.

Recommended starting policy:

```yaml
chunking:
  documents:
    engine: docling_hybrid
    max_tokens: 900
    merge_peers: true
    preserve_heading_path: true
    preserve_captions: true
```

`900` is not a universal optimum; it is an initial Project Expert profile. Benchmark alternatives such as 512, 768, 900 and 1200 tokens on the actual document corpus.

Do not cut merely every N characters. The chunker should prefer:

```text
section → paragraph/list/table boundary → tokenizer limit
```

### 6.2 Source code

Use Tree-sitter rather than document chunking.

For Java:

```text
file
 └── package/class/interface/enum
      ├── fields
      ├── constructor
      ├── method
      └── nested type
```

A normal method is one chunk. An oversized method is split at statement/block boundaries while retaining the parent symbol metadata.

Enrichment fields include:

```text
repository
branch/commit
module
source path
package
class/interface
method signature
implemented interface/base class
symbol references when available
```

## 7. Enrichment: what is embedded and what remains metadata

Do not embed the entire metadata JSON.

Split each chunk into three forms:

```text
raw_text          exact source text
retrieval_text    semantically enriched text sent to the embedding model
metadata          structured fields used for filters/provenance
```

Example:

```json
{
  "chunk_id": "...",
  "raw_text": "The release telegram contains ...",
  "retrieval_text": "GENESYS Manual\nCommunication > Telegram Format > Release Message\nThe release telegram contains ...",
  "metadata": {
    "source_id": "...",
    "revision_id": "...",
    "page_from": 37,
    "page_to": 37,
    "branch": "dev",
    "commit": "...",
    "language": "en",
    "element_ids": ["..."],
    "figure_ids": ["figure-37-1"]
  }
}
```

Semantic context that usually belongs in `retrieval_text`:

```text
document title
heading path
caption when directly relevant
symbol/class/method context for code
actual chunk content
```

Data that usually remains metadata only:

```text
SHA-256
branch/commit ID
absolute/local path
page coordinates
timestamps
processing version
security/access labels
```

This keeps embeddings semantic while retaining exact filtering and provenance.

## 8. Embedding model profiles

### 8.1 Default unified profile

Use `google/embeddinggemma-2` when cross-modal retrieval matters.

```yaml
embedding:
  profile: unified
  model: google/embeddinggemma-2
  dimension: 512
  normalize: true
```

`512` is a storage/search trade-off. Keep 768 as an evaluation profile.

Important: reducing vector dimension reduces vector/index storage; it does not proportionally reduce model VRAM.

### 8.2 Low-memory text profile

Load only the text encoder when images/audio/video are not needed in that process. Keep batch size small and let the accelerator report actual available memory.

### 8.3 Alternative text/code profile

`Qwen/Qwen3-Embedding-0.6B` can be enabled as a separate model profile for text/code evaluation.

**Never place Qwen and EmbeddingGemma vectors in the same vector index.** Different embedding models create different coordinate spaces.

If both are used:

```text
index_text_qwen
index_unified_gemma
```

Search them separately and fuse ranked results.

## 9. Host GPU accelerator architecture

The application container should not own GPU-specific host setup. GPU inference is an optional host service started by the project launcher.

### 9.1 Components

```text
Host OS
  ├── GPU driver already installed
  ├── Project Expert host accelerator (Python)
  │     ├── SentenceTransformers/Transformers
  │     ├── PyTorch CUDA for NVIDIA profile
  │     ├── optional ONNX Runtime profiles
  │     └── FastAPI
  │
  └── Docker/Podman
        └── Project Expert application container
              └── calls accelerator HTTP API
```

### 9.2 Accelerator API

Minimal internal API:

```text
GET  /health
GET  /v1/capabilities
POST /v1/embeddings
POST /v1/rerank
```

Example request:

```json
{
  "model": "google/embeddinggemma-2",
  "dimension": 512,
  "items": [
    {"id": "chunk-1", "modality": "text", "text": "..."}
  ]
}
```

Example capability response:

```json
{
  "device": "cuda",
  "gpu": "NVIDIA ...",
  "free_memory_mb": 812,
  "models": ["google/embeddinggemma-2"],
  "modalities": ["text"]
}
```

### 9.3 Security

The accelerator is not a general command-execution service.

- It accepts only fixed inference operations.
- No arbitrary model path from the request.
- Models must exist in an allow-list.
- Generate an ephemeral bearer token on each start.
- Pass the token to the container through a runtime secret/env file outside Git.
- Bind only to the interface necessary for Docker-to-host communication; if platform limitations force a wider bind, host firewall + bearer token are mandatory.

### 9.4 Startup sequence

The canonical orchestrator is a cross-platform Python launcher; Make and PowerShell are wrappers.

```text
make up
   │
   ▼
tools/harness.py up
   │
   ├── detect OS
   ├── detect GPU / execution provider
   ├── create/update host accelerator venv with uv
   ├── start accelerator
   ├── wait for /health
   ├── write runtime endpoint + token
   └── docker compose up
```

On native Windows where GNU Make is intentionally unavailable:

```powershell
.\tools\project.ps1 up
```

Both wrappers call the same `harness.py`; Make is convenience, not an architectural dependency.

### 9.5 Suggested commands

```text
make bootstrap           prepare local runtime and model registry
make accelerator-up      start/detect host accelerator
make accelerator-status  show selected device/model/memory
make app-up              start container only
make up                  accelerator-up + app-up
make down                stop app and accelerator
make ingest FILE=...     ingest one source
make reindex             rebuild FTS/vector/graph indexes from durable runtime records
make verify              run architecture/integration checks
```

## 10. Container CPU fallback

The application remains functional without the host accelerator.

```text
if host accelerator healthy:
    use host accelerator
else:
    use container CPU backend
```

CPU inference can use SentenceTransformers/PyTorch initially. ONNX Runtime is an optional optimization profile; it is MIT licensed and cross-platform.

The user therefore gets:

```text
GPU machine → fast host acceleration
CPU-only machine → same feature set, slower
```

## 11. Runtime storage design

### 11.1 SQLite tables

Suggested minimum schema:

```text
sources
revisions
pages
elements
assets
tables
chunks
chunk_elements
edges
embeddings
ingestion_jobs
index_state
```

Create FTS5 over selected chunk fields:

```text
chunk title
heading path
raw text
selected captions/symbols
```

FTS5 provides BM25 ranking.

### 11.2 Vector index

Persist the computed vector payload or a compact vector record separately from the ANN structure so an ANN index can be rebuilt without re-running the model.

Default:

```text
SQLite: chunk metadata + vector payload/version
USearch: ANN index derived from vectors
```

Alternative small-project mode:

```text
SQLite + sqlite-vec only
```

`sqlite-vec` is deliberately behind a `VectorIndex` port because it is currently pre-v1.

### 11.3 Graph

Do not add Neo4j or another server in v1.

Use:

```text
edges(from_id, edge_type, to_id, revision_id, confidence, source)
```

Example edge types:

```text
PART_OF
NEXT
PREVIOUS
DESCRIBES
MENTIONS
CAPTIONED_BY
IMPLEMENTED_BY
DEFINED_BY
TESTED_BY
REFERENCES
ON_PAGE
IN_SECTION
```

For limited traversals use recursive SQLite CTEs. For more complex in-memory graph algorithms, load only the relevant subgraph into NetworkX.

## 12. Hybrid retrieval pipeline

```text
User/agent query
      │
      ├── embedding → USearch top 50
      │
      ├── FTS5 BM25 → top 50
      │
      └── metadata filters
              │
              ▼
        rank fusion (RRF)
              │
              ▼
        graph expansion 1–2 hops
              │
              ▼
      optional reranker top 20
              │
              ▼
       context assembly top N
```

Recommended first implementation uses Reciprocal Rank Fusion rather than hand-tuned incomparable raw vector/BM25 score weights.

Graph expansion should add supporting nodes, not replace ranking. Example: a matching paragraph can pull in its figure, caption, parent section and exact source-page provenance.

## 13. Incremental indexing and Git awareness

Every processed source records:

```text
branch
commit/revision
source path
source_id
revision_id
page/block/chunk hashes
parser version
chunker version
embedding model + revision
embedding dimension
```

On re-index:

1. unchanged `revision_id` → skip source;
2. changed PDF → compare normalized page/element hashes;
3. unchanged chunks → reuse existing embedding;
4. changed/new chunks → embed only these;
5. deleted chunks → tombstone/remove from derived indexes;
6. update index generation atomically.

For Git branch switching, retrieval must filter by the active branch/commit knowledge snapshot. Runtime indexes are derived from the active manifest and can be rebuilt.

## 14. Interaction with OpenSpec and the Project Expert Wiki

Imported documents do not automatically become normative requirements.

```text
external source/PDF/code
        ↓
ingestion + provenance
        ↓
retrievable evidence
        ↓
verified knowledge extraction
        ↓
Markdown Wiki / ADR / OpenSpec update
```

OpenSpec remains normative. The Wiki remains durable verified knowledge. Ingestion creates searchable evidence and proposed context, not silent specification changes.

Generated durable knowledge should preserve stable source links:

```text
source_id
revision_id
page/element IDs
chunk IDs
```

so an agent can always explain where a Wiki assertion came from.

## 15. Suggested project structure

```text
project-expert/
├── pyproject.toml
├── uv.lock
├── compose.yaml
├── Makefile
├── project-expert.yaml
│
├── src/project_expert/
│   ├── ingestion/
│   │   ├── discovery/
│   │   ├── parsers/
│   │   │   ├── docling_pdf.py
│   │   │   ├── markdown.py
│   │   │   └── tree_sitter_code.py
│   │   ├── canonical/
│   │   ├── ocr/
│   │   └── jobs/
│   ├── chunking/
│   ├── enrichment/
│   ├── embedding/
│   │   ├── ports.py
│   │   ├── host_accelerator.py
│   │   └── cpu_backend.py
│   ├── storage/
│   │   ├── sqlite_store.py
│   │   ├── fts5.py
│   │   ├── usearch_index.py
│   │   └── graph.py
│   ├── retrieval/
│   ├── mcp/
│   └── api/
│
├── accelerator/
│   ├── pyproject.toml
│   └── src/project_expert_accelerator/
│       ├── main.py
│       ├── models.py
│       └── device.py
│
├── tools/
│   ├── harness.py
│   └── project.ps1
│
├── knowledge/
│   └── ... sharded canonical durable knowledge ...
│
└── .runtime/                  # ignored by Git
    ├── project-expert.db
    ├── indexes/
    ├── cas/
    ├── models/
    ├── jobs/
    └── accelerator/
```

## 16. Example configuration

```yaml
project_expert:
  offline_first: true

ingestion:
  pdf:
    parser: docling
    page_batch_size: 32
    boundary_context_pages: 1
    heading_hierarchy: true
    table_mode: accurate
    ocr:
      enabled: true
      engine: tesseract
      mode: pdf_aware_layout_regions
      languages: [iso:en, iso:de, iso:ru, iso:uk]
      scan_fallback_mode: full_page
      optional_fallback_engine: paddleocr

chunking:
  documents:
    engine: docling_hybrid
    max_tokens: 900
    merge_peers: true
  code:
    engine: tree_sitter

embedding:
  backend: auto
  primary:
    model: google/embeddinggemma-2
    dimension: 512
    normalize: true
  alternative_text:
    model: Qwen/Qwen3-Embedding-0.6B
    dimension: 512
    enabled: false

accelerator:
  enabled: auto
  endpoint: http://host.docker.internal:8765
  request_timeout_seconds: 120
  fallback_to_container_cpu: true

retrieval:
  vector_candidates: 50
  lexical_candidates: 50
  fusion: rrf
  graph_hops: 1
  reranker:
    enabled: false
    model: Qwen/Qwen3-Reranker-0.6B
    candidates: 20

storage:
  metadata: sqlite
  full_text: sqlite_fts5
  vector_index: usearch
  graph: sqlite_edges

versioning:
  branch_aware: true
  reuse_unchanged_embeddings: true
  canonical_shards: true
```

## 17. Recommended implementation order

### Phase 1 — foundation

Implement the neutral data model, SQLite schema, content hashes, ingestion jobs, configuration and ports/adapters. Do not start with vector search.

### Phase 2 — PDF ingestion

Integrate pypdf pre-scan + Docling batched parsing + Tesseract OCR + canonical JSON records. Validate with 10-page, 100-page and 600-page PDFs, including mixed scanned/native pages.

### Phase 3 — chunking/enrichment

Add Docling HybridChunker using the actual embedding tokenizer. Add deterministic enrichment and precise source provenance.

### Phase 4 — embedding accelerator

Implement FastAPI host accelerator, device detection, model allow-list, token authentication and CPU fallback. Start with EmbeddingGemma 2 text mode.

### Phase 5 — hybrid retrieval

Add SQLite FTS5 + USearch, Reciprocal Rank Fusion, source/version filters and exact source reconstruction.

### Phase 6 — visual document understanding

Extract and persist figure crops, captions, nearby text and OCR. Enable EmbeddingGemma visual embeddings when memory permits. Add graph links between figure and explanatory paragraphs.

### Phase 7 — code knowledge

Integrate Tree-sitter code chunking and source-symbol metadata. Connect code chunks to Wiki/OpenSpec/document concepts with graph edges.

### Phase 8 — reranking and evaluation

Only after baseline retrieval metrics exist, test Qwen3-Reranker-0.6B and compare latency/quality. Keep it disabled if quality gain does not justify resource cost.

## 18. Acceptance criteria

The architecture is considered correctly implemented when all of the following are true:

- A 600-page PDF can be ingested without loading the complete converted document into RAM at once.
- Processing can resume after failure from a page batch checkpoint.
- Every retrieved chunk can be traced to exact source, revision, page and element(s).
- Text, tables, figures and captions remain related after ingestion.
- OCR is selective; native PDF text is not unnecessarily replaced.
- Markdown export can be regenerated from structured source data.
- Vector indexes can be deleted and rebuilt without losing canonical knowledge.
- Re-indexing an unchanged source does not recompute embeddings.
- Git branch/commit filters prevent mixing incompatible knowledge snapshots.
- No cloud service is required for ingestion, embedding or search.
- Application remains functional without GPU.
- GPU acceleration can be enabled from the host launcher without putting GPU-specific logic into the main application container.
- All production dependencies/models have a recorded approved license and pinned version/revision.

## 19. Key technical decisions

1. **Docling is the primary PDF ingestion engine**, not PDF-to-Markdown alone.
2. **Markdown is a generated representation**, not the only canonical PDF representation.
3. **OCR is selective** and page/region aware.
4. **Figures are first-class graph nodes**, not discarded after OCR.
5. **Chunking is structure-aware before token-aware**.
6. **Enrichment is separated from metadata**; only semantic context enters the embedding text.
7. **SQLite is the durable runtime truth; indexes are derived.**
8. **USearch + FTS5 + graph edges form the initial hybrid retrieval stack.**
9. **Embedding model is behind a port**, allowing EmbeddingGemma/Qwen/other replacements without changing ingestion.
10. **Host GPU accelerator is optional and isolated behind HTTP**, while CPU fallback keeps deployment portable.
11. **Different embedding models never share one vector space/index.**
12. **OpenSpec is not modified automatically by ingestion.** Imported information remains evidence until verified.

## 20. Upstream references used for this design

- Docling: https://github.com/docling-project/docling
- Docling chunking: https://docling-project.github.io/docling/concepts/chunking/
- Docling CLI/page ranges: https://docling-project.github.io/docling/reference/cli/
- Docling pipeline/OCR options: https://docling-project.github.io/docling/reference/pipeline_options/
- Tesseract: https://github.com/tesseract-ocr/tesseract
- PaddleOCR: https://github.com/PaddlePaddle/PaddleOCR
- pypdf: https://github.com/py-pdf/pypdf
- Tree-sitter: https://github.com/tree-sitter/tree-sitter
- EmbeddingGemma 2: https://huggingface.co/google/embeddinggemma-2
- Qwen3-Embedding-0.6B: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- Qwen3-Reranker-0.6B: https://huggingface.co/Qwen/Qwen3-Reranker-0.6B
- SQLite FTS5: https://www.sqlite.org/fts5.html
- USearch: https://github.com/unum-cloud/usearch
- sqlite-vec: https://github.com/asg017/sqlite-vec
- FastAPI: https://github.com/fastapi/fastapi
- ONNX Runtime: https://github.com/microsoft/onnxruntime
- uv: https://github.com/astral-sh/uv
