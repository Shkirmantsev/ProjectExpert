# Tasks — improve-ingestion-retrieval-local-models

The work is grouped into **eight Change Packages (A–H)** plus
a **P0 baseline**. Each package is independently reviewable and
testable. Within each package tasks are ordered to keep tests
green at every step.

Per-package acceptance criteria and required tests are derived
from `ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md`
(plan) sections cited in each block. The verification gate at
the end of every package is `python harness.py check` and the
focused pytest subset named in the block.

Cross-cutting gates (run after every package):

- [x] `python harness.py openspec-check` — OpenSpec schema
      compliance, naming, link integrity.
- [x] `python harness.py check` — full gate (lint, type,
      unit, focused integration, Wiki validation, manifest
      integrity, security).
- [x] Wiki updates from `context-impact.md` committed
      alongside the code.
- [x] No accepted requirement body modified.

---

## P0 — Baseline measurements and OpenSpec scaffolding

- [x] 1. Record the current Tier 1 deterministic benchmark
      numbers (Recall@5, Recall@10, MRR, NDCG, protected-hit
      retention, context coverage, average context tokens,
      p50/p95 latency, peak RAM) as
      `evals/baselines/pre_change.json`. Add the harness
      command to `Makefile` (`make eval-baseline`) and a
      `tests/test_evaluation_baseline.py` that asserts the
      recorded numbers are non-empty and the focused subset
      passes.
- [x] 2. Add `evals/quality_gates.yaml` with the
      integration-quality-gate thresholds named in plan
      §28.3 and §37; reference them from
      `tests/test_evaluation_quality_gates.py`.
- [x] 3. Create the change folder
      `openspec/changes/improve-ingestion-retrieval-local-models/`
      with the `proposal.md`, `design.md`, `tasks.md`,
      `context-impact.md` and the `specs/` tree (this
      change is the first package that uses them; the
      scaffolding itself is part of P0).
- [x] 4. Add `pi_platform/ports/ingest/ingestion_job_store.py`
      and `pi_platform/ports/ingest/tokenizer.py` as
      interface-only ports (no implementation) so the
      PDF, token, and chunking Change Packages can depend
      on stable contracts from day one. Add minimal
      `tests/test_ingestion_job_store_port.py` and
      `tests/test_tokenizer_port.py` that import the
      abstract class and assert `NotImplementedError`
      from the abstract methods.
- [x] 5. Document the P0 baseline in the Wiki as
      `kb://project/retrieval-evaluation-corpus`
      (link target of plan §29) and add a small section
      to `kb://architecture/system-overview` titled
      "v0.8 refinement baseline" that links to
      `evals/baselines/pre_change.json`.

P0 acceptance:

- The change folder exists, is OpenSpec-schema compliant,
  and the harness gate is green on the unchanged codebase.
- `evals/baselines/pre_change.json` is recorded and
  reloaded by `make eval-baseline`.
- The two new ports exist as interface-only modules and
  the import tests pass.

---

## Change Package A — Retrieval correctness and candidate lifecycle

> No heavy new model dependencies. Do this first.
> Plan: §4.1, §4.2, §5, §5.1–§5.4, §6, §7.

### A1 — Query features and mixed-identifier handling

- [x] 1. Add
      `pi_platform/core/retrieval/query_features.py`
      with the `QueryFeatures` dataclass
      (`identifiers`, `quoted_phrases`, `has_free_text`,
      `target_document`, `target_symbol`, `filters`).
- [x] 2. Extend
      `pi_platform/adapters/retrieval/identifier_query_detector.py`
      to surface `has_free_text` and `quoted_phrases` and
      return a `QueryFeatures` value object.
- [x] 3. Modify
      `pi_platform/ports/retrieval/hybrid_retrieval.py`
      and
      `pi_platform/core/retrieval/hybrid_retrieval.py`:
      pure-identifier queries still take the exact-only
      fast path; mixed queries keep the exact candidate
      marked `PROTECTED` and execute dense + sparse
      retrieval + RRF.
- [x] 4. Add focused tests
      `tests/test_query_features.py`,
      `tests/test_pure_identifier_fast_path.py`,
      `tests/test_mixed_identifier_hybrid_path.py` with
      the four plan §4.1 cases
      (`"ILO-5193"`,
      `"Where is ILO-5193 implemented?"`,
      `"Explain PSB_FINISH_PACK timeout behavior"`,
      `"GEN_3.0.03 FinishPack"`).

### A2 — Candidate selection model

- [x] 1. Add
      `pi_platform/ports/retrieval/selection.py`
      with the `SelectionPort` interface and the
      `SelectionState` enum (`PRIMARY`, `RESERVE`,
      `PROTECTED`, `SUPPORT`, `DROPPED_DUPLICATE`).
- [x] 2. Add
      `pi_platform/core/retrieval/selection.py`
      with `CandidateTrace` (chunk_id, dense_rank,
      sparse_rank, exact_match, rrf_rank, rrf_score,
      rerank_rank, rerank_score, selection_state,
      protected_reason, duplicate_of,
      source_document_id, trace_reasons) and a
      `select(candidates, query_features, budget)`
      implementation that honours the plan §5.2 / §5.3 /
      §5.4 rules (protected reasons, reserve pool,
      source diversity soft limit
      `max_primary_chunks_per_source: 3`).
- [x] 3. Add `tests/test_selection.py` and
      `tests/test_candidate_trace.py` covering
      protected-hit survival, reserve retention,
      near-duplicate detection by normalised content
      hash, and source diversity (only on `PRIMARY`,
      not on `RESERVE`, not when the user explicitly
      targets a specific document).

### A3 — Reorder multi-stage retrieval pipeline

- [x] 1. Modify
      `pi_platform/ports/retrieval/multi_stage_retrieval.py`
      and
      `pi_platform/core/retrieval/multi_stage_retrieval.py`
      to the new stage order from plan §4.2:
      `query_analysis → exact/dense/sparse →
       metadata/version/security → RRF → pre-rerank
       pool → rerank DIRECT candidates → selection
       (PRIMARY/RESERVE/PROTECTED) → graph expansion
       from selected seeds → hierarchy/adjacent/
       figure/table expansion → mark SUPPORT →
       Context Assembly → reserve escalation`.
- [x] 2. Introduce a `DirectCandidate` /
      `SupportEvidence` split so the reranker never
      sees support nodes. `RetrievalHit.source`
      stays `dense|sparse|exact|hybrid`; support
      items are added by `ContextAssembler` with
      their own `evidence_kind`.
- [x] 3. Add `tests/test_multi_stage_order.py` and
      `tests/test_graph_expansion_after_rerank.py`
      and `tests/test_support_not_cross_encoded.py`
      that assert the new order, the support
      separation, and the reranker not being called
      on support nodes.

### A4 — Context Assembler reserve escalation

- [x] 1. Modify
      `pi_platform/core/retrieval/context_assembler.py`
      to be aware of `PRIMARY | PROTECTED | SUPPORT |
      RESERVE` and assemble in the plan §6 order:
      protected direct evidence → authoritative
      PRIMARY → other PRIMARY → mandatory SUPPORT →
      conflict-support evidence → reserve escalation
      for uncovered subtopics → optional additional
      SUPPORT → stop at context budget.
- [x] 2. Add near-duplicate collapse by normalised
      content hash / similarity while preserving
      links to the collapsed equivalents (do not
      discard duplicate provenance).
- [x] 3. Add `tests/test_context_assembler_selection.py`
      and `tests/test_reserve_escalation.py` and
      `tests/test_source_diversity_primary_only.py`
      and `tests/test_protected_candidate_survives_rerank.py`
      and `tests/test_primary_reserve_selection.py`.

### A5 — Retrieval trace

- [x] 1. Add
      `pi_platform/core/retrieval/retrieval_trace.py`
      with the `RetrievalTrace` typed value object
      (query_features, active_filters,
      exact_candidates, dense_candidates,
      sparse_candidates, fusion, reranker,
      selection, graph_expansion,
      hierarchy_expansion, budget_decisions, timings).
- [x] 2. Extend `MultiStageRetrievalPort` and
      `MultiStageRetrievalCore` to populate the
      trace; serialise to JSON; redact secret
      metadata via the existing
      `pi_platform/security/secret_provider.py`.
- [x] 3. Make the trace optional in the normal
      retrieval API response (controlled by
      `RetrievalConfig.include_trace`); always
      available in debug/evaluation mode; surface
      in Control Plane diagnostics
      (`pi_platform/control/diagnostics/...`).
- [x] 4. Add `tests/test_retrieval_trace.py`
      covering round-trip serialisation,
      redaction, debug-mode presence, and the
      Control Plane hook.

### A acceptance

- [x] Tier 1 deterministic CI benchmark remains
      green.
- [x] Pure-ID fast path preserved.
- [x] Mixed-ID + text queries use hybrid retrieval
      and retain the exact hit.
- [x] Exact candidate never silently lost.
- [x] Support nodes are not reranked as direct
      evidence.
- [x] Reserve pool survives selection.
- [x] Retrieval trace explains why context was
      chosen.
- [x] All new tests listed above pass.
- [x] `kb://architecture/retrieval-candidate-selection`,
      `kb://modules/retrieval-trace`,
      `kb://interfaces/selection` Wiki nodes
      authored.
- [x] New ADRs `0025-rerank-direct-before-graph-expansion.md`
      committed.

---

## Change Package B — Tokenizer-aware chunking and semantic retrieval text

> Plan: §3.3, §3.4, §8, §8.1, §9, §10, §10.1, §11,
> §11.1, §11.2.

### B1 — Tokenizer port

- [x] 1. Add
      `pi_platform/ports/ingest/tokenizer.py`
      with `TokenizerPort`
      (`count(text) -> int`,
      `truncate(text, max_tokens) -> str`,
      `identity() -> str`).
- [x] 2. Add implementations:
      `HashingTokenizer` (no external deps),
      `WhitespaceTokenizer` (test fallback), and
      the first real adapter
      `EmbeddingGemma2Tokenizer` under
      `pi_platform/adapters/ingest/embeddinggemma2_tokenizer.py`
      behind the `semantic-embeddings` optional
      dependency group.
- [x] 3. Add `tests/test_tokenizer_port.py` for
      each implementation, including
      round-trip / determinism / truncation
      behaviour.

### B2 — Extend ChunkerContext additively

- [x] 1. Extend
      `pi_platform/ports/ingest/chunker.py`:
      `ChunkerContext` gains `target_tokens`,
      `max_tokens`, `min_tokens`, `tokenizer_id`,
      `merge_peers`. `max_chunk_bytes` is preserved
      as a hard safety limit.
- [x] 2. Update every existing structural chunker
      in
      `pi_platform/adapters/ingest/chunkers.py`
      to read the new fields (defaulting to the
      existing byte-based behaviour when unset) so
      no accepted requirement body changes.
- [x] 3. Add `tests/test_chunker_context_additive.py`.

### B3 — Token budget normalizer

- [x] 1. Add
      `pi_platform/core/ingest/token_budget.py`
      with `TokenBudgetNormalizer` that composes
      after a `SemanticBoundaryStrategy`: split
      oversized candidates at token boundaries;
      merge compatible peers when below
      `min_tokens`; never violate
      `max_chunk_bytes`.
- [x] 2. Wrap each existing structural chunker
      with the normalizer (composition in
      `local_pipeline_driver.py`); no chunker is
      replaced.
- [x] 3. Add
      `tests/test_token_budget_split.py`,
      `tests/test_token_budget_merge_peers.py`,
      `tests/test_chunking_determinism.py`.

### B4 — Retrieval text builder

- [x] 1. Add
      `pi_platform/ports/ingest/retrieval_text_builder.py`
      and
      `pi_platform/core/ingest/retrieval_text_builder.py`
      with
      `DeterministicRetrievalTextBuilder` (default)
      and the
      `RetrievalText` value object
      (`text`, `strategy_version`,
      `deterministic_parts`, `inferred_parts`,
      `content_hash`).
- [x] 2. Define one canonical mapping:
      `retrieval_text = context_prefix + "\n\n" +
      raw_text`; reconcile `Chunk.contextualText`
      to a single meaning (either persists the
      builder result or is deprecated in favor of
      `retrieval_text`).
- [x] 3. Add
      `tests/test_retrieval_text_builder.py`
      covering: deterministic content; excluded
      fields (absolute path, SHA, Git commit,
      timestamp, bbox, security label, processing
      version); semantic inputs (document title,
      heading path, requirement ID, Java
      signature, caption, protocol name); hash
      stability.

### B5 — Fix local-LLM contextualization path

- [x] 1. Add
      `pi_platform/core/ingest/local_contextualizer.py`
      with `LocalContextualizer` — a narrow
      application service over `LocalLLMPort`
      (ADR-0027). Its output is restricted to:
      context summary, candidate entities,
      candidate relations, query aliases /
      glossary hints. It is forbidden from
      producing requirement ID, protocol version,
      validFrom/validTo, security class, Git
      revision, source ID, license.
- [x] 2. Add an `InferencePolicy` value object
      (`NO_MODEL | LOCAL_MODEL_ALLOWED |
      EXTERNAL_MODEL_ALLOWED`), separate from
      `SourcePersistencePolicy`; wire it through
      the central Policy Engine
      (`pi_platform/control/policy_engine.py`).
- [x] 3. Add a `ContextualizationCache` keyed by
      `sha256(chunk_content_hash ||
      contextualizer_model_revision ||
      prompt_version ||
      enrichment_strategy_version)`.
- [x] 4. Modify
      `pi_platform/adapters/ingest/layered_context_enricher.py`
      to invoke the builder; the embedding input
      actually reflects the LLM suggestion when
      the contextualizer is enabled and the
      inference policy allows it.
- [x] 5. Add
      `tests/test_local_contextualizer_is_inferred.py`,
      `tests/test_authoritative_metadata_not_overwritten.py`,
      `tests/test_contextualization_cache_key.py`.

### B acceptance

- [x] All existing structural chunkers remain
      (Markdown, requirements, protocols, tables,
      architecture, Java AST).
- [x] Chunk IDs include `chunker_strategy_version`
      and `tokenizer_id` where necessary.
- [x] Same input + same strategy + same tokenizer
      produce deterministic chunks.
- [x] Oversized chunks respect `max_tokens`; the
      hard `max_chunk_bytes` safety limit is
      preserved.
- [x] Deterministic profile works without a local
      LLM; opt-in local contextualizer is
      applied only when allowed.
- [x] Local contextualizer output is never
      authoritative metadata.
- [x] Wiki nodes `kb://interfaces/tokenizer`,
      `kb://interfaces/retrieval-text-builder`
      authored; ADRs
      `0027-inference-policy-separate-from-source-policy.md`
      committed.

---

## Change Package C — Production embeddings and vector persistence

> Plan: §3.5, §12, §13, §14, §15, §16.

### C1 — Implement real semantic embedding adapter

- [x] 1. Add
      `pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py`
      as the first real local semantic adapter,
      behind the `semantic-embeddings` optional
      dependency group. The adapter implements the
      existing `EmbeddingModelPort`; on
      `embed()` / `embed_batch()` it returns real
      vectors. It honours the `EmbeddingProfile`
      descriptor (provider, model_id,
      model_revision, modality, output_dimension,
      normalization, instruction_profile,
      tokenizer_id, strategy_version).
- [x] 2. Add
      `pi_platform/adapters/retrieval/qwen3_embedding_model.py`
      as a separate profile. Its vectors are
      persisted in a separate
      `embedding_profile_hash` namespace; never
      mixed with EmbeddingGemma 2.
- [x] 3. Keep `HashingEmbeddingModel` for unit
      tests, zero-dependency boot, and
      deterministic smoke tests.
- [x] 4. Add
      `tests/test_embeddinggemma2_embedding_model.py`
      (Tier 2, `@pytest.mark.local_model`) and a
      Tier 1 import-and-contract test.

### C2 — Embedding profile identity

- [x] 1. Add `EmbeddingProfile` descriptor and
      identity computation
      `sha256(canonical(EmbeddingProfile))`.
- [x] 2. Modify the dense index to refuse to
      open an ANN namespace whose
      `embedding_profile_hash` does not match the
      active profile; raise a clear, redacted
      error.
- [x] 3. Add
      `tests/test_embedding_profile_identity.py`
      and
      `tests/test_vector_space_mismatch_rejected.py`.

### C3 — Vector record persistence

- [x] 1. Add
      `pi_platform/ports/runtime/vector_record_store.py`
      and
      `pi_platform/adapters/runtime/sqlite_vector_record_store.py`
      with the `VectorRecord` shape
      (`chunk_id`, `content_hash`,
      `embedding_profile_hash`, `model_revision`,
      `dimension`, `normalization`,
      `vector_payload` (BLOB),
      `created_from_retrieval_text_hash`).
- [x] 2. Migrate `runtime.db` to add the
      `embeddings` table; do not rewrite
      existing rows.
- [x] 3. Add
      `tests/test_vector_record_reuse.py`
      (same content / same retrieval text /
      same profile reuses the record) and
      `tests/test_ann_rebuild_without_reembedding.py`.

### C4 — Preserve hashing backend

- [x] 1. Confirm
      `HashingEmbeddingModel` is still wired
      by default in the `minimal` profile; no
      accepted requirement body changes.
- [x] 2. Add a smoke test
      `tests/test_hashing_embedding_fallback.py`
      asserting it loads without optional
      dependencies.

### C acceptance

- [x] Production adapter produces real semantic
      vectors.
- [x] Model revision is pinned and license-
      recorded (`distribution/licenses/model-licenses.json`).
- [x] Vectors are reusable across branch
      switches by content / retrieval-text
      hash.
- [x] Incompatible vector spaces cannot be
      opened together.
- [x] Deleting the ANN does not require re-
      embedding.
- [x] Wiki node
      `kb://architecture/embedding-profile-identity`
      authored; ADR
      `0026-embedding-profile-identity-and-vector-namespace.md`
      committed.

---

## Change Package D — ANN backend

> Plan: §3.6, §17, §17.1.

### D1 — USearch adapter

- [x] 1. Add
      `pi_platform/adapters/runtime/usearch_dense_index.py`
      implementing the existing `DenseIndexPort`
      with the USearch HNSW index type.
- [x] 2. Persist the index under
      `.project-intelligence-cache/indexes/<embedding_profile_hash>/`;
      the directory is git-ignored.
- [x] 3. Record index metadata:
      `embedding_profile_hash`,
      `index_schema_version`,
      `source_generation`, `vector_count`.
- [x] 4. If any compatibility key changes,
      rebuild the ANN index from
      `VectorRecordStorePort` without re-
      embedding.

### D2 — Backend selection

- [x] 1. Add
      `dense_index.backend ∈ {auto, flat,
      usearch}` driven by configuration. `auto`
      may choose based on benchmarked corpus
      size and recall constraints; the
      architectural invariant is that the
      choice is data-driven, not hard-coded.
- [x] 2. Add
      `tests/test_dense_index_backend_selection.py`
      and
      `tests/test_usearch_conforms_to_port.py`
      (Flat and USearch must both pass the
      same `DenseIndexPort` contract tests).

### D3 — Derived index lifecycle

- [x] 1. Integrate rebuild with the existing
      runtime / index state machine; the new
      `index_state` SQLite table records the
      current ANN namespace, profile, and
      version.
- [x] 2. Add
      `tests/test_ann_branch_mismatch_rebuild.py`.

### D acceptance

- [x] Flat and USearch conform to the same
      `DenseIndexPort` contract.
- [x] ANN file is disposable.
- [x] Branch / version / index profile mismatch
      triggers a rebuild.
- [x] Recall vs flat baseline is measured
      (`scripts/recall_vs_flat.py`).
- [x] Wiki node
      `kb://interfaces/dense-index` updated;
      ADR
      `0028-usearch-as-default-ann-backend.md`
      committed.

---

## Change Package E — Rich PDF document graph + resumable Docling ingestion

> Plan: §3.1, §3.2, §19, §19.1, §20, §21, §21.1–
> §21.6, §22.

### E1 — Canonical rich-document model

- [x] 1. Add
      `pi_platform/core/canonical/document_graph.py`
      with the additive types
      `DocumentRevision`, `Page`,
      `DocumentElement` (discriminated union of
      `Heading`, `Paragraph`, `List`, `Table`,
      `Figure`, `Formula`), `ElementKind`,
      `SourceAnchor`, `AssetRef`, `TableGrid`,
      `IngestionCheckpoint`.
- [x] 2. Extend `Chunk` additively with
      `anchors: Sequence[SourceAnchor]`. Bump
      `KNOWLEDGE_SCHEMA_VERSION` `1 → 2`.
- [x] 3. Migration script under
      `pi_platform/adapters/runtime/migrations/`
      adds the new tables and columns; existing
      rows are not rewritten.
- [x] 4. Add
      `tests/test_document_graph_roundtrip.py`,
      `tests/test_chunk_source_anchors.py`,
      `tests/test_document_graph_schema_migration.py`.

### E2 — pypdf-style prescan

- [x] 1. Add
      `pi_platform/adapters/pdf/prescan.py`:
      hash file, read page count, read
      metadata, sample the native text layer,
      resolve `revision_id`, check
      `IngestionJobStorePort` for `COMPLETED`
      with the same revision + strategy. If so,
      skip the expensive parse.
- [x] 2. Add `tests/test_pdf_prescan.py`.

### E3 — Docling adapter

- [x] 1. Add
      `pi_platform/adapters/pdf/docling_pdf_adapter.py`
      and
      `pi_platform/adapters/pdf/docling_mapper.py`.
      Docling types must not leak past the
      adapter; the core knows only the
      ProjectExpert-neutral types from E1.
- [x] 2. Replace
      `PLANNED_ADAPTERS.pdfplumber` with the
      Docling adapter in
      `pi_platform/ports/ingest/source_adapter.py`.

### E4 — Batched ingestion

- [x] 1. Add
      `pi_platform/adapters/runtime/sqlite_ingestion_job_store.py`
      implementing `IngestionJobStorePort` with
      states `PENDING | RUNNING | PAUSED |
      FAILED_RETRYABLE | FAILED_PERMANENT |
      COMPLETED | CANCELLED`.
- [x] 2. Add
      `pi_platform/adapters/runtime/sqlite_document_graph_store.py`
      implementing `DocumentGraphStorePort` with
      `document_revisions`, `pages`,
      `document_elements`, `assets`,
      `table_cells`, `table_payloads`,
      `chunk_anchors` tables.
- [x] 3. Add
      `pi_platform/ports/runtime/document_graph_store.py`
      port and
      `pi_platform/ports/ingest/ingestion_job_store.py`
      port (the latter is a P0 stub upgraded
      here to the SQLite implementation).
- [x] 4. Stage B batches parse into
      `page_batch_size` page windows with
      `boundary_context_pages` neighbour pages
      as context; each batch commits
      transactionally; a crash at page 417 does
      not invalidate completed batches.
- [x] 5. Add
      `tests/test_pdf_batch_resume.py`
      asserting resume after an injected
      mid-document failure.

### E5 — Selective OCR

- [x] 1. Add
      `pi_platform/adapters/pdf/ocr_policy.py`
      with the policy: usable native text →
      native text + layout (OCR only image /
      bitmap regions when needed); no usable
      native text → full-page OCR.
- [x] 2. Add `OcrEnginePort` and the
      `TesseractOcrEngine` (default) and
      `PaddleOcrEngine` (optional fallback)
      adapters. Both are subject to the License
      Gate and pinned in
      `distribution/licenses/model-licenses.json`.
- [x] 3. Add
      `tests/test_pdf_native_text_no_unnecessary_ocr.py`
      and `tests/test_pdf_scan_ocr.py`.

### E6 — Tables / figures / assets

- [x] 1. Tables: store three views
      (structured cells/rows/columns as
      canonical, text/Markdown serialisation as
      retrieval, source provenance / caption /
      page geometry). When split, repeat the
      header. The canonical structure is the
      grid, not the Markdown serialisation.
- [x] 2. Figures: first-class `AssetRef`
      records with `page`, `bbox`, `caption`,
      `OCR_text` (if present), nearby
      explanatory elements, and graph relations
      `MENTIONS`, `CAPTIONED_BY`, `ON_PAGE`,
      `IN_SECTION`. Image bytes go to local CAS
      by default.
- [x] 3. Add `tests/test_pdf_table_header_repeat.py`
      and `tests/test_pdf_figure_relations.py`.

### E7 — Document-specific chunker

- [x] 1. Add
      `pi_platform/adapters/pdf/docling_chunker.py`
      and
      `pi_platform/adapters/ingest/docling_hybrid_chunker.py`
      using Docling's `HybridChunker` only where
      a `DoclingDocument` exists. Both implement
      the existing `ChunkerPort` so the pipeline
      driver does not need a special-case path.
- [x] 2. Chunk sizes `512 / 768 / 900 / 1200`
      are configurable; `900` is only an
      initial candidate and must be benchmarked
      (Change Package J).

### E acceptance

- [x] 10-page, 100-page, and generated 600-page
      PDF fixtures pass.
- [x] Resume after injected mid-document
      failure.
- [x] Exact page / element provenance survives.
- [x] Tables retain headers.
- [x] Figures retain captions and relations.
- [x] No whole-document memory requirement.
- [x] Wiki node
      `kb://architecture/rich-document-graph`
      authored; ADR
      `0024-rich-document-graph-as-additive-submodel.md`
      committed.

---

## Change Package F — Quality reranker

> Only after A–E baseline metrics exist.
> Plan: §18, §18.1, §18.2.

### F1 — Make generic CrossEncoder adapter functional

- [x] 1. Implement
      `CrossEncoderRerankerAdapter` against a
      SentenceTransformers `CrossEncoder` (e.g.
      a compact multilingual model). No longer a
      constructor-only placeholder.
- [x] 2. Add `tests/test_cross_encoder_reranker.py`
      (Tier 2,
      `@pytest.mark.local_model`).

### F2 — Qwen3 reranker adapter

- [x] 1. Add
      `pi_platform/adapters/retrieval/qwen3_reranker.py`
      with its own prompt template, truncation,
      and timeouts; bound to the `quality`
      profile, not the default.

### F3 — Timeouts and batching

- [x] 1. Add bounded timeouts, batch sizes, and
      concurrency for both adapters; a failure
      falls back to the BM25-light RRF ordering
      of the pre-rerank direct candidate pool.
- [x] 2. Build a separate `rerank_text` from
      `document_title`, `heading_path`,
      `raw_chunk`, `caption`, `class/method
      context`; exclude hashes, bbox,
      timestamps, Git SHA, unrelated metadata.
      Bounded token budget
      (`max_pair_tokens`, default 1536). Inferred
      enrichment is trimmed before raw evidence.

### F4 — Fallback

- [x] 1. Timeout / error returns to RRF
      ordering; surface the fallback in the
      retrieval trace.
- [x] 2. Add
      `tests/test_reranker_timeout_fallback.py`.

### F acceptance

- [x] Measure Recall@K, MRR/NDCG, p50/p95
      latency, peak RAM, startup / model-load
      time, context quality (plan §18).
- [x] Enable Qwen as default only if the
      measured gain justifies the resource cost
      (plan §18.1). Keep the `minimal` profile
      byte-identical for the synthetic Tier 1
      benchmark.

---

## Change Package G — Optional host accelerator

> Do only after container CPU embedding works.
> Plan: §23, §23.1, §23.2, §24.

### G1 — Host accelerator service

- [x] 1. Add a separate optional package
      `accelerator/` (outside the default
      container) with an approved model
      registry, GPU backend, and a local HTTP
      API. Minimal API:
      `GET /health`, `GET /v1/capabilities`,
      `POST /v1/embeddings`.

### G2 — Health / capability API

- [x] 1. Implement the three endpoints; the
      model registry is allow-listed; pinned
      model revisions only.
- [x] 2. Add
      `tests/test_accelerator_capabilities.py`
      and
      `tests/test_accelerator_model_allowlist.py`.

### G3 — Secure token / bootstrap

- [x] 1. Add an ephemeral bearer token stored
      outside Git; local/private bind; firewall
      requirement if a wide bind is unavoidable;
      request size limit; timeout; concurrency
      limit; audit health / model identity but
      never payload contents by default.

### G4 — Launcher integration

- [x] 1. Use existing one-click distribution
      / harness concepts; do not reinvent
      launchers.

### G5 — Control Plane status

- [x] 1. Expose `device`, `model`, `revision`,
      `free memory`, `active modality`,
      `fallback state` in Control Plane
      diagnostics.
- [x] 2. Add
      `tests/test_accelerator_cpu_fallback.py`
      and
      `tests/test_accelerator_profile_compatibility.py`.

### G acceptance

- [x] The application functions with the
      accelerator absent.
- [x] The same `EmbeddingProfile` produces
      compatible vectors on CPU and GPU.
- [x] The accelerator cannot load an
      arbitrary model path.
- [x] Failure triggers a clean CPU fallback.

---

## Change Package H — Multimodal figures

> Optional, later. Enable only after PDF text
> ingestion is stable, figure extraction is
> stable, the embedding profile is stable, and
> the evaluation corpus includes diagram
> queries.
> Plan: §16, §25 (multimodal profile).

- [x] 1. Add a `FigureEmbeddingModel` adapter
      behind the `multimodal` profile (not part
      of the minimal installation).
- [x] 2. Add `multimodal` profile to
      `Makefile` / `harness.py` and the
      `multimodal.figures` feature flag (off
      by default).
- [x] 3. Add Tier 2 PDF figure queries to
      `evals/corpus/golden_queries.yaml`.
- [x] 4. Update the agent skill to mention
      first-class figure retrieval.

---

## Change Package I — Control Plane / MCP / distribution polish

> Plan: §32, §33.

- [x] 1. Extend Control Plane diagnostics
      with the panels in plan §32
      (`Ingestion`, `Chunking`, `Embeddings`,
      `Retrieval`, `Accelerator`, `Evaluation`).
- [x] 2. Update the MCP `retrieve_context`
      tool output to include
      `selection_state`, `source/provenance`,
      `project version`, `conflicts`,
      `support_relationships`, `retrieval_trace_id`.
      In debug / admin mode, add
      `project.get_retrieval_trace(trace_id)`.
- [x] 3. Update
      `distribution/skills/project-intelligence/...`
      agent skill: protected exact candidates,
      reserve escalation, support context
      automatically attached, broad repository
      scans remain a fallback, trace tool usage.
- [x] 4. Add `tests/test_mcp_retrieval_output.py`
      and `tests/test_mcp_trace_tool.py`.

---

## Change Package J — Evaluation tiers and chunk-size sweep

> Plan: §28, §28.1, §28.2, §28.3, §28.4, §29,
> §30.

- [x] 1. Keep Tier 1 deterministic CI
      benchmark as the regression gate.
- [x] 2. Add Tier 2 local-model integration
      tier (real tokenizer, real embedding
      model, real ANN, real reranker where
      configured) with the
      `@pytest.mark.local_model`,
      `@pytest.mark.pdf`, `@pytest.mark.slow`
      markers.
- [x] 3. Add Tier 3:
      `project-intelligence eval retrieval`
      with `evals/corpus/{synthetic,generated-pdf,multilingual,java,requirements}/`
      and `evals/corpus/golden_queries.yaml`.
      Outputs the metrics in plan §28.3
      (Recall@5/10, MRR, NDCG, protected-hit
      retention, context coverage, average
      context tokens, p50/p95 latency, peak
      RAM, embedding throughput, reranker
      throughput, cache reuse, branch-switch
      hydration time).
- [x] 4. Add a chunk-size sweep over
      `512 / 768 / 900 / 1200` token budgets on
      the multilingual, requirements, English
      protocol, Java, mixed code/business, and
      tables sub-corpora. The selected default
      is recorded in
      `evals/reports/chunk_size_sweep.md` and
      cross-referenced from the embedding ADR.
- [x] 5. Add Tier 2 fixtures
      (10-page, 100-page, generated 600-page
      PDF) under
      `evals/corpus/generated-pdf/` with
      sanitised content; allow
      `tmp/local/evals/` for confidential
      corpora.
- [x] 6. Add
      `tests/test_evaluation_baseline.py`,
      `tests/test_evaluation_quality_gates.py`,
      `tests/test_chunk_size_sweep.py`.

---

## Final verification

- [x] 1. Update `.ai/wiki/INDEX.md` so the new
      and updated nodes are discoverable.
- [x] 2. Refresh the local context index
      (`python -m scripts.project_mcp kb_refresh`
      or the harness equivalent) and confirm
      `kb_search` / `kb_get` return the new
      nodes.
- [x] 3. Run `python harness.py openspec-check`
      and resolve every report.
- [x] 4. Run `python harness.py check` and
      resolve every report. Confirm:
      - Tier 1 deterministic CI benchmark is
        green;
      - Tier 2 local-model tier passes
        (`@pytest.mark.local_model`) on the
        developer's local environment;
      - Tier 3 retrieval-evaluation command
        produces a report that is recorded
        alongside `evals/baselines/pre_change.json`;
      - The integration quality gates
        (plan §28.3, §37) pass.
- [x] 5. Confirm the v0.8 invariant probe
      (`kb://invariants/v0.8` /
      `kb://invariants/v0.8-ingestion-retrieval`)
      is green: Git canonical truth, runtime
      rebuildability, branch awareness,
      content-addressed reuse, OpenSpec
      normativity, source provenance, license
      governance, offline operation, CPU
      fallback, single-container default, MCP
      retrieval-first behavior, Control Plane
      authorization, agent/vendor neutrality.
- [x] 6. Refresh `ARTIFACT_MANIFEST.sha256`
      after the implementation work that lands
      with this change.
- [x] 7. Verify OpenSpec scenarios for every
      new and modified requirement body
      (proposal, specs, design, context-impact,
      tasks) and archive the change per the
      installed OpenSpec workflow.
