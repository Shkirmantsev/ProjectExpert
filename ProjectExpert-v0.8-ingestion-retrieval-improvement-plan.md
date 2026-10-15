# ProjectExpert — Incremental Ingestion & Retrieval Improvement Plan

**Status:** additional implementation instruction / delta over `Project Intelligence Platform Architecture v0.8`  
**Repository baseline:** `Shkirmantsev/ProjectExpert`, branch `dev`  
**Reviewed:** 2026-10-14  
**Scope:** ingestion, chunking, local-model enrichment, embeddings, ANN, reranking, PDF/document understanding, retrieval evaluation  
**Non-goal:** redesigning the already implemented v0.8 platform foundation

---

## 1. Executive decision

Do **not** replace the current v0.8 architecture.

The current repository already implements the correct high-level boundaries:

- canonical Git knowledge vs runtime working state;
- ports/adapters;
- content addressing;
- local source inbox;
- structured Java/JAR intelligence;
- SQLite runtime store;
- sparse/full-text/dense index ports;
- hybrid retrieval;
- multi-stage retrieval;
- metadata filtering;
- graph expansion;
- reranker port;
- context assembler;
- local-LLM port;
- query orchestrator;
- MCP/skill distribution;
- Control Plane;
- enterprise security boundary.

The additional ingestion/retrieval v2 design should therefore be treated as a **production-quality refinement of existing ports**, not as a competing architecture.

The most useful improvements that are not yet fully implemented in the `dev` branch are:

1. **Rich canonical document graph for PDF/Office documents** instead of flattening imported documents directly to sections/chunks.
2. **Resumable, batched PDF ingestion** with selective OCR, page/element provenance and first-class tables/figures.
3. **Tokenizer-aware chunk sizing** layered on top of the already existing structural chunk strategies.
4. A real distinction between:
   - `raw_text`,
   - semantic `retrieval_text`,
   - exact/filterable `metadata`.
5. **Actually using optional local-LLM contextualization in embedding input**, rather than only storing its suggestion as metadata.
6. **A production semantic embedding backend**; the current semantic adapter is a contract/stub while the hashing model is the functional fallback.
7. **A production ANN adapter** such as USearch behind the already existing `DenseIndexPort`, while keeping flat search for small corpora.
8. **Embedding profile identity and vector-space isolation** so vectors from different models/dimensions/revisions can never be mixed.
9. **Non-destructive reranking** with `PRIMARY`, `RESERVE`, `PROTECTED`, `SUPPORT` and duplicate states.
10. **Rerank direct evidence before graph/hierarchy expansion.**
11. **Protected exact candidates combined with semantic retrieval** for mixed queries such as “where is ILO-5193 handled?”.
12. **Reserve escalation and source diversity** inside Context Assembly.
13. **Persistent retrieval trace** for evaluation/debugging.
14. **Real-corpus model/chunking evaluation**, in addition to the existing deterministic synthetic benchmark.
15. Optional **host-side embedding acceleration** as a deployment profile, without making GPU availability mandatory.
16. Optional **multimodal figure retrieval**, after the text/PDF pipeline is proven.

These improvements should be implemented incrementally and must preserve the current v0.8 invariants.

---

# 2. What is already implemented and should NOT be rebuilt

The following current code is structurally aligned with the desired architecture and should be extended rather than replaced.

| Area | Current implementation | Decision |
|---|---|---|
| Canonical model | `pi_platform/core/canonical/` | Keep; add rich-document types additively |
| Content addressing | `pi_platform/core/canonical/content_address.py` | Keep |
| Git/runtime sync | `pi_platform/core/sync/` | Keep |
| Source registry | `pi_platform/ports/ingest/source_adapter.py` | Keep; PDF family already exists |
| Ingestion pipeline | `pi_platform/adapters/ingest/local_pipeline_driver.py` | Keep; add richer adapters/stages behind ports |
| Local source inbox | `pi_platform/core/ingest/local_source_inbox_scanner.py` | Keep |
| Java/JAR parsing | `pi_platform/adapters/java/` | Keep; already substantially implemented |
| Structural chunk strategies | `pi_platform/adapters/ingest/chunkers.py` | Keep; add token-budget normalization |
| Three-layer enrichment contract | `pi_platform/ports/ingest/context_enricher.py` | Keep |
| SQLite runtime store | `pi_platform/adapters/runtime/sqlite_runtime_store.py` | Keep as operational runtime store |
| Sparse/FTS search | `bm25_sparse_index.py`, `sqlite_fts_full_text_index.py` | Keep |
| Dense index port | `pi_platform/ports/runtime/dense_index.py` | Keep |
| Flat dense index | `pi_platform/adapters/runtime/flat_dense_index.py` | Keep as small-corpus fallback |
| Hybrid retrieval + RRF | `pi_platform/core/retrieval/hybrid_retrieval.py` | Keep, correct mixed exact-query behavior |
| Metadata filter | `pi_platform/core/retrieval/metadata_filter.py` | Keep |
| Multi-stage retrieval | `pi_platform/core/retrieval/multi_stage_retrieval.py` | Keep API; revise internal stage order |
| Context assembler | `pi_platform/core/retrieval/context_assembler.py` | Keep; extend selection semantics |
| Reranker port | `pi_platform/ports/retrieval/reranker.py` | Keep |
| BM25-light fallback | `pi_platform/core/retrieval/reranker.py` | Keep as zero-dependency fallback |
| Query orchestrator | `pi_platform/core/orchestration/query_orchestrator.py` | Keep |
| Local LLM port | `pi_platform/core/orchestration/local_llm.py` | Keep; bind a real adapter only optionally |
| Retrieval benchmark framework | `tests/test_retrieval_benchmark.py` | Keep; add real integration/evaluation tier |
| MCP / skill / Control Plane / security | existing `pi_platform` modules | Keep; expose new capabilities through them |

The improvement project must preserve these boundaries.

---

# 3. Concrete gaps found in the current `dev` branch

## 3.1 PDF is declared but not implemented

`SourceContentFamily.PDF` already exists in:

```text
pi_platform/ports/ingest/source_adapter.py
```

but:

```text
pi_platform/adapters/pdf/
```

currently contains only `__init__.py`.

The old `PLANNED_ADAPTERS` list still references a simple `pdfplumber` plan. The richer v2 design provides a materially better PDF ingestion model and should supersede that planned default.

### Required change

Implement a `DoclingPdfAdapter` behind the existing `SourceAdapterPort`.

Do **not** create a parallel ingestion architecture.

---

## 3.2 Current document model loses rich PDF structure

Current canonical types are centered around:

```text
Source
Document
Section
Chunk
Entity
Relation
Evidence
```

This is sufficient for Markdown/code but not enough to faithfully retain:

- page geometry;
- reading order;
- tables;
- figures;
- captions;
- formulas;
- page-level OCR provenance;
- binary asset references;
- relation of a chunk to source elements.

### Required change

Add an additive rich-document submodel without replacing the existing universal model.

Recommended new file:

```text
pi_platform/core/canonical/document_graph.py
```

Recommended types:

```text
DocumentRevision
Page
DocumentElement
ElementKind
SourceAnchor
AssetRef
TableGrid
IngestionCheckpoint
```

The existing `Document`, `Section`, and `Chunk` remain the generic public model.

The rich document graph is projected into those generic types.

---

## 3.3 Chunk sizing is structural but byte-based

Current `PlainTextChunker` correctly respects paragraphs/sections, but the hard size mechanism is:

```text
max_chunk_bytes
```

with UTF-8 byte splitting.

This is a good safety fallback but is not aligned to the actual embedding tokenizer.

### Required change

Retain structural strategies and add token-aware normalization after semantic boundary selection.

The rule becomes:

```text
semantic boundary
    ↓
structural chunk candidate
    ↓
embedding-tokenizer budget
    ↓
split only if oversized
    ↓
merge compatible peers if undersized
```

Do **not** replace Requirement/Protocol/Table/Architecture chunkers with one generic model chunker.

---

## 3.4 Optional local-LLM enrichment currently does not improve retrieval text

`LayeredContextEnricher` already calls an optional local LLM and safely restricts it to suggestions such as:

```text
contextPrefix
entities
relations
```

but that suggestion is currently stored under metadata extensions as an assumption.

The final `ContextualChunk.contextPrefix` is still built from deterministic fields such as:

```text
section
sourcePath
requirementId
```

Therefore the local LLM does not currently enrich the actual text that will be embedded.

### Required change

Introduce a separate, explicit:

```text
RetrievalTextBuilderPort
```

or equivalent application service.

It builds:

```text
retrieval_text =
    deterministic semantic context
    + accepted local-model context
    + raw_text
```

The model-generated part remains marked `INFERRED`/`ASSUMPTION` and may never overwrite authoritative metadata.

---

## 3.5 Current semantic embedding adapter is not a production implementation

The functional default today is the deterministic hashing model.

`MultilingualSentenceTransformerEmbeddingModel` validates that `sentence-transformers` exists but its `embed()` and `embed_batch()` methods still raise an error.

This is a correct placeholder architecture but not a production semantic embedding implementation.

### Required change

Implement at least one real local semantic embedding adapter.

Recommended evaluation profiles:

```text
embeddinggemma2
qwen3-embedding-0.6b
```

Do not hard-code one model into the core.

---

## 3.6 Current dense index is flat

The runtime contains a `FlatDenseIndex`.

That is a good fallback and test implementation.

There is no current USearch adapter in `pi_platform`.

### Required change

Add a production ANN adapter behind the existing `DenseIndexPort`.

Recommended:

```text
FlatDenseIndex
    = small-corpus / deterministic fallback

USearchDenseIndex
    = larger-corpus ANN profile
```

The runtime chooses through configuration/capabilities.

---

# 4. Retrieval correctness issues that should be fixed before adding larger models

This work has the highest leverage because it improves correctness without requiring model downloads.

---

## 4.1 Mixed identifier queries currently lose semantic retrieval

Current behavior in `HybridRetrievalCore` is approximately:

```text
if query contains an engineering identifier:
    return exact_lookup(identifier)
```

This is correct for a pure identifier query:

```text
ILO-5193
```

but not for:

```text
Why is ILO-5193 handled in PackingService?
```

The latter contains both:

- protected exact evidence;
- semantic intent.

### Required behavior

Introduce query analysis:

```text
QueryFeatures
├── identifiers
├── quoted_phrases
├── has_free_text
├── target_document
├── target_symbol
└── filters
```

Routing:

```text
pure identifier
    → exact-only fast path

identifier + meaningful prose
    → exact candidates marked PROTECTED
    + dense candidates
    + sparse candidates
    → RRF/selection
```

### Files

Modify:

```text
pi_platform/core/retrieval/hybrid_retrieval.py
pi_platform/ports/retrieval/hybrid_retrieval.py
pi_platform/adapters/retrieval/identifier_query_detector.py
```

Add:

```text
pi_platform/core/retrieval/query_features.py
```

### Tests

Add cases:

```text
"ILO-5193"
"Where is ILO-5193 implemented?"
"Explain PSB_FINISH_PACK timeout behavior"
"GEN_3.0.03 FinishPack"
```

Acceptance:

- pure-ID query avoids dense/sparse calls;
- mixed-ID query retains exact hit **and** executes normal hybrid retrieval.

---

## 4.2 Current graph/hierarchy expansion is performed before reranking

Current `MultiStageRetrievalCore` effectively does:

```text
direct candidates
→ metadata
→ graph expansion
→ hierarchy expansion
→ merge all
→ rerank
```

This is semantically suboptimal.

A parent section, neighboring chunk, figure caption, or implementation relation is frequently **supporting evidence**, not the best direct answer passage.

Forcing support nodes through the same reranker can:

- displace direct passages;
- waste reranker CPU;
- distort ranking;
- fail when support records do not have the same text shape as direct chunks.

### Required stage order

Change to:

```text
1. query analysis
2. exact / dense / sparse candidate generation
3. metadata/version/security constraints
4. RRF fusion
5. pre-rerank direct candidate pool
6. cross-encoder / fallback rerank DIRECT candidates
7. selection → PRIMARY / RESERVE / PROTECTED
8. graph expansion from selected primary/protected seeds
9. hierarchy / adjacent / figure / table expansion
10. mark expanded nodes SUPPORT
11. context assembly
12. reserve escalation if necessary
```

### Important compatibility issue

`RetrievalHit.source` currently allows only:

```text
dense
sparse
exact
hybrid
```

while graph/hierarchy code attempts to create hits with sources such as:

```text
graph
hierarchy
```

Do not solve this by simply growing `RetrievalHit.source` forever.

Prefer separating:

```text
DirectCandidate
```

from:

```text
SupportEvidence
```

or introduce a wrapper that distinguishes ranking candidates from context-support items.

This makes stage semantics explicit.

---

# 5. Non-destructive candidate selection

The strongest retrieval idea from the v2 design is to stop treating reranking as destructive `top_k`.

Introduce a selection layer.

Recommended new module:

```text
pi_platform/core/retrieval/selection.py
```

Recommended state:

```python
SelectionState:
    PRIMARY
    RESERVE
    PROTECTED
    SUPPORT
    DROPPED_DUPLICATE
```

Recommended candidate trace:

```text
CandidateTrace
├── chunk_id
├── dense_rank
├── sparse_rank
├── exact_match
├── rrf_rank
├── rrf_score
├── rerank_rank
├── rerank_score
├── selection_state
├── protected_reason
├── duplicate_of
├── source_document_id
└── trace_reasons[]
```

Do not place all of this into canonical Git knowledge.

This is runtime/evaluation state.

---

## 5.1 Initial configurable candidate budgets

Use the v2 values as **starting profiles, not permanent constants**:

```yaml
retrieval:
  dense_candidates: 80
  lexical_candidates: 80
  pre_rerank_pool: 48
  primary_top_k: 8
  reserve_top_k: 24
```

These values must later be tuned by evaluation.

---

## 5.2 Protected candidates

A candidate may be protected by:

- exact engineering identifier;
- quoted phrase;
- exact code symbol;
- explicit document ID;
- explicit requirement ID;
- explicit heading;
- direct source request.

Protected candidates survive reranking unless excluded by a hard policy filter:

```text
wrong Git version
security denied
source explicitly excluded
invalid/stale runtime record
```

Relevance ranking must never override authorization/version correctness.

---

## 5.3 Reserve pool

The reserve pool is retained after reranking.

It is used when:

- primary chunks are near-duplicates;
- the answer has multiple subquestions;
- a needed source type is absent;
- conflict verification requires more evidence;
- Context Assembler still has useful budget;
- an answer verifier requests more evidence.

The reserve pool must retain provenance and all ranking scores.

---

## 5.4 Source diversity

Apply a **soft** source diversity limit only to `PRIMARY`.

Example initial value:

```yaml
max_primary_chunks_per_source: 3
```

Do not apply this limit when the user explicitly targets a specific document.

Do not apply the limit to `RESERVE`.

---

# 6. Context Assembler changes

Current Context Assembler already does:

- deduplication;
- authority preference;
- budget enforcement;
- conflict detection;
- uncertainty surfacing;
- citations.

Keep all of that.

Add:

```text
PRIMARY
PROTECTED
SUPPORT
RESERVE
```

awareness.

Recommended order:

```text
1. protected direct evidence
2. authoritative PRIMARY evidence
3. other PRIMARY evidence
4. mandatory SUPPORT nodes
5. conflict-support evidence
6. reserve escalation for uncovered subtopics
7. optional additional SUPPORT
8. stop at context budget
```

Add near-duplicate collapse by normalized content hash/similarity while preserving links to the collapsed equivalents.

Do not discard duplicate provenance.

---

# 7. Retrieval trace and explainability

Add a retrieval trace object to `RetrievalResult`.

Recommended:

```text
RetrievalTrace
├── query_features
├── active_filters
├── exact_candidates
├── dense_candidates
├── sparse_candidates
├── fusion
├── reranker
├── selection
├── graph_expansion
├── hierarchy_expansion
├── budget_decisions
└── timings
```

The trace should be:

- optional for normal API responses;
- always available in debug/evaluation mode;
- serializable to JSON;
- visible in Control Plane diagnostics;
- safe against leaking secret metadata.

This makes retrieval failures debuggable.

---

# 8. Tokenizer-aware chunking without destroying existing strategies

The current structural chunkers are valuable and should remain.

Introduce:

```text
TokenizerPort
TokenBudget
TokenBudgetNormalizer
```

Recommended port:

```python
class TokenizerPort:
    def count(self, text: str) -> int: ...
    def truncate(self, text: str, max_tokens: int) -> str: ...
    def identity(self) -> str: ...
```

Extend `ChunkerContext` additively:

```text
max_chunk_bytes     # retain as hard safety limit
target_tokens
max_tokens
min_tokens
tokenizer_id
merge_peers
```

Do not remove `max_chunk_bytes`; it remains a protection against pathological input.

---

## 8.1 Chunking composition

Use two stages:

```text
SemanticBoundaryStrategy
        ↓
TokenBudgetNormalizer
```

Examples:

### Markdown/plain documents

```text
heading/section
→ paragraph/list boundary
→ token-size split
→ compatible peer merge
```

### Requirements

```text
requirement ID
→ paragraph/statement boundary
→ token-size fallback
```

### Protocol documents

```text
protocol message
→ field/paragraph boundary
→ token-size fallback
```

### Tables

```text
table
→ row groups
→ repeat header
→ token-size check
```

### Java

Keep AST/symbol boundaries.

For an oversized method:

```text
method
→ statement/block boundaries
→ token budget
```

Do not run generic prose chunking over code.

---

# 9. Docling HybridChunker integration

Use Docling `HybridChunker` specifically where a `DoclingDocument` exists.

It is useful because it combines:

```text
hierarchical document boundaries
+
embedding-tokenizer-aware split
+
optional merge of compatible peers
```

and supports repeating table headers.

Do **not** introduce Docling into Java/OpenSpec/JAR chunking.

Recommended adapter:

```text
pi_platform/adapters/pdf/docling_chunker.py
```

or a document-specific chunker under:

```text
pi_platform/adapters/ingest/
```

while still implementing the existing `ChunkerPort`.

Initial chunk sizes such as:

```text
512
768
900
1200
```

must be benchmarked. `900` is only an initial candidate.

---

# 10. Introduce explicit `retrieval_text`

The model should not embed raw metadata JSON.

For each chunk maintain these concepts:

```text
raw_text
    exact source text

retrieval_text
    text actually passed to embedding model

metadata
    exact filters, provenance, version/security fields
```

The existing model already has:

```text
Chunk.rawText
Chunk.contextualText
ContextualChunk.contextPrefix
```

Do not create duplicate truth unnecessarily.

Define one deterministic mapping:

```text
retrieval_text =
    ContextualChunk.contextPrefix
    + "\n\n"
    + Chunk.rawText
```

`Chunk.contextualText` should either:

1. become the persisted result of that builder, or
2. be deprecated in favor of a single clearly defined representation.

Do not allow three competing meanings for the same semantic text.

---

## 10.1 RetrievalTextBuilder

Add:

```text
pi_platform/ports/ingest/retrieval_text_builder.py
pi_platform/core/ingest/retrieval_text_builder.py
```

Inputs:

```text
Chunk
Document
Section
Metadata
optional local enrichment
```

Output:

```text
RetrievalText
├── text
├── strategy_version
├── deterministic_parts
├── inferred_parts
└── content_hash
```

Semantic inputs may include:

- document title;
- normalized heading path;
- business concept;
- requirement ID when semantically meaningful;
- Java package/class/method signature;
- relevant caption;
- protocol/system name;
- local-LLM contextual sentence;
- raw chunk text.

Do **not** embed:

- absolute filesystem path;
- SHA;
- Git commit hash;
- timestamps;
- bbox coordinates;
- security label;
- processing version.

These remain metadata.

---

# 11. Local-LLM contextualization: use the existing port correctly

The current v0.8 already has a `LocalLLMPort`.

Do not invent another agent/model abstraction.

Instead add a narrow:

```text
LocalContextualizer
```

application service that uses `LocalLLMPort`.

Its job is limited to indexing-time enrichment:

```text
document title
heading path
neighbor text
raw chunk
        ↓
small local LLM
        ↓
1–3 sentence semantic context
```

Allowed outputs:

```text
context summary
candidate entities
candidate relations
query aliases/glossary hints
```

Forbidden authoritative outputs:

```text
requirement ID
protocol version
validFrom/validTo
security class
Git revision
source ID
license
```

Those come only from deterministic/trusted sources.

---

## 11.1 Separate source persistence policy from model exposure policy

Do not use:

```text
LOCAL_ONLY / REFERENCE / SNAPSHOT
```

as the only criterion for whether a model may see content.

That policy describes persistence.

Introduce a separate inference policy, for example:

```text
NO_MODEL
LOCAL_MODEL_ALLOWED
EXTERNAL_MODEL_ALLOWED
```

This avoids the current coupling where local-LLM use is indirectly tied to source persistence type.

Security policy remains authoritative.

---

## 11.2 Contextualization cache key

Cache local contextualization using:

```text
chunk_content_hash
+
contextualizer_model_revision
+
prompt_version
+
enrichment_strategy_version
```

A Git branch switch should reuse the result if the underlying content and strategy are unchanged.

---

# 12. Production embedding implementation

Keep the existing `EmbeddingModelPort`.

Add production adapters.

Recommended files:

```text
pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py
pi_platform/adapters/retrieval/qwen3_embedding_model.py
pi_platform/adapters/retrieval/host_embedding_client.py
```

Do not replace:

```text
HashingEmbeddingModel
```

It remains valuable for:

- unit tests;
- zero-dependency boot;
- deterministic smoke tests.

---

# 13. Embedding profile identity

A vector index must be namespaced by full embedding identity.

Introduce a descriptor such as:

```text
EmbeddingProfile
├── provider
├── model_id
├── model_revision
├── modality
├── output_dimension
├── normalization
├── instruction_profile
├── tokenizer_id
└── strategy_version
```

Index compatibility key:

```text
SHA256(canonical(EmbeddingProfile))
```

The runtime must reject a vector/index mismatch.

Never mix:

```text
EmbeddingGemma vectors
Qwen embedding vectors
different dimensions
different normalization modes
different incompatible revisions
```

in one ANN namespace.

---

# 14. EmbeddingGemma 2 profile

EmbeddingGemma 2 is a good **evaluation candidate** for this project because it supports text/code plus optional multimodal retrieval in one embedding family.

Recommended initial text profile:

```yaml
embedding:
  family: embeddinggemma2
  dimension: 512
  normalize: true
```

Do not treat `512` as permanently optimal.

The model supports Matryoshka dimensional truncation; when truncating, normalization after truncation is mandatory.

Recommended runtime profiles:

```text
compact:
    256 or 512 vector dimension
    text only
    CPU or accelerator

quality:
    768 vector dimension
    text only

multimodal:
    compatible visual/audio encoders enabled
```

Do not claim a strict VRAM number before measuring the actual selected encoder/runtime/precision.

---

# 15. Qwen3 Embedding profile

Keep Qwen3-Embedding-0.6B as a separate text/code evaluation profile.

It is useful for:

- multilingual retrieval;
- code retrieval;
- long input;
- instruction-aware retrieval.

Never place its vectors in an EmbeddingGemma index.

If both profiles are enabled:

```text
index_gemma
index_qwen
```

and fuse **ranked results**, not raw vectors.

Do not enable two heavy embedding profiles in the normal default installation.

---

# 16. Persist embedding records separately from ANN

The ANN index must be disposable.

Add an embedding record store:

```text
VectorRecordStorePort
```

Recommended record:

```text
VectorRecord
├── chunk_id
├── content_hash
├── embedding_profile_hash
├── model_revision
├── dimension
├── normalization
├── vector_payload/reference
└── created_from_retrieval_text_hash
```

Implementation options:

```text
SQLite BLOB
or
content-addressed binary vector store referenced by SQLite
```

Do not store large float arrays as JSON.

This permits:

```text
delete ANN index
→ rebuild ANN
```

without re-running the embedding model.

---

# 17. Production ANN adapter

Add:

```text
pi_platform/adapters/runtime/usearch_dense_index.py
```

implementing existing:

```text
DenseIndexPort
```

Keep:

```text
FlatDenseIndex
```

for small corpora and deterministic tests.

Selection should be configuration/capability driven:

```yaml
dense_index:
  backend: auto
```

`auto` may choose flat vs ANN based on benchmarked corpus thresholds.

Do not hard-code an arbitrary threshold as an architectural invariant.

---

## 17.1 ANN persistence

USearch index files are runtime-derived artifacts.

Store under:

```text
.project-intelligence-cache/indexes/
```

not Git.

Index metadata must include:

```text
embedding_profile_hash
index_schema_version
source_generation
vector_count
```

If any compatibility key changes, rebuild the ANN index.

---

# 18. Reranker strategy

Do not make one heavy reranker mandatory.

Retain profiles.

Recommended:

```text
minimal:
    BM25-light fallback

fast:
    optional compact cross-encoder if a validated multilingual model is selected

quality:
    Qwen3-Reranker-0.6B on CPU

experimental:
    ColBERT-style adapter
```

The current `CrossEncoderRerankerAdapter` is still a placeholder and should be made functional.

The Qwen model should get its own adapter if its inference semantics differ from a normal SentenceTransformers `CrossEncoder`.

---

## 18.1 Why Qwen should be optional rather than mandatory

The v2 design correctly notes that CPU inference avoids consuming constrained GPU VRAM.

However the Qwen3-Reranker-0.6B model artifact is approximately 1.2 GB before runtime overhead.

Therefore making it mandatory would conflict with the platform's lightweight/portable objective on smaller developer machines.

Use it as:

```text
quality profile
```

until benchmarks demonstrate acceptable:

- RAM;
- startup time;
- batch latency;
- p95 query latency.

---

## 18.2 Rerank text

Build a separate:

```text
rerank_text
```

with only useful semantic information:

```text
document title
heading path
raw chunk
relevant caption
class/method context
```

Do not send:

```text
hashes
bbox
timestamps
Git SHA
unrelated metadata
```

to the cross encoder.

Set a bounded token budget; `1536` is a reasonable initial experiment, not a permanent contract.

Trim inferred enrichment before raw evidence.

---

# 19. Rich PDF / document graph

This is the largest new ingestion capability and should be an independent OpenSpec change.

Recommended neutral graph:

```text
Source
 └── DocumentRevision
      ├── Page
      │    ├── DocumentElement
      │    │    ├── Heading
      │    │    ├── Paragraph
      │    │    ├── List
      │    │    ├── Table
      │    │    ├── Figure
      │    │    └── Formula
      │    └── AssetRef
      ├── Section projection
      ├── Chunk projection
      └── Relations
```

Docling types must stop at the adapter boundary.

The core knows only ProjectExpert-neutral types.

---

## 19.1 Deterministic IDs

Recommended:

```text
source_id
    = hash(normalized source URI)

revision_id
    = hash(file bytes)

element_id
    = hash(revision_id + page + type + geometry + content hash)

asset_id
    = hash(asset bytes)

chunk_id
    = hash(chunking strategy version + ordered source anchors)
```

Also retain a non-authoritative:

```text
semantic_key
```

for cross-revision matching.

Example:

```text
heading path + element kind + local ordinal
```

The semantic key helps identify a moved/edited section but does not replace exact hash identity.

---

# 20. Source anchors

Add exact source anchors so every retrieval result can point to the original document structure.

Recommended:

```text
SourceAnchor
├── revision_id
├── page
├── element_id
├── bbox
├── line/ordinal
└── asset_id
```

Extend `Chunk` additively with:

```text
anchors: Sequence[SourceAnchor]
```

or introduce an equivalent separate relation.

Because this changes the canonical schema:

1. bump knowledge schema version;
2. add migration;
3. add canonical round-trip tests;
4. run migration guard.

Do not hide important provenance only inside a free-form `extensions` map.

---

# 21. PDF ingestion pipeline

Implement behind the existing PDF source family.

Recommended files:

```text
pi_platform/adapters/pdf/prescan.py
pi_platform/adapters/pdf/docling_pdf_adapter.py
pi_platform/adapters/pdf/docling_mapper.py
pi_platform/adapters/pdf/ocr_policy.py
pi_platform/adapters/pdf/assets.py
pi_platform/adapters/pdf/docling_chunker.py
```

---

## 21.1 Stage A — cheap prescan

Before Docling:

```text
hash file
read page count
read metadata
sample text layer
resolve revision_id
check completed ingestion revision
```

Use a cheap PDF reader for this stage.

If the exact revision and ingestion strategy already exist, skip expensive parsing.

---

## 21.2 Stage B — batched parse

Do not convert a 600-page document as one in-memory transaction.

Starting profile:

```yaml
page_batch_size: 32
boundary_context_pages: 1
```

Pattern:

```text
parse 1..33      persist 1..32
parse 32..65     persist 33..64
...
```

Only the owned page window is persisted; neighboring pages are context.

Every batch commits transactionally.

---

## 21.3 Persistent ingestion jobs

Add a dedicated port:

```text
IngestionJobStorePort
```

and SQLite adapter.

State:

```text
job_id
source_id
revision_id
strategy_version
state
next_page
completed_ranges
failed_range
error
started_at
updated_at
```

States:

```text
PENDING
RUNNING
PAUSED
FAILED_RETRYABLE
FAILED_PERMANENT
COMPLETED
CANCELLED
```

A crash at page 417 must not invalidate completed batches.

---

## 21.4 OCR policy

Never OCR all pages by default.

Policy:

```text
usable native text?
   yes → native text + layout
         OCR only image/bitmap regions when needed
   no  → full-page OCR
```

OCR engine remains an adapter.

Default candidate:

```text
Tesseract
```

Optional fallback:

```text
PaddleOCR
```

Both remain subject to the repository License Gate and pinned package/model inventory.

---

## 21.5 Tables

Store three views:

```text
structured cells/rows/columns
text/Markdown serialization for retrieval
source provenance / caption / page geometry
```

When split, repeat the header.

The canonical structure is not the Markdown serialization.

---

## 21.6 Figures

A figure should be first-class evidence.

Store:

```text
asset id
content hash
page
bbox
caption
OCR text if present
nearby explanatory elements
relations
optional visual embedding record
```

Graph examples:

```text
chunk → MENTIONS → figure
figure → CAPTIONED_BY → caption
figure → ON_PAGE → page
figure → IN_SECTION → section
```

Image bytes go to local CAS by default, not Git.

Whether an approved snapshot stores an asset in Git/LFS remains source-policy dependent.

---

# 22. Runtime storage extension without replacing RuntimeStorePort

Do not turn `RuntimeStorePort` into a giant relational API.

Add focused ports:

```text
DocumentGraphStorePort
IngestionJobStorePort
VectorRecordStorePort
```

SQLite adapters can share the same physical:

```text
runtime.db
```

but remain logically decoupled.

Recommended new SQLite tables:

```text
document_revisions
pages
document_elements
assets
table_cells / table_payloads
chunk_anchors
embeddings
ingestion_jobs
index_state
```

Existing generic `runtime_entries` remains useful for canonical runtime objects.

---

# 23. Host-side embedding accelerator

This is useful but should be an **optional deployment profile**, not a core requirement.

Reason:

- Windows/Linux GPU runtimes differ;
- Docker/Podman GPU setup is environment-specific;
- the one-container CPU profile must remain functional.

Recommended structure:

```text
Host OS
├── optional ProjectExpert accelerator
│   ├── approved model registry
│   ├── GPU backend
│   └── local HTTP API
└── ProjectExpert container
    └── HostEmbeddingClient
```

Minimal API:

```text
GET /health
GET /v1/capabilities
POST /v1/embeddings
```

Do not expose arbitrary model loading or command execution.

---

## 23.1 Accelerator security

Requirements:

- fixed inference operations only;
- model IDs from allow-list;
- pinned model revisions;
- ephemeral bearer token;
- token outside Git;
- local/private bind;
- firewall requirement if wide bind is unavoidable;
- request size limit;
- timeout;
- concurrency limit;
- audit health/model identity but never payload contents by default.

---

## 23.2 CPU fallback

Always support:

```text
accelerator available
    → host embedding backend

accelerator unavailable
    → container CPU embedding backend
```

Same:

```text
EmbeddingProfile
```

must identify the semantic vector space independent of device.

A CPU-generated vector and GPU-generated vector are compatible only when the model revision and all embedding settings are identical.

---

# 24. Deployment/model profiles

Add explicit profiles instead of silently loading all models.

Recommended:

```text
minimal
    hashing embedding
    flat dense
    FTS/BM25
    no local LLM
    BM25-light reranker

semantic-cpu
    production text embedding on CPU
    flat/ANN auto
    deterministic enrichment

semantic-gpu
    host accelerator embedding
    same retrieval stack

quality
    production embedding
    ANN
    Qwen3 reranker CPU
    reserve/protected selection

contextualized
    quality/semantic profile
    + small local LLM indexing-time contextualizer

multimodal
    compatible image embeddings
    first-class figures
```

The Control Plane should show:

- active profile;
- model IDs/revisions;
- device;
- RAM/VRAM capability result;
- fallback state;
- index compatibility;
- reranker status.

---

# 25. Configuration additions

Illustrative configuration:

```yaml
chunking:
  documents:
    strategy: structural_token_aware
    target_tokens: 768
    max_tokens: 900
    min_tokens: 160
    merge_peers: true
    hard_max_bytes: 16384

  pdf:
    strategy: docling_hybrid

enrichment:
  retrieval_text:
    deterministic: true
    local_contextualizer: false

inference_policy:
  default: LOCAL_MODEL_ALLOWED

embedding:
  profile: semantic-cpu
  model:
    family: embeddinggemma2
    revision: "<pinned>"
    dimension: 512
    normalize: true

dense_index:
  backend: auto
  ann_backend: usearch

retrieval:
  dense_candidates: 80
  lexical_candidates: 80
  pre_rerank_pool: 48

  selection:
    primary_top_k: 8
    reserve_top_k: 24
    protect_exact_matches: true
    max_primary_chunks_per_source: 3

  reranker:
    profile: minimal
    timeout_seconds: 8
    max_pair_tokens: 1536

pdf:
  page_batch_size: 32
  boundary_context_pages: 1
  selective_ocr: true

accelerator:
  enabled: auto
  role: embedding_only
  fallback_to_cpu: true
```

Exact values must remain config/evaluation parameters.

---

# 26. OpenSpec implementation strategy

Do not edit accepted behavior directly without a new change.

Create a new OpenSpec change, for example:

```text
openspec/changes/improve-ingestion-retrieval-local-models/
```

Minimum artifacts:

```text
proposal.md
design.md
tasks.md
context-impact.md
```

Recommended affected accepted capabilities:

```text
canonical-knowledge-schema
document-source-adapters
ingestion-pipeline-driver
semantic-structural-chunking
context-enrichment
runtime-store
dense-index
embedding-model
hybrid-retrieval
multi-stage-retrieval
reranker-port
context-assembler
retrieval-benchmark
capability-discovery
one-click-distribution
integration-quality-gates
```

Recommended new capabilities only where the concept is genuinely independent:

```text
rich-document-graph
resumable-document-ingestion
retrieval-candidate-selection
embedding-execution-profile
retrieval-trace
```

Avoid creating a separate spec for every class.

---

# 27. Recommended implementation changes / PR sequence

The sequence below is intentionally decoupled.

Each package should be independently reviewable and testable.

---

## Change Package A — Retrieval correctness and candidate lifecycle

**No heavy new model dependencies. Do this first.**

### A1 — query features and mixed identifier handling

Add:

```text
core/retrieval/query_features.py
```

Modify hybrid retrieval.

### A2 — candidate selection model

Add:

```text
core/retrieval/selection.py
ports/retrieval/selection.py
```

Add runtime-only selection states and trace.

### A3 — reorder pipeline

Modify:

```text
core/retrieval/multi_stage_retrieval.py
```

Direct evidence rerank happens before graph/hierarchy support expansion.

### A4 — Context Assembler reserve escalation

Extend:

```text
core/retrieval/context_assembler.py
```

### A5 — retrieval trace

Extend:

```text
ports/retrieval/multi_stage_retrieval.py
```

### A acceptance

- pure ID fast path preserved;
- mixed ID + text uses hybrid;
- exact candidate never silently lost;
- support nodes are not reranked as direct evidence;
- reserve survives;
- existing tests remain green;
- new tests cover protected/reserve/support semantics.

---

## Change Package B — Tokenizer-aware chunking and semantic retrieval text

### B1 — tokenizer port

Add:

```text
ports/ingest/tokenizer.py
```

### B2 — extend ChunkerContext additively

Retain byte safety limit.

Add token fields.

### B3 — token budget normalizer

Add:

```text
core/ingest/token_budget.py
```

### B4 — retrieval text builder

Add:

```text
ports/ingest/retrieval_text_builder.py
core/ingest/retrieval_text_builder.py
```

### B5 — fix local LLM contextualization path

Ensure approved local-model context actually participates in retrieval text.

### B acceptance

- existing structural chunkers remain;
- chunk IDs include chunking strategy/tokenizer version where necessary;
- same input/strategy produces deterministic chunks;
- oversized chunks respect tokenizer max;
- deterministic profile works without local LLM;
- local contextualizer output is never authoritative metadata.

---

## Change Package C — Production embeddings and vector persistence

### C1 — implement real embedding adapter

Add one real model adapter.

### C2 — embedding profile identity

Add model/revision/dimension/normalization namespace.

### C3 — vector record persistence

Add:

```text
VectorRecordStorePort
SqliteVectorRecordStore
```

### C4 — preserve hashing backend

Hashing remains unit-test/fallback.

### C acceptance

- production adapter produces real semantic vectors;
- model revision is pinned/licensed;
- vectors are reusable across branch switches by content/retrieval-text hash;
- incompatible vector spaces cannot be opened together;
- deleting ANN does not require re-embedding.

---

## Change Package D — ANN backend

### D1 — USearch adapter

Add:

```text
adapters/runtime/usearch_dense_index.py
```

### D2 — backend selection

```text
flat
usearch
auto
```

### D3 — derived index lifecycle

Integrate rebuild with existing runtime/index state.

### D acceptance

- Flat and USearch conform to same port contract;
- ANN file is disposable;
- branch/version/index profile mismatch triggers rebuild;
- recall vs flat baseline is measured.

---

## Change Package E — Rich PDF ingestion

### E1 — canonical rich-document model

Add neutral types.

### E2 — pypdf-style prescan

Cheap hash/page/text-layer detection.

### E3 — Docling adapter

Docling types remain in adapter layer.

### E4 — batched ingestion

Page windows + persistence checkpoints.

### E5 — selective OCR

Native text preferred.

### E6 — tables/figures/assets

First-class source graph.

### E7 — document-specific chunker

Docling HybridChunker behind `ChunkerPort`.

### E acceptance

- 10-page fixture;
- 100-page fixture;
- generated 600-page fixture;
- resume after injected mid-document failure;
- exact page/element provenance;
- tables retain headers;
- figures retain captions/relations;
- no whole-document memory requirement.

---

## Change Package F — Quality reranker

Only after A–E baseline metrics exist.

### F1 — make generic CrossEncoder adapter functional

Do not leave it as a constructor-only placeholder.

### F2 — Qwen3 reranker adapter

Separate adapter/profile.

### F3 — timeouts and batching

Required.

### F4 — fallback

Timeout/error returns to RRF ordering.

### F acceptance

Measure:

- Recall@K;
- MRR/NDCG;
- p50/p95 latency;
- peak RAM;
- startup/model-load time;
- context quality.

Enable Qwen as default only if measured gain justifies resource cost.

---

## Change Package G — Optional host accelerator

Do only after container CPU embedding works.

### G1 — host accelerator service

Suggested separate package:

```text
accelerator/
```

### G2 — health/capability API

### G3 — secure token/bootstrap

### G4 — launcher integration

Use existing one-click distribution/harness concepts.

### G5 — Control Plane status

Expose:

```text
device
model
revision
free memory
active modality
fallback state
```

### G acceptance

- app functions with accelerator absent;
- same embedding profile produces compatible vectors on CPU/GPU;
- accelerator cannot load arbitrary model path;
- failure triggers clean CPU fallback.

---

## Change Package H — Multimodal figures

Optional, later.

Enable only after:

- PDF text ingestion stable;
- figure extraction stable;
- embedding profile stable;
- evaluation corpus includes diagram queries.

Do not make multimodal model loading part of minimal installation.

---

# 28. Evaluation architecture

The existing synthetic benchmark is valuable because it is:

- deterministic;
- fast;
- dependency-light;
- CI-friendly.

Keep it.

Add a second evaluation tier.

---

## 28.1 Tier 1 — deterministic CI benchmark

Existing synthetic corpus.

Purpose:

```text
contract regressions
routing regressions
exact fast-path
selection state invariants
stage invocation
serialization
```

No downloaded models.

---

## 28.2 Tier 2 — local integration evaluation

Tagged optional test suite:

```text
@pytest.mark.local_model
@pytest.mark.pdf
@pytest.mark.slow
```

Use real:

- tokenizer;
- embedding model;
- reranker where configured;
- FTS;
- ANN;
- generated/sanitized PDF fixtures.

Do not make this a mandatory lightweight PR test unless CI runners are provisioned for it.

---

## 28.3 Tier 3 — benchmark/evaluation command

Add command such as:

```text
project-intelligence eval retrieval
```

Inputs:

```text
golden queries
expected evidence
chunking profile
embedding profile
reranker profile
corpus snapshot
```

Outputs:

```text
Recall@5
Recall@10
MRR
NDCG
protected-hit retention
context evidence coverage
average context tokens
p50/p95 latency
peak RAM
embedding throughput
reranker throughput
cache reuse
branch-switch hydration time
```

---

## 28.4 Chunk-size experiment

Do not choose `900` by intuition alone.

Evaluate:

```text
512
768
900
1200
```

on representative:

- German requirements;
- English protocols;
- Ukrainian queries;
- Java source;
- mixed code/business queries;
- tables.

The selected default should be recorded in an ADR/eval report.

---

# 29. Real evaluation corpus design

Do not put proprietary customer material in the public repository.

Create:

```text
evals/corpus/
├── synthetic/
├── generated-pdf/
├── multilingual/
├── java/
├── requirements/
└── golden_queries.yaml
```

Use:

- generated documents;
- permissively licensed samples;
- sanitized project fixtures.

For confidential internal evaluation, support an ignored:

```text
tmp/local/evals/
```

The same evaluator should run against it locally.

---

# 30. Incremental processing rules

For every processed source persist:

```text
source_id
revision_id
parser_version
chunker_strategy_version
tokenizer_id
enrichment_strategy_version
local_contextualizer_revision
retrieval_text_hash
embedding_profile_hash
index_schema_version
```

On refresh:

```text
unchanged revision
    → skip parser

changed source
    → compare element/page hashes where possible

unchanged chunk/retrieval_text
    → reuse embedding

changed retrieval_text
    → re-embed

deleted chunk
    → tombstone/remove from FTS/vector/graph

embedding profile changed
    → rebuild vectors/index namespace

ANN implementation changed only
    → rebuild ANN from stored vector records
```

This distinction is important:

```text
content changed
vs
enrichment changed
vs
embedding model changed
vs
ANN implementation changed
```

They must not all trigger the same expensive rebuild.

---

# 31. Model and dependency licensing

Every optional dependency and model must continue to pass the existing License Gate.

Add exact model revisions to:

```text
distribution/licenses/model-licenses.json
```

and dependency inventory/SBOM.

Model license is independent from runtime/library license.

Do not infer:

```text
sentence-transformers is Apache
therefore every downloaded model is allowed
```

The model itself must be approved.

Recommended optional dependency groups:

```text
documents
semantic-embeddings
ann
reranking
accelerator
multimodal
```

Do not inflate the minimal base installation.

---

# 32. Control Plane integration

Expose new features through current Control Plane rather than configuration-only hidden behavior.

Recommended panels/settings:

```text
Ingestion
├── PDF parser
├── OCR mode
├── page batch size
└── active jobs

Chunking
├── tokenizer
├── target/max tokens
└── chunk profile

Embeddings
├── active model/revision
├── device
├── dimension
├── normalization
└── index compatibility

Retrieval
├── dense/lexical candidates
├── primary/reserve sizes
├── reranker profile
└── debug trace

Accelerator
├── health
├── device
├── memory
└── fallback

Evaluation
└── latest benchmark report
```

Administrative model changes require the existing capability/policy system.

---

# 33. MCP / Agent Skill implications

Do not create many low-level MCP tools for individual retrieval stages.

Keep semantic tools.

The server can internally use the richer pipeline.

Useful additions to existing tool output:

```text
selection state
source/provenance
project version
conflicts
support relationships
retrieval trace ID
```

In debug/admin mode, optionally expose:

```text
project.get_retrieval_trace(trace_id)
```

Do not expose raw internal DB access.

Update the canonical Agent Skill so agents understand:

1. exact identifiers are protected;
2. `retrieve_context` already performs hybrid/reranked retrieval;
3. support context is attached automatically;
4. broad repository scans remain a fallback;
5. reserve evidence can be requested through the server if verification needs more context.

---

# 34. Important corrections to the v2 design before adoption

The v2 design contains several ideas that should **not** be copied literally.

## 34.1 Do not make SQLite the durable project source of truth

Keep v0.8 invariant:

```text
Git canonical knowledge = durable truth
runtime SQLite = operational working state
```

SQLite may persist expensive runtime records, embeddings and ingestion checkpoints, but it is rebuildable/reconcilable from canonical knowledge and sources.

---

## 34.2 Do not replace the current package layout

Do not introduce a second tree such as:

```text
src/project_expert/...
```

The repository already has:

```text
pi_platform/core
pi_platform/ports
pi_platform/adapters
```

Integrate into that structure.

---

## 34.3 Do not make Qwen reranking mandatory

Keep a no-heavy-model profile.

Qwen belongs to the quality profile until benchmarks justify otherwise.

---

## 34.4 Do not move graph expansion before reranking

The current code does that today; the v2 idea to move it after direct-evidence reranking is the better model and should be adopted.

---

## 34.5 Do not store large binary document assets in Git by default

Use CAS and manifests.

Respect:

```text
LOCAL_ONLY
REFERENCE
SNAPSHOT
```

and Git/LFS policy separately.

---

## 34.6 Do not allow Docling types into core contracts

Map them in the adapter.

---

## 34.7 Do not hard-code GPU assumptions

Device selection is runtime capability information.

The one-container CPU path remains valid.

---

## 34.8 Do not automatically LLM-enrich every chunk

Default:

```text
deterministic enrichment
```

Optional:

```text
local contextualizer
```

Run contextualizer only when:

- profile enables it;
- source policy permits it;
- content hash is not cached;
- expected quality gain justifies ingestion cost.

---

# 35. Suggested new files

Likely new files:

```text
pi_platform/core/canonical/document_graph.py

pi_platform/ports/ingest/tokenizer.py
pi_platform/ports/ingest/retrieval_text_builder.py
pi_platform/ports/ingest/ingestion_job_store.py

pi_platform/core/ingest/token_budget.py
pi_platform/core/ingest/retrieval_text_builder.py
pi_platform/core/ingest/local_contextualizer.py

pi_platform/adapters/pdf/prescan.py
pi_platform/adapters/pdf/docling_pdf_adapter.py
pi_platform/adapters/pdf/docling_mapper.py
pi_platform/adapters/pdf/docling_chunker.py
pi_platform/adapters/pdf/ocr_policy.py
pi_platform/adapters/pdf/assets.py

pi_platform/ports/runtime/vector_record_store.py
pi_platform/adapters/runtime/sqlite_vector_record_store.py
pi_platform/adapters/runtime/sqlite_document_graph_store.py
pi_platform/adapters/runtime/sqlite_ingestion_job_store.py
pi_platform/adapters/runtime/usearch_dense_index.py

pi_platform/core/retrieval/query_features.py
pi_platform/core/retrieval/selection.py
pi_platform/core/retrieval/retrieval_trace.py

pi_platform/ports/retrieval/selection.py

pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py
pi_platform/adapters/retrieval/qwen3_embedding_model.py
pi_platform/adapters/retrieval/qwen3_reranker.py
pi_platform/adapters/retrieval/host_embedding_client.py

accelerator/...
```

Possible files to modify:

```text
pi_platform/core/canonical/value_types.py
pi_platform/ports/ingest/source_adapter.py
pi_platform/ports/ingest/chunker.py
pi_platform/ports/ingest/context_enricher.py
pi_platform/adapters/ingest/chunkers.py
pi_platform/adapters/ingest/layered_context_enricher.py
pi_platform/adapters/ingest/local_pipeline_driver.py

pi_platform/ports/retrieval/hybrid_retrieval.py
pi_platform/ports/retrieval/multi_stage_retrieval.py
pi_platform/core/retrieval/hybrid_retrieval.py
pi_platform/core/retrieval/multi_stage_retrieval.py
pi_platform/core/retrieval/context_assembler.py

pi_platform/core/orchestration/capability_discovery.py

pi_platform/mcp/server.py
distribution/skills/project-intelligence/...

pyproject.toml
project-context.yaml examples
distribution/licenses/...
```

Do not add all files in one PR.

---

# 36. Suggested tests

## Canonical / migration

```text
test_document_graph_roundtrip.py
test_chunk_source_anchors.py
test_document_graph_schema_migration.py
```

## PDF

```text
test_pdf_prescan.py
test_pdf_native_text_no_unnecessary_ocr.py
test_pdf_scan_ocr.py
test_pdf_batch_resume.py
test_pdf_table_header_repeat.py
test_pdf_figure_relations.py
test_pdf_600_page_generated.py
```

## Chunking

```text
test_token_budget_split.py
test_token_budget_merge_peers.py
test_code_chunk_ast_boundary.py
test_requirement_chunk_semantics.py
test_chunking_determinism.py
```

## Enrichment

```text
test_retrieval_text_builder.py
test_local_contextualizer_is_inferred.py
test_authoritative_metadata_not_overwritten.py
test_contextualization_cache_key.py
```

## Embedding

```text
test_embedding_profile_identity.py
test_vector_space_mismatch_rejected.py
test_vector_record_reuse.py
test_ann_rebuild_without_reembedding.py
```

## Retrieval

```text
test_pure_identifier_fast_path.py
test_mixed_identifier_hybrid_path.py
test_protected_candidate_survives_rerank.py
test_primary_reserve_selection.py
test_source_diversity_primary_only.py
test_graph_expansion_after_rerank.py
test_support_not_cross_encoded.py
test_reserve_escalation.py
test_retrieval_trace.py
```

## Accelerator

```text
test_accelerator_capabilities.py
test_accelerator_model_allowlist.py
test_accelerator_cpu_fallback.py
test_accelerator_profile_compatibility.py
```

---

# 37. Acceptance criteria for the complete improvement

The improvement is complete only when all of the following are demonstrated.

### Ingestion

- PDF source adapter is functional.
- A generated 600-page PDF is processed in bounded batches.
- Ingestion resumes from a failed batch.
- Native text pages are not blindly OCRed.
- Page/element provenance survives.
- Tables preserve structured data and repeated headers.
- Figures remain first-class referenced assets.

### Chunking

- document chunks respect semantic structure before token budget;
- tokenizer identity is versioned;
- chunk sizes can be evaluated/configured;
- code remains AST/symbol-based.

### Enrichment

- raw evidence remains unchanged;
- retrieval text contains semantic context;
- model-generated context is marked inferred;
- authoritative metadata cannot be generated by the local LLM;
- contextualization cache works across branches.

### Embedding

- at least one real local semantic embedding backend works;
- CPU-only operation works;
- vectors carry model/revision/dimension identity;
- different vector spaces cannot mix;
- unchanged retrieval text reuses embeddings.

### Dense index

- flat backend remains available;
- ANN backend can be enabled;
- ANN can be deleted/rebuilt without model inference.

### Retrieval

- exact-only queries take fast path;
- mixed exact/semantic queries combine both channels;
- RRF precedes reranking;
- direct candidates are reranked before graph support expansion;
- protected candidates survive;
- primary/reserve pools are retained;
- graph/hierarchy items are SUPPORT;
- Context Assembler can escalate from reserve;
- retrieval trace explains why context was chosen.

### Reranker

- system functions with reranker disabled;
- reranker has timeout/fallback;
- quality profile is benchmarked for memory/latency;
- no whole large document is passed to the cross encoder.

### Evaluation

- deterministic synthetic CI tests remain;
- real local model evaluation exists;
- chunk-size sweep exists;
- multilingual queries exist;
- PDF/table/figure cases exist;
- branch/version isolation is tested.

### Portability

- minimal profile remains lightweight;
- CPU-only profile remains supported;
- host accelerator is optional;
- no external DB service is required;
- all new dependencies and model revisions pass License Gate.

---

# 38. Priority recommendation

Implement in this exact order:

```text
P0  OpenSpec change + baseline measurements
P1  Retrieval correctness: protected/reserve/support + stage order
P2  Tokenizer-aware chunking + retrieval-text builder
P3  Real semantic embedding backend + vector record persistence
P4  ANN adapter
P5  Rich PDF document graph + resumable Docling ingestion
P6  Quality reranker profile
P7  Optional host GPU accelerator
P8  Optional local-LLM contextualization
P9  Optional multimodal figures
P10 Control Plane/skill polish + production evaluation gates
```

Why this order:

- P1 fixes correctness independently of models.
- P2 improves input quality before spending compute on embeddings.
- P3/P4 make retrieval genuinely semantic and scalable.
- P5 adds the largest missing source capability.
- P6 is only meaningful after candidate quality can be measured.
- P7 is a performance optimization, not a correctness requirement.
- P8 should be justified by measured retrieval gains.
- P9 has the highest complexity and should not delay text/code/PDF quality.

---

# 39. Definition of “do not regress v0.8”

Every change must preserve:

```text
Git canonical truth
runtime rebuildability
branch awareness
content-addressed reuse
OpenSpec normativity
source provenance
license governance
offline operation
CPU fallback
single-container default
MCP retrieval-first behavior
Control Plane authorization
agent/vendor neutrality
```

If an optimization conflicts with one of these, the optimization must change, not the invariant.

---

# 40. First implementation ticket to execute

The best first engineering ticket is:

## `retrieval-candidate-lifecycle-and-stage-order`

### Deliverables

1. `QueryFeatures`.
2. Mixed identifier + semantic query handling.
3. `SelectionState`.
4. `CandidateTrace`.
5. `PRIMARY / RESERVE / PROTECTED`.
6. Direct-evidence rerank before graph expansion.
7. `SUPPORT` graph/hierarchy items.
8. Context Assembler reserve escalation.
9. Unit tests.
10. Retrieval benchmark regression.

### Why first

It:

- needs no heavy dependency;
- fixes a real semantic weakness in the current code;
- gives a clean contract for the later Qwen reranker;
- makes retrieval explainable;
- reduces the risk that a future model silently destroys useful evidence.

Only after this ticket is accepted should the production embedding/PDF changes begin.

---

# 41. Final target pipeline

```text
                         SOURCE
                           │
          ┌────────────────┼───────────────────┐
          │                │                   │
       Code/Specs       Rich Docs          Local Inbox
          │                │                   │
          │          Prescan / OCR              │
          │                │                   │
          └────────────────┼───────────────────┘
                           ↓
                 Neutral Canonical Model
               + Rich Document Graph
                           │
                           ↓
                Structural Boundaries
                           │
                           ↓
              Token-Budget Normalization
                           │
                           ↓
              Deterministic Enrichment
                           │
                 optional Local LLM
                           │
                           ↓
                    retrieval_text
                           │
             ┌─────────────┼─────────────┐
             ↓             ↓             ↓
          Embedding       FTS/BM25     Metadata
             │             │             │
             ↓             │             │
       Flat / USearch      │             │
             └──────┬──────┘             │
                    ↓                    │
            Exact + Hybrid RRF ◄─────────┘
                    │
                    ↓
             direct candidate pool
                    │
                    ↓
             bounded reranker
                    │
                    ↓
       ┌────────────┼────────────┐
       ↓            ↓            ↓
   PROTECTED     PRIMARY       RESERVE
       └────────────┬────────────┘
                    ↓
          Graph/Hierarchy Expansion
                    ↓
                  SUPPORT
                    ↓
             Context Assembler
           primary + support + reserve
                    ↓
            Project Context Bundle
                    ↓
       MCP / UI / Local LLM / Agent
```

This pipeline is the recommended refinement of the existing v0.8 implementation.

It is not a replacement architecture.

It is the next production-quality layer on top of the architecture that is already present in `dev`.
