# Design — improve-ingestion-retrieval-local-models

## Current state

The v0.8 Project Intelligence Platform is accepted and shipped.
The accepted baseline this change refines is summarised in
`openspec/CURRENT.md` and explained in
`kb://architecture/platform-overview`,
`kb://architecture/system-overview`,
`project-intelligence-platform-architecture-v0.8.md`, and the
Phase 2–10 Wiki module maps. The implementation lives entirely
under `pi_platform/{core,ports,adapters,orchestration,mcp,control}/`
and the per-phase module Wiki nodes.

Concretely, the following already exist and are accepted:

- `pi_platform/core/canonical/` — `Source`, `Document`, `Section`,
  `Chunk`, `Entity`, `Relation`, `Evidence`, `KnowledgeState`,
  `ProjectVersion`, `Shard`, `Manifest` (knowledge schema v1).
- `pi_platform/core/canonical/content_address.py` — content
  addressing and canonical hashing.
- `pi_platform/core/sync/` — bidirectional Git/runtime sync.
- `pi_platform/ports/ingest/source_adapter.py` — `SourceAdapterPort`,
  `SourceContentFamily`, including `PDF`.
- `pi_platform/adapters/ingest/local_pipeline_driver.py` — the
  ingestion pipeline driver.
- `pi_platform/core/ingest/local_source_inbox_scanner.py` — local
  source inbox.
- `pi_platform/adapters/java/` — Java/JAR parsing
  (`tree-sitter` based, ADR-0006).
- `pi_platform/adapters/ingest/chunkers.py` — structural chunkers
  (Markdown, requirements, protocols, tables, architecture,
  Java AST-based).
- `pi_platform/ports/ingest/context_enricher.py` — three-layer
  context enricher contract.
- `pi_platform/adapters/ingest/layered_context_enricher.py` —
  deterministic + metadata + optional local-LLM suggestion.
- `pi_platform/adapters/runtime/sqlite_runtime_store.py` — SQLite
  runtime store with the `runtime_entries` table.
- `pi_platform/adapters/runtime/flat_dense_index.py` — flat dense
  index fallback.
- `pi_platform/adapters/runtime/bm25_sparse_index.py`,
  `pi_platform/adapters/runtime/sqlite_fts_full_text_index.py` —
  sparse/FTS.
- `pi_platform/core/retrieval/hybrid_retrieval.py` — hybrid RRF.
- `pi_platform/core/retrieval/multi_stage_retrieval.py` — multi-stage
  retrieval.
- `pi_platform/core/retrieval/metadata_filter.py` — metadata filters.
- `pi_platform/core/retrieval/context_assembler.py` — context
  assembler.
- `pi_platform/core/retrieval/reranker.py` — BM25-light fallback
  reranker.
- `pi_platform/ports/retrieval/reranker.py` — reranker port (with a
  placeholder `CrossEncoderRerankerAdapter`).
- `pi_platform/core/orchestration/query_orchestrator.py` — query
  orchestrator.
- `pi_platform/core/orchestration/local_llm.py` — local LLM port.
- `pi_platform/core/orchestration/capability_discovery.py` —
  capability discovery.
- `pi_platform/mcp/server.py` — MCP server with the
  `retrieve_context` tool, retrieval-first policy.
- `pi_platform/control/` — Control Registry, Hook Runtime, Policy
  Engine, Secret Provider, Audit Log, Feature Flags, UI Extension
  Registry, Capabilities.
- `pi_platform/security/` — enterprise security boundary
  (ADR-0017).
- `distribution/`, `Containerfile`, `docker-compose.yml`,
  `harness.py`, `Makefile` — one-click distribution and CI gates.
- `tests/test_retrieval_benchmark.py` — Tier 1 deterministic
  synthetic benchmark.

The `pi_platform/adapters/pdf/` package is currently empty
(only `__init__.py`). `PLANNED_ADAPTERS` in the source adapter
references a `pdfplumber` plan that this change replaces.

The current `MultilingualSentenceTransformerEmbeddingModel` is a
contract/stub: it validates that `sentence-transformers` is
importable and raises on `embed()` / `embed_batch()`. The
`HashingEmbeddingModel` is the de-facto default.

`HybridRetrievalCore` short-circuits any query whose
`IdentifierQueryDetector` flags at least one identifier; mixed
queries with both identifier and free text lose the semantic
channel.

`MultiStageRetrievalCore` currently does
`direct → metadata → graph → hierarchy → merge → rerank`. The
plan calls this semantically suboptimal (plan §4.2).

`RetrievalHit.source` accepts only
`dense|sparse|exact|hybrid`; graph/hierarchy code sometimes
constructs hits with `graph|hierarchy`, which is a contract
mismatch that this change resolves by separating
`DirectCandidate` from `SupportEvidence`.

No non-destructive selection layer exists; reranking currently
returns the reranker's top-`k`, dropping everything else
including exact-id hits that the reranker undervalued.

No retrieval trace is persisted; the only debugging surface is
the existing `RetrievalResult` returned to the caller.

No embedding profile identity is recorded; the dense index holds
vectors without a model/dimension namespace, so a future model
switch could silently mix vector spaces.

No `TokenizerPort` exists; chunking uses a `max_chunk_bytes`
safety fallback aligned to UTF-8 byte length, not to the actual
embedding tokenizer.

The cross-encoder reranker adapter is a constructor placeholder.

Evaluation is Tier 1 only; there is no Tier 2 local-model
integration, no Tier 3 retrieval-evaluation command, and no
chunk-size sweep.

## Proposed design

The design is a **strict extension** of the v0.8 architecture.
The platform layout, the `pi_platform/{core,ports,adapters}`
tree, the control plane, the security boundary, the MCP server,
the distribution model, and the harness workflow are all
preserved. The change adds new ports, new canonical types, new
runtime store tables, new adapters, and a new retrieval pipeline
order, all behind stable contracts.

### Architectural style

The platform keeps the architectural style mandated by
`project-intelligence-platform-architecture-v0.8.md` §59 and
ADR-0004 (Ports-and-Adapters extension style):

- **Hexagonal / Ports-and-Adapters core.** Business logic depends
  on ports; adapters implement ports for specific technologies
  (a USearch vector-store adapter, a Docling PDF adapter, an
  EmbeddingGemma 2 embedding-model adapter, a host-accelerator
  HTTP client adapter, a Qwen3 reranker adapter).
- **Micro-kernel / Plugin extension surface.** Optional
  capabilities (PDF, EmbeddingGemma 2, Qwen3 reranker, host
  accelerator, multimodal figures) are registered through the
  same `CapabilityRegistry` already in use (Control Plane module).
  The core remains agent-neutral, model-neutral, storage-neutral
  at the architectural level, and UI-neutral.
- **Single modular deployable.** The default deployable is one
  container. The host-side embedding accelerator is an optional
  deployment profile, not a core requirement, and lives outside
  the container.

### Module layout

The change does not introduce a second product tree. New code
lives alongside the existing v0.8 code:

```text
pi_platform/
├── core/
│   ├── canonical/
│   │   ├── (existing canonical types)
│   │   └── document_graph.py             # NEW
│   ├── ingest/
│   │   ├── (existing scanner)
│   │   ├── token_budget.py               # NEW
│   │   ├── retrieval_text_builder.py     # NEW
│   │   └── local_contextualizer.py       # NEW
│   └── retrieval/
│       ├── (existing hybrid, multi-stage, context assembler)
│       ├── query_features.py             # NEW
│       ├── selection.py                  # NEW
│       └── retrieval_trace.py            # NEW
├── ports/
│   ├── ingest/
│   │   ├── (existing source_adapter, chunker, context_enricher)
│   │   ├── tokenizer.py                  # NEW
│   │   ├── retrieval_text_builder.py     # NEW
│   │   └── ingestion_job_store.py        # NEW
│   ├── retrieval/
│   │   ├── (existing hybrid, multi-stage, reranker)
│   │   └── selection.py                  # NEW
│   └── runtime/
│       ├── (existing dense_index, sparse_index, full_text_index, runtime_store)
│       └── vector_record_store.py        # NEW
├── adapters/
│   ├── ingest/
│   │   ├── (existing layered_context_enricher, chunkers)
│   │   ├── local_pipeline_driver.py      # EXTEND
│   │   ├── docling_hybrid_chunker.py     # NEW (PDF)
│   │   ├── embeddinggemma2_tokenizer.py  # NEW
│   │   └── docling_local_contextualizer.py  # NEW (optional)
│   ├── pdf/
│   │   ├── prescan.py                    # NEW
│   │   ├── docling_pdf_adapter.py        # NEW
│   │   ├── docling_mapper.py             # NEW
│   │   ├── ocr_policy.py                 # NEW
│   │   ├── assets.py                     # NEW
│   │   └── docling_chunker.py            # NEW
│   ├── runtime/
│   │   ├── (existing sqlite_runtime_store, flat_dense_index)
│   │   ├── usearch_dense_index.py        # NEW
│   │   ├── sqlite_vector_record_store.py # NEW
│   │   ├── sqlite_document_graph_store.py # NEW
│   │   └── sqlite_ingestion_job_store.py # NEW
│   ├── retrieval/
│   │   ├── (existing hashing_embedding_model, multilingual_st)
│   │   ├── embeddinggemma2_embedding_model.py  # NEW
│   │   ├── qwen3_embedding_model.py      # NEW (profile)
│   │   ├── qwen3_reranker.py             # NEW (profile)
│   │   └── host_embedding_client.py      # NEW
│   └── java/                             # KEEP
└── mcp/                                   # EXTEND tools
```

### New canonical types (additive)

In `pi_platform/core/canonical/document_graph.py`:

- `DocumentRevision` — `revision_id`, `source_id`, `byte_hash`,
  `strategy_version`, `ingested_at`, `metadata` (page count,
  author, language, etc.).
- `Page` — `page_no`, `bbox`, `native_text_present`, `ocr_used`,
  `rotation`, `language_hint`.
- `DocumentElement` — discriminated union of `Heading`,
  `Paragraph`, `List`, `Table`, `Figure`, `Formula`. Carries
  `element_id`, `page_no`, `bbox`, `content_hash`, `semantic_key`
  (non-authoritative cross-revision key).
- `ElementKind` — enum.
- `SourceAnchor` — `revision_id`, `page`, `element_id`, `bbox`,
  `line`, `asset_id`. Added to `Chunk` as
  `Chunk.anchors: Sequence[SourceAnchor]` (additive; legacy
  chunks have an empty list).
- `AssetRef` — `asset_id`, `byte_hash`, `mime_type`, `cas_path`,
  `page`, `bbox`. Image bytes live in CAS (default) or in
  Git/LFS only when source policy is `SNAPSHOT`.
- `TableGrid` — `headers`, `rows`, `serialised_markdown`,
  `repeat_header`. The canonical structure is the grid; the
  Markdown serialisation is a retrieval convenience.
- `IngestionCheckpoint` — `job_id`, `revision_id`, `strategy_version`,
  `state`, `next_page`, `completed_ranges`, `failed_range`, `error`,
  `started_at`, `updated_at`.

The schema version for the canonical knowledge is bumped from
`1` to `2` to record the additive fields; the existing schema
version `1` records are still readable. A migration adds the new
fields and tables; it does not rewrite existing records.

### New ports (additive)

- `TokenizerPort` — `count(text) -> int`,
  `truncate(text, max_tokens) -> str`, `identity() -> str`.
  Implemented by `HashingTokenizer` (deterministic, no
  dependencies), `EmbeddingGemma2Tokenizer` (when the
  EmbeddingGemma 2 model/tokenizer is available, behind
  `semantic-embeddings` extra), `WhitespaceTokenizer` (test
  fallback). Identity is the canonical token, e.g.
  `embeddinggemma2/transformers/<revision>`.
- `RetrievalTextBuilderPort` — `build(chunk, document, section,
  metadata, optional_local_enrichment) -> RetrievalText`.
  Implemented by `DeterministicRetrievalTextBuilder` (default)
  and `LocalContextualizerRetrievalTextBuilder` (opt-in). The
  output includes `text`, `strategy_version`,
  `deterministic_parts`, `inferred_parts`, `content_hash`.
- `LocalContextualizer` — narrow application service over
  `LocalLLMPort`. Its output is restricted to:
  - 1–3 sentence semantic context;
  - candidate entities;
  - candidate relations;
  - query aliases / glossary hints.
  It is forbidden from producing authoritative metadata
  (requirement ID, protocol version, validFrom/validTo,
  security class, Git revision, source ID, license). Its
  outputs are tagged `INFERRED` / `ASSUMPTION`.
- `InferencePolicy` — `NO_MODEL | LOCAL_MODEL_ALLOWED |
  EXTERNAL_MODEL_ALLOWED`, separate from source persistence
  policy (`LOCAL_ONLY | REFERENCE | SNAPSHOT`). Both
  policies are evaluated by the central Policy Engine
  (`pi_platform/control/policy_engine.py`).
- `ContextualizationCache` — keyed by
  `sha256(chunk_content_hash || contextualizer_model_revision
  || prompt_version || enrichment_strategy_version)`.
- `EmbeddingProfile` — descriptor: `provider`, `model_id`,
  `model_revision`, `modality`, `output_dimension`,
  `normalization`, `instruction_profile`, `tokenizer_id`,
  `strategy_version`. Identity key is
  `sha256(canonical(EmbeddingProfile))`.
- `VectorRecordStorePort` — `put(VectorRecord)`,
  `get(chunk_id, profile_hash)`, `delete(chunk_id,
  profile_hash)`, `iter(profile_hash)`. Adapter
  `SqliteVectorRecordStore` stores the vector as a
  `BLOB` in the `embeddings` table
  (`vector_payload`).
- `IngestionJobStorePort` — `create(IngestionJob)`,
  `mark_running`, `mark_batch_done`, `mark_failed`,
  `mark_completed`, `get(job_id)`, `list_for(revision_id)`.
  Adapter `SqliteIngestionJobStore` lives in the same
  `runtime.db`.
- `DocumentGraphStorePort` — `put_revision`,
  `get_revision`, `put_page`, `put_element`, `put_asset`,
  `put_table`, `get_elements_for_page`, etc. Adapter
  `SqliteDocumentGraphStore`.
- `SelectionPort` — `select(candidates, query_features,
  budget) -> SelectionResult`. `SelectionResult` is
  `PRIMARY`, `RESERVE`, `PROTECTED`, `SUPPORT`,
  `DROPPED_DUPLICATE` grouped, with per-candidate
  `CandidateTrace`.
- `EmbeddingModelPort` (existing) — implementations:
  `HashingEmbeddingModel` (kept), new
  `EmbeddingGemma2EmbeddingModel`,
  `Qwen3EmbeddingModel` (profile), new
  `HostEmbeddingClient` (HTTP, additive behind the
  same port).

### New retrieval pipeline order (normative)

The plan §4.2 stage order becomes the normative multi-stage
retrieval order:

```text
1. Query analysis  (QueryFeatures)
2. Exact / dense / sparse candidate generation
3. Metadata / version / security constraints
4. RRF fusion
5. Pre-rerank direct candidate pool  (cap = pre_rerank_pool)
6. Cross-encoder / fallback rerank of DIRECT candidates only
7. Selection: PRIMARY / RESERVE / PROTECTED
8. Graph expansion from selected primary/protected seeds
9. Hierarchy / adjacent / figure / table expansion
10. Mark expanded nodes SUPPORT
11. Context Assembly (PRIMARY > PROTECTED > SUPPORT > RESERVE)
12. Reserve escalation if context budget is not exhausted and
    the assembler / verifier still needs more evidence
```

`DirectCandidate` and `SupportEvidence` are distinct types so
the reranker never has to handle support nodes. The
`RetrievalHit.source` enum stays as
`dense|sparse|exact|hybrid`; support items are added by
`ContextAssembler` with their own `evidence_kind`.

`SelectionState` is `PRIMARY | RESERVE | PROTECTED | SUPPORT |
DROPPED_DUPLICATE`. `CandidateTrace` carries
`chunk_id`, `dense_rank`, `sparse_rank`, `exact_match`,
`rrf_rank`, `rrf_score`, `rerank_rank`, `rerank_score`,
`selection_state`, `protected_reason`, `duplicate_of`,
`source_document_id`, `trace_reasons`. `CandidateTrace` lives
in the runtime/evaluation layer; it is not committed to
canonical Git knowledge.

`RetrievalTrace` is attached to `RetrievalResult` and contains
`query_features`, `active_filters`, `exact_candidates`,
`dense_candidates`, `sparse_candidates`, `fusion`,
`reranker`, `selection`, `graph_expansion`,
`hierarchy_expansion`, `budget_decisions`, `timings`. It is
serialisable to JSON, redacted of secret metadata, and
optionally surfaced through the MCP server in
`debug` / `evaluation` mode. Control Plane diagnostics
expose the trace for the active query and the latest
N traces for inspection.

### Chunking composition (normative)

Chunking becomes a two-stage composition:

```text
SemanticBoundaryStrategy  →  TokenBudgetNormalizer
```

The existing structural chunkers (`PlainTextChunker`,
`RequirementChunker`, `ProtocolChunker`, `TableChunker`,
`ArchitectureChunker`, Java AST chunkers) are kept; they
produce structural candidates. The new
`TokenBudgetNormalizer` is composed after each one to:

1. split oversized candidates at token boundaries (preserving
   structure when possible);
2. merge compatible peer candidates when below `min_tokens`;
3. never violate `max_chunk_bytes` (kept as a hard safety
   limit).

`ChunkerContext` is extended additively with
`target_tokens`, `max_tokens`, `min_tokens`,
`tokenizer_id`, `merge_peers`. `max_chunk_bytes` is
preserved.

For PDF documents the `DoclingHybridChunker` adapter
(`pi_platform/adapters/ingest/docling_hybrid_chunker.py`)
combines Docling hierarchical boundaries with
tokenizer-aware splits; it implements the existing
`ChunkerPort` so the pipeline driver does not need a
special-case code path for PDF.

### `RetrievalTextBuilder` (normative)

The model never embeds raw metadata JSON. The builder
computes:

```text
retrieval_text = context_prefix + "\n\n" + raw_text
```

where `context_prefix` is built deterministically from
`document_title`, `heading_path`, `requirement_id` (when
semantically meaningful), `java_signature` (when
applicable), `protocol_name` (when applicable),
`caption`, and (optionally, behind the opt-in local
contextualizer) a 1–3 sentence semantic context produced
by the local LLM. The builder never embeds: absolute
filesystem path, SHA, Git commit hash, timestamps, bbox
coordinates, security label, processing version. Those
remain metadata.

`Chunk.contextualText` is reconciled: it either
becomes the persisted result of the builder or is
deprecated in favor of `retrieval_text` + a deterministic
mapping. The plan forbids three competing meanings for
the same semantic text (plan §10).

### PDF ingestion pipeline (normative)

The PDF ingestion pipeline is implemented behind the
existing `SourceAdapterPort` and follows the plan §21
contract:

- **Stage A — cheap prescan**
  (`pi_platform/adapters/pdf/prescan.py`): hash file,
  read page count, read metadata, sample the native
  text layer, resolve `revision_id`, and check whether
  the exact revision + ingestion strategy already exist
  in `IngestionJobStorePort` (`COMPLETED` state). If so,
  skip the expensive parse.
- **Stage B — batched parse**
  (`pi_platform/adapters/pdf/docling_pdf_adapter.py`):
  page window of `page_batch_size` pages, with
  `boundary_context_pages` neighbour pages as context.
  Each batch is committed transactionally to
  `SqliteDocumentGraphStore`. A crash at page 417 does
  not invalidate completed batches; the job is
  resumable.
- **Selective OCR**
  (`pi_platform/adapters/pdf/ocr_policy.py`): if the
  native text layer is usable, do not OCR; OCR is used
  for image/bitmap regions or full pages when no text
  layer exists. The OCR engine is an adapter
  (`OcrEnginePort`); the default candidate is
  Tesseract, the optional fallback is PaddleOCR, both
  behind the existing License Gate and pinned in
  `distribution/licenses/model-licenses.json`.
- **Tables** (`DoclingTableExtractor`): structured
  cells/rows/columns as the canonical structure;
  Markdown serialisation as the retrieval view;
  repeated headers preserved across splits.
- **Figures** (`pi_platform/adapters/pdf/assets.py`):
  first-class `AssetRef` records with `page`, `bbox`,
  `caption`, `OCR_text` if present, and graph relations
  `MENTIONS`, `CAPTIONED_BY`, `ON_PAGE`, `IN_SECTION`.
  Image bytes go to local CAS by default.
- **Chunking**: a `DoclingHybridChunker` adapter
  implements `ChunkerPort` for the PDF family only;
  it does not apply to Java/OpenSpec/JAR chunking.

### Embedding / ANN design

- `HashingEmbeddingModel` is kept for unit tests, zero-
  dependency boot, and deterministic smoke tests.
- `EmbeddingGemma2EmbeddingModel` is the first real
  local semantic adapter; it is bound behind the
  `semantic-embeddings` optional dependency group.
- `Qwen3EmbeddingModel` is a separate adapter bound to
  the same `EmbeddingModelPort`. Its vectors are
  persisted in a separate `embedding_profile_hash`
  namespace.
- `HostEmbeddingClient` is an HTTP client adapter to
  the optional host-side accelerator
  (`accelerator/`). The container-side adapter falls
  back to the CPU adapter when the accelerator is
  unavailable.
- `EmbeddingProfile.identity()` is a SHA-256 over the
  canonical serialisation of the profile descriptor.
  The runtime rejects any vector/index/profile
  mismatch; the dense index will not load an ANN
  namespace whose `embedding_profile_hash` does not
  match the active profile.
- `FlatDenseIndex` (kept) and `USearchDenseIndex` (new)
  both implement the existing `DenseIndexPort`. Backend
  selection is `auto | flat | usearch`, driven by
  configuration. `auto` may choose based on
  benchmarked corpus size and recall constraints; the
  architectural invariant is that the choice is data-
  driven, not hard-coded.
- USearch index files are stored under
  `.project-intelligence-cache/indexes/<embedding_profile_hash>/`
  and carry `embedding_profile_hash`,
  `index_schema_version`, `source_generation`,
  `vector_count` in their metadata. If any compatibility
  key changes, the platform rebuilds the index from
  `VectorRecordStorePort` without re-running the
  embedding model.

### Reranker design

- `Bm25LightReranker` is kept as the `minimal` profile
  and as the deterministic fallback when the active
  cross-encoder times out or errors.
- `CrossEncoderRerankerAdapter` becomes a real adapter
  bound to a SentenceTransformers
  `CrossEncoder` (e.g. a compact multilingual model
  selected by configuration) for the `fast` profile.
- `Qwen3RerankerAdapter` is a separate adapter behind
  the `quality` profile, with its own prompt
  template, truncation, and timeouts. It is opt-in and
  remains off by default because the 1.2 GB model
  artifact conflicts with the lightweight
  one-container default (plan §18.1).
- `rerank_text` is built from `document_title`,
  `heading_path`, `raw_chunk`, `caption` (if any),
  `class/method context` (if any), with a hard token
  budget (`max_pair_tokens`, default 1536 — a starting
  experiment, not a permanent contract). Hashes, bbox,
  timestamps, Git SHA, and unrelated metadata are
  excluded. Inferred enrichment is trimmed before raw
  evidence.
- Reranker timeouts, batch sizes, and concurrency are
  bounded; a failure falls back to the RRF ordering
  of the pre-rerank direct candidate pool.

### Retrieval trace and explainability

`RetrievalTrace` is a typed value object attached to
`RetrievalResult`. It is:

- optional in the normal API response (controlled by
  `RetrievalConfig.include_trace`);
- always available in debug / evaluation mode;
- serialisable to JSON;
- visible in Control Plane diagnostics (`/diagnostics/
  traces/...`);
- safe against leaking secret metadata — secret
  detection (`pi_platform/security/secret_provider.py`)
  is applied before persistence.

The trace ID is exposed through the MCP `retrieve_context`
tool result; in debug / admin mode an additional
`project.get_retrieval_trace(trace_id)` tool returns the
full trace.

### Deployment / model profiles

Profiles are configuration presets, not code paths
(plan §24):

```yaml
profiles:
  minimal:        { embedding: hashing, dense: flat, reranker: bm25, ocr: tesseract }
  semantic-cpu:   { embedding: embeddinggemma2-cpu, dense: auto, reranker: bm25, ocr: tesseract }
  semantic-gpu:   { embedding: embeddinggemma2-host, dense: auto, reranker: bm25, ocr: tesseract }
  quality:        { embedding: embeddinggemma2-cpu, dense: usearch, reranker: qwen3-cpu, ocr: tesseract }
  contextualized: { embedding: embeddinggemma2-cpu, dense: usearch, reranker: qwen3-cpu, ocr: tesseract, local_contextualizer: true }
  multimodal:     { embedding: embeddinggemma2-multimodal, dense: usearch, reranker: qwen3-cpu, ocr: tesseract, figure_embedding: true }
```

The host-side accelerator is an **optional deployment
profile** (plan §23). The one-container CPU path remains
fully functional and is the default. The accelerator
exposes a minimal HTTP API
(`GET /health`, `GET /v1/capabilities`,
`POST /v1/embeddings`) with an allow-listed model
registry, pinned model revisions, an ephemeral bearer
token stored outside Git, local/private bind, request
size limit, timeout, and concurrency limit (plan §23.1).

### Evaluation

- **Tier 1** (CI, deterministic, dependency-light): the
  existing `tests/test_retrieval_benchmark.py`. Extended
  with new scenarios for protected exact candidates,
  reserve escalation, source diversity, support-only
  expansion, retrieval trace.
- **Tier 2** (local model, optional, marked
  `@pytest.mark.local_model`): runs the real tokenizer,
  real embedding model, real ANN where configured, real
  reranker. Not run on PR CI unless runners are
  provisioned.
- **Tier 3** (evaluation command):
  `project-intelligence eval retrieval` with
  `evals/corpus/{synthetic,generated-pdf,multilingual,java,requirements}/`
  and a `golden_queries.yaml` per profile. Outputs the
  metrics in plan §28.3 plus a chunk-size sweep report
  on `512 / 768 / 900 / 1200` token budgets
  (plan §28.4).
- A separate `tmp/local/evals/` is supported for
  confidential corpora; the same evaluator runs against
  it locally and is git-ignored.

### Incremental processing rules

`IncrementalIngestionEngine` distinguishes:

- content changed (parser version, source bytes,
  extraction changes) → re-parse;
- enrichment changed (local contextualizer, retrieval
  text builder strategy) → re-enrich, re-embed if
  retrieval text changed;
- embedding model changed (profile) → re-embed, rebuild
  ANN namespace;
- ANN implementation changed (Flat → USearch) → rebuild
  ANN from `VectorRecordStorePort` without re-embedding.

Cache keys are explicit so a Git branch switch reuses
results when content and strategy are unchanged.

### Control Plane / MCP / distribution integration

- Control Plane diagnostics expose
  `Ingestion` (active jobs, PDF parser, OCR mode, page
  batch size), `Chunking` (tokenizer, target/max tokens,
  profile), `Embeddings` (active model/revision, device,
  dimension, normalization, index compatibility),
  `Retrieval` (candidate budgets, primary/reserve sizes,
  reranker profile, debug trace toggle), `Accelerator`
  (health, device, memory, fallback), `Evaluation`
  (latest report).
- MCP `retrieve_context` tool output gains
  `selection_state`, `source/provenance`, `project
  version`, `conflicts`, `support_relationships`,
  `retrieval_trace_id`. The agent skill
  (`distribution/skills/project-intelligence/`) is
  updated to document protected exact candidates,
  reserve escalation, and the trace tool.
- Distribution: `pyproject.toml` optional dependency
  groups `documents`, `semantic-embeddings`, `ann`,
  `reranking`, `accelerator`, `multimodal` keep the
  minimal container slim. License Gate
  (`distribution/licenses/model-licenses.json`)
  records model revisions and license terms.

### ADR alignment

New ADRs to author alongside implementation
(see `context-impact.md`):

- `0024-rich-document-graph-as-additive-submodel`
  (DocumentRevision / Page / DocumentElement /
  SourceAnchor as additive submodel; the generic
  `Document` / `Section` / `Chunk` remain the public
  surface).
- `0025-rerank-direct-before-graph-expansion` (stage
  order rationale and the DirectCandidate vs
  SupportEvidence split).
- `0026-embedding-profile-identity-and-vector-namespace`
  (profile identity, compatibility key, ANN rebuild
  semantics).
- `0027-inference-policy-separate-from-source-policy`
  (InferencePolicy vs SourcePersistencePolicy).
- `0028-usearch-as-default-ann-backend` (configuration-
  driven selection; no hard-coded corpus size threshold).

## Affected modules / interfaces

### New core modules

- `pi_platform/core/canonical/document_graph.py`
- `pi_platform/core/ingest/token_budget.py`
- `pi_platform/core/ingest/retrieval_text_builder.py`
- `pi_platform/core/ingest/local_contextualizer.py`
- `pi_platform/core/retrieval/query_features.py`
- `pi_platform/core/retrieval/selection.py`
- `pi_platform/core/retrieval/retrieval_trace.py`

### New port modules

- `pi_platform/ports/ingest/tokenizer.py`
- `pi_platform/ports/ingest/retrieval_text_builder.py`
- `pi_platform/ports/ingest/ingestion_job_store.py`
- `pi_platform/ports/retrieval/selection.py`
- `pi_platform/ports/runtime/vector_record_store.py`

### New adapter modules

- `pi_platform/adapters/pdf/prescan.py`
- `pi_platform/adapters/pdf/docling_pdf_adapter.py`
- `pi_platform/adapters/pdf/docling_mapper.py`
- `pi_platform/adapters/pdf/ocr_policy.py`
- `pi_platform/adapters/pdf/assets.py`
- `pi_platform/adapters/pdf/docling_chunker.py`
- `pi_platform/adapters/ingest/docling_hybrid_chunker.py`
- `pi_platform/adapters/ingest/embeddinggemma2_tokenizer.py`
- `pi_platform/adapters/ingest/docling_local_contextualizer.py`
- `pi_platform/adapters/runtime/usearch_dense_index.py`
- `pi_platform/adapters/runtime/sqlite_vector_record_store.py`
- `pi_platform/adapters/runtime/sqlite_document_graph_store.py`
- `pi_platform/adapters/runtime/sqlite_ingestion_job_store.py`
- `pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py`
- `pi_platform/adapters/retrieval/qwen3_embedding_model.py`
- `pi_platform/adapters/retrieval/qwen3_reranker.py`
- `pi_platform/adapters/retrieval/host_embedding_client.py`

### Modified modules (additive only)

- `pi_platform/core/canonical/value_types.py` — extend
  `Chunk` with `anchors: Sequence[SourceAnchor]`.
- `pi_platform/ports/ingest/source_adapter.py` — extend
  `SourceAdapterPort` with PDF resumable hooks; replace
  `PLANNED_ADAPTERS.pdfplumber` with Docling.
- `pi_platform/ports/ingest/chunker.py` — extend
  `ChunkerContext` additively with
  `target_tokens`, `max_tokens`, `min_tokens`,
  `tokenizer_id`, `merge_peers`.
- `pi_platform/ports/ingest/context_enricher.py` — add
  retrieval-text builder contract.
- `pi_platform/adapters/ingest/chunkers.py` — wrap each
  existing structural chunker with the token budget
  normalizer.
- `pi_platform/adapters/ingest/layered_context_enricher.py` —
  invoke the new `RetrievalTextBuilder` so the
  embedding input actually reflects the LLM suggestion
  (when enabled).
- `pi_platform/adapters/ingest/local_pipeline_driver.py` —
  bind the PDF family to the new resumable job model.
- `pi_platform/ports/retrieval/hybrid_retrieval.py`,
  `pi_platform/core/retrieval/hybrid_retrieval.py` —
  introduce `QueryFeatures`; preserve pure-identifier
  fast path; for mixed queries mark exact candidates
  `PROTECTED` and keep dense/sparse channels.
- `pi_platform/ports/retrieval/multi_stage_retrieval.py`,
  `pi_platform/core/retrieval/multi_stage_retrieval.py` —
  reorder stages per plan §4.2; attach
  `RetrievalTrace`.
- `pi_platform/core/retrieval/context_assembler.py` —
  `PRIMARY > PROTECTED > SUPPORT > RESERVE` order;
  reserve escalation; near-duplicate collapse while
  preserving provenance links.
- `pi_platform/adapters/retrieval/identifier_query_detector.py` —
  also surface `has_free_text` and `quoted_phrases` for
  `QueryFeatures`.
- `pi_platform/core/orchestration/capability_discovery.py` —
  expose profile / model / device / fallback state /
  index compatibility.
- `pi_platform/mcp/server.py` — extend
  `retrieve_context` output; add
  `project.get_retrieval_trace(trace_id)` in debug mode.
- `pi_platform/control/feature_flags.py` — register
  profiles as feature flags.
- `pyproject.toml` — add optional dependency groups
  `documents`, `semantic-embeddings`, `ann`,
  `reranking`, `accelerator`, `multimodal`.
- `distribution/licenses/model-licenses.json` — record
  model revisions.
- `distribution/skills/project-intelligence/...` — agent
  skill updates (plan §33).
- `Makefile`, `harness.py` — add the
  `project-intelligence eval retrieval` command, the
  PDF fixture generator, the chunk-size sweep, and
  the Tier 2 pytest marker.

### Schema / DB impact

- New SQLite tables in `runtime.db`:
  `document_revisions`, `pages`,
  `document_elements`, `assets`, `table_cells`,
  `table_payloads`, `chunk_anchors`, `embeddings`,
  `ingestion_jobs`, `index_state`.
- Migration script in
  `pi_platform/adapters/runtime/migrations/` bumps
  `knowledge_schema_version` from `1` to `2`.
- Existing `runtime_entries` table is preserved;
  existing rows are not rewritten.

## Data / persistence / concurrency impact

- **Concurrency:** ingestion is parallelised per page
  window only. The `IngestionJobStorePort` uses a
  single-writer-per-job model with optimistic
  `next_page` checks. Multi-process embeddings use the
  `LocalContextualizer` cache and the
  `VectorRecordStorePort` upsert with an
  `(chunk_id, embedding_profile_hash)` primary key.
- **Persistence:** ANN index files are runtime-derived
  artefacts under
  `.project-intelligence-cache/indexes/<embedding_profile_hash>/`;
  they are git-ignored. The vector records themselves
  are persisted in `embeddings.vector_payload (BLOB)`;
  re-creating the ANN does not require re-embedding.
- **Reuse:** cache keys
  (`chunk_content_hash`, `retrieval_text_hash`,
  `embedding_profile_hash`, `index_schema_version`,
  `source_generation`, `local_contextualizer_revision`,
  `prompt_version`, `enrichment_strategy_version`,
  `tokenizer_id`, `chunker_strategy_version`,
  `parser_version`) let the platform skip work that
  has not actually changed (plan §30).
- **Memory:** the platform never holds an entire large
  document in memory. PDF ingestion is page-windowed.
  Embedding batches are bounded. The host accelerator
  is the only profile allowed to use GPU memory; the
  one-container CPU path stays within the existing
  default resource limits.
- **CPU fallback:** every GPU / accelerator-dependent
  path has a CPU fallback. The Tier 1 CI benchmark
  must pass on CPU without any optional dependencies.
- **Offline operation:** the platform never requires
  outbound network. Model weight fetches are an
  explicit, audited, one-time action recorded in
  `distribution/licenses/model-licenses.json`.

## Compatibility and migration

- **Backward compatibility:** the additive design means
  no existing accepted requirement body changes.
  Existing target projects with hydrated corpora keep
  their `runtime_entries` and `HashingEmbeddingModel`
  vectors; the new fields are optional.
- **Knowledge schema migration:** version bump
  `1 → 2`; legacy records remain readable; new fields
  default to empty. Migration is reversible (a
  `down` path drops the new tables/columns and
  decrements the version, but only if no v2 records
  exist).
- **PDF migration:** if a target project already
  started a PDF ingestion with the old `pdfplumber`
  placeholder, the platform aborts the partial
  ingestion and re-registers the source. No partial
  state is migrated.
- **Embedding model migration:** switching from
  `HashingEmbeddingModel` to `EmbeddingGemma 2`
  requires a fresh embedding pass. The old
  `HashingEmbeddingModel` namespace remains queryable
  for comparison; the active profile is the new
  namespace. The platform never silently mixes the
  two (plan §13).
- **ANN migration:** switching from `FlatDenseIndex`
  to `USearchDenseIndex` reuses the existing
  `VectorRecordStorePort` records; no re-embedding
  is required. The flat index remains queryable in
  the `minimal` profile.
- **CLI:** `project-intelligence eval retrieval` is
  added without changing existing CLI commands; the
  new flag is opt-in.

## Risks and rollback

| Risk | Mitigation | Rollback |
| --- | --- | --- |
| New ports silently change accepted behaviour | Additive only; new ports are behind capability registration and feature flags | Disable the capability via `pi_platform/control/feature_flags.py`; no accepted requirement body changes. |
| PDF ingestion regression on real-world PDFs | Tier 1 synthetic CI remains green; Tier 2 PDF fixtures (10-page, 100-page, generated 600-page) are part of the acceptance gate (plan §37) | Disable the PDF capability; the platform falls back to the existing behaviour (PDF family declared but no adapter). |
| Tokenizer-aware chunking produces non-deterministic chunk IDs | `Chunk.id` is `hash(chunker_strategy_version || ordered source anchors || tokenizer_id)`. Determinism is enforced by the test plan §36. | Revert to byte-based chunking by setting `chunking.strategy: structural_byte` in the profile. |
| Local LLM hallucinates authoritative metadata | `LocalContextualizer` is forbidden from producing requirement IDs, protocol versions, validFrom/validTo, security class, Git revision, source ID, license. The `InferencePolicy` is separate from `SourcePersistencePolicy`; the central Policy Engine evaluates both. | Disable `local_contextualizer` per profile; deterministic builder is the default. |
| Embedding profile mismatch silently mixed | `EmbeddingProfile.identity()` is a SHA-256 over the canonical descriptor; the dense index refuses to open a namespace whose key does not match. | Reject the operation with a clear, redacted error; re-embed under the active profile. |
| Host accelerator exposes arbitrary model loading | Minimal HTTP API; model IDs from allow-list; pinned revisions; bearer token outside Git; local/private bind; size/timeout/concurrency limits; audit health/model identity but not payload contents. | Bind to `127.0.0.1` only; set accelerator to `enabled: false`; CPU fallback is always available. |
| USearch dependency is unavailable on a target OS | `FlatDenseIndex` is the fallback; `dense_index.backend: flat` overrides `auto`. | Switch the profile to `minimal`. |
| Quality reranker is too heavy for small machines | The Qwen3-Reranker-0.6B profile is `quality` only; `minimal` and `fast` profiles do not load it. | Drop to `minimal` profile; reranker becomes the BM25-light fallback. |
| Multimodal figure model loading bloats the minimal container | `multimodal` is a separate profile; `multimodal.figures` is off by default; the agent skill and Control Plane diagnostics surface the active profile. | Disable the multimodal capability via the capability registry. |
| Schema migration corrupts legacy data | Migration is additive; a reversible down path is provided; CI tests cover the round-trip. | Run the down migration; restore from Git canonical knowledge (canonical truth is Git, runtime is rebuildable — plan §34.1). |
