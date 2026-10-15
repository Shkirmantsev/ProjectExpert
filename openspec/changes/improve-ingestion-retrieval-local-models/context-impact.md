# Context impact — improve-ingestion-retrieval-local-models

This file records the Wiki, ADR, manifest, SBOM, License Gate,
Control Plane, MCP, distribution, and harness impact that
accompanies implementation of this OpenSpec change. The
implementation work is described in `tasks.md`; the architectural
intent is in `proposal.md` and `design.md`.

## Knowledge to create

Wiki nodes to author during the corresponding Change Package
(reference = `tasks.md` task block, plan section in
`ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md`):

- `kb://architecture/rich-document-graph` — Task E1, plan §3.2,
  §19. Explains the additive submodel
  (`DocumentRevision`, `Page`, `DocumentElement`, `SourceAnchor`,
  `AssetRef`, `TableGrid`, `IngestionCheckpoint`) and the
  projection into the existing `Document` / `Section` / `Chunk`
  generic model.
- `kb://architecture/retrieval-candidate-selection` — Task A2,
  plan §5. Explains `SelectionState`, `CandidateTrace`, the
  `PRIMARY / RESERVE / PROTECTED / SUPPORT / DROPPED_DUPLICATE`
  contract, and why the trace is runtime state, not canonical
  knowledge.
- `kb://architecture/embedding-profile-identity` — Task C2,
  plan §13. Explains `EmbeddingProfile` descriptor, the
  SHA-256 compatibility key, the namespace separation between
  `EmbeddingGemma 2`, `Qwen3-Embedding-0.6B`, and
  `HashingEmbeddingModel` vectors, and the rebuild semantics
  (content change vs enrichment change vs embedding model change
  vs ANN implementation change).
- `kb://modules/retrieval-trace` — Task A5, plan §7. Explains
  the `RetrievalTrace` typed value object, the redaction
  contract, the optionality in normal API responses vs the
  always-available debug/evaluation mode, and the Control Plane
  diagnostics surface.
- `kb://modules/host-embedding-accelerator` — Task G1, plan §23.
  Explains the optional host-side HTTP service, the
  allow-listed model registry, the pinned revisions, the
  ephemeral bearer token, the local/private bind, and the
  CPU fallback contract.
- `kb://interfaces/tokenizer` — Task B1, plan §8.
- `kb://interfaces/retrieval-text-builder` — Task B4, plan §10.
- `kb://interfaces/vector-record-store` — Task C3, plan §16.
- `kb://interfaces/document-graph-store` — Task E1, plan §22.
- `kb://interfaces/ingestion-job-store` — Task E3, plan §21.3.
- `kb://interfaces/selection` — Task A2, plan §5.
- `kb://interfaces/embedding-profile` — Task C2, plan §13.
- `kb://invariants/v0.8-ingestion-retrieval` — plan §39.
  Documents the eleven invariants this change must preserve
  (Git canonical truth, runtime rebuildability, branch
  awareness, content-addressed reuse, OpenSpec normativity,
  source provenance, license governance, offline operation, CPU
  fallback, single-container default, MCP retrieval-first
  behavior, Control Plane authorization, agent/vendor
  neutrality).
- `kb://project/retrieval-evaluation-corpus` — plan §29.
  Documents `evals/corpus/{synthetic,generated-pdf,multilingual,java,requirements}/`
  and the ignored `tmp/local/evals/` path.
- `kb://project/deployment-profiles` — plan §24. Documents the
  `minimal / semantic-cpu / semantic-gpu / quality /
  contextualized / multimodal` profile set as configuration
  presets, not code paths.

## Knowledge to update

Wiki nodes that must be updated when the corresponding Change
Package lands:

- `kb://architecture/system-overview` — Tasks A3, B1, C1, D1,
  E1. Add the new pipeline diagram from plan §41 alongside the
  existing v0.8 diagram; clarify that the new diagram is a
  refinement, not a replacement.
- `kb://architecture/platform-overview` — Task A3. Update the
  retrieval pipeline section to reflect the new stage order
  and the `DirectCandidate` / `SupportEvidence` split.
- `kb://modules/ingest` — Tasks A1, B1, B2, E1, E2, E3. Add
  the Docling PDF adapter, the resumable job model, the
  selective OCR policy, the table/figure handling, the
  `TokenizerPort` and `RetrievalTextBuilderPort`, and the
  LocalContextualizer isolation.
- `kb://modules/retrieval` — Tasks A1, A2, A3, A4, A5. Add
  `QueryFeatures`, the protected candidates, the new stage
  order, the selection layer, the retrieval trace, and the
  Context Assembler reserve escalation.
- `kb://modules/embeddings` — Tasks C1, C2, C3. Add the
  EmbeddingGemma 2 / Qwen3 adapters, the EmbeddingProfile
  identity, the VectorRecordStorePort, the disposable ANN
  index, and the CPU fallback.
- `kb://modules/runtime-store` — Task E1, plan §22. Add
  `DocumentGraphStorePort`, `IngestionJobStorePort`,
  `VectorRecordStorePort` and the new SQLite tables.
- `kb://modules/eval` — plan §28. Add Tier 2 (local model) and
  Tier 3 (`project-intelligence eval retrieval`).
- `kb://modules/mcp-server` — plan §33. Update the
  `retrieve_context` tool output and add the
  `project.get_retrieval_trace` debug tool.
- `kb://modules/security` — plan §23.1. Add the host
  accelerator security contract; reference the existing
  Policy Engine and Secret Provider.
- `kb://modules/registry` — plan §24. Document the
  profile/feature flag registration.
- `kb://interfaces/source-adapters` — Tasks E1, E2, E3. Add
  the PDF resumable hooks and the Docling mapper.
- `kb://interfaces/chunker` — Task B2. Document the additive
  `ChunkerContext` fields and the
  `SemanticBoundaryStrategy` + `TokenBudgetNormalizer`
  composition.
- `kb://interfaces/enrichment` — Tasks B4, B5. Document the
  `RetrievalTextBuilderPort` and the `LocalContextualizer`
  isolation.
- `kb://interfaces/hybrid-retrieval` — Task A1. Document the
  `QueryFeatures` routing and the protected candidates.
- `kb://interfaces/reranker` — Task F1, F2. Document the
  minimal/fast/quality/experimental profiles and the
  `rerank_text` construction rules.
- `kb://interfaces/runtime-store` — plan §22. Document the
  three new store ports and the new SQLite tables.
- `kb://interfaces/dense-index` — Task D1. Document the
  `USearchDenseIndex` adapter, the `auto | flat | usearch`
  selection, and the disposable index metadata.
- `kb://glossary/domain` — add terms
  `DirectCandidate`, `SupportEvidence`, `SelectionState`,
  `CandidateTrace`, `EmbeddingProfile`, `VectorRecord`,
  `SourceAnchor`, `DocumentRevision`, `DocumentElement`,
  `ElementKind`, `IngestionCheckpoint`, `RetrievalTrace`,
  `InferencePolicy`, `LocalContextualizer`.
- `kb://glossary/platform` — add terms
  `profile`, `evaluation tier`, `chunking composition`,
  `incremental processing key`, `ANN namespace`.
- `kb://project/distribution-vendors` — plan §23, §31. Add
  the host accelerator service, the model registry, the
  pinned model revisions, and the optional dependency
  groups.

## Knowledge to review for staleness

Wiki nodes that must be reviewed for staleness against the new
pipeline order, the new ports, and the new evaluation tiers:

- `kb://architecture/system-overview`
- `kb://architecture/platform-overview`
- `kb://modules/ingest`
- `kb://modules/retrieval`
- `kb://modules/embeddings`
- `kb://modules/runtime-store`
- `kb://modules/eval`
- `kb://modules/mcp-server`
- `kb://modules/registry`
- `kb://modules/security`
- `kb://interfaces/source-adapters`
- `kb://interfaces/chunker`
- `kb://interfaces/enrichment`
- `kb://interfaces/hybrid-retrieval`
- `kb://interfaces/reranker`
- `kb://interfaces/runtime-store`
- `kb://interfaces/dense-index`
- `kb://adr/0008-embedded-storage-selection` — confirm
  that the additive SQLite tables do not contradict the
  embedded-storage selection rationale.
- `kb://adr/0009-embedding-model-selection` — update or
  add a follow-up ADR reflecting the new EmbeddingProfile
  identity.
- `kb://adr/0010-hybrid-fusion-strategy` — add
  `0025-rerank-direct-before-graph-expansion.md` to
  document the new stage order.

## Affected implementation

### Modules / paths (additions)

- `pi_platform/core/canonical/document_graph.py`
- `pi_platform/core/ingest/token_budget.py`
- `pi_platform/core/ingest/retrieval_text_builder.py`
- `pi_platform/core/ingest/local_contextualizer.py`
- `pi_platform/core/retrieval/query_features.py`
- `pi_platform/core/retrieval/selection.py`
- `pi_platform/core/retrieval/retrieval_trace.py`
- `pi_platform/ports/ingest/tokenizer.py`
- `pi_platform/ports/ingest/retrieval_text_builder.py`
- `pi_platform/ports/ingest/ingestion_job_store.py`
- `pi_platform/ports/retrieval/selection.py`
- `pi_platform/ports/runtime/vector_record_store.py`
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
- `accelerator/` (new optional package; not built into the
  default container)
- `evals/corpus/{synthetic,generated-pdf,multilingual,java,requirements}/`
- `evals/corpus/golden_queries.yaml`
- `scripts/generate_pdf_fixtures.py`
- `scripts/chunk_size_sweep.py`

### Modules / paths (additive modifications)

- `pi_platform/core/canonical/value_types.py` — extend
  `Chunk` with `anchors: Sequence[SourceAnchor]`;
  bump `KNOWLEDGE_SCHEMA_VERSION` `1 → 2`.
- `pi_platform/ports/ingest/source_adapter.py` — extend
  `SourceAdapterPort`; replace `PLANNED_ADAPTERS.pdfplumber`
  with Docling.
- `pi_platform/ports/ingest/chunker.py` — extend
  `ChunkerContext` additively.
- `pi_platform/ports/ingest/context_enricher.py` — add
  retrieval-text builder contract.
- `pi_platform/ports/retrieval/hybrid_retrieval.py` and
  `pi_platform/core/retrieval/hybrid_retrieval.py` —
  introduce `QueryFeatures`; preserve pure-identifier fast
  path; mark exact candidates `PROTECTED` for mixed queries.
- `pi_platform/ports/retrieval/multi_stage_retrieval.py`
  and
  `pi_platform/core/retrieval/multi_stage_retrieval.py` —
  reorder stages per plan §4.2; attach `RetrievalTrace`.
- `pi_platform/core/retrieval/context_assembler.py` —
  `PRIMARY > PROTECTED > SUPPORT > RESERVE` order; reserve
  escalation; near-duplicate collapse while preserving
  provenance links.
- `pi_platform/adapters/retrieval/identifier_query_detector.py`
  — surface `has_free_text` and `quoted_phrases` for
  `QueryFeatures`.
- `pi_platform/adapters/ingest/chunkers.py` — wrap each
  structural chunker with the token budget normalizer.
- `pi_platform/adapters/ingest/layered_context_enricher.py`
  — invoke the `RetrievalTextBuilder` so the embedding input
  actually reflects the LLM suggestion when enabled.
- `pi_platform/adapters/ingest/local_pipeline_driver.py` —
  bind the PDF family to the new resumable job model.
- `pi_platform/adapters/runtime/sqlite_runtime_store.py` —
  add migration for new tables; do not rewrite existing
  rows.
- `pi_platform/core/orchestration/capability_discovery.py`
  — expose profile / model / device / fallback state /
  index compatibility.
- `pi_platform/mcp/server.py` — extend
  `retrieve_context` output; add
  `project.get_retrieval_trace(trace_id)` in debug mode.
- `pi_platform/control/feature_flags.py` — register
  profiles.
- `pyproject.toml` — add optional dependency groups
  `documents`, `semantic-embeddings`, `ann`, `reranking`,
  `accelerator`, `multimodal`.
- `distribution/licenses/model-licenses.json` — record
  model revisions.
- `distribution/skills/project-intelligence/...` — agent
  skill updates (plan §33).
- `Makefile` and `harness.py` — add the
  `project-intelligence eval retrieval` command, the PDF
  fixture generator, the chunk-size sweep, the Tier 2
  pytest marker, and the integration-quality-gate
  thresholds.

### Primary symbols / interfaces

New ports (normative contracts):

- `pi_platform/ports/ingest/tokenizer.TokenizerPort`
- `pi_platform/ports/ingest/retrieval_text_builder.Retri
  evalTextBuilderPort`
- `pi_platform/ports/ingest/ingestion_job_store.Ingestion
  JobStorePort`
- `pi_platform/ports/retrieval/selection.SelectionPort`
- `pi_platform/ports/runtime/vector_record_store.VectorRe
  cordStorePort`

Extended ports (additive fields/methods only):

- `pi_platform/ports/ingest/source_adapter.SourceAdapterP
  ort` — PDF resumable hooks
- `pi_platform/ports/ingest/chunker.ChunkerContext` —
  `target_tokens`, `max_tokens`, `min_tokens`,
  `tokenizer_id`, `merge_peers`
- `pi_platform/ports/ingest/context_enricher.ContextEnric
  herPort` — `RetrievalTextBuilderPort` injection
- `pi_platform/ports/retrieval/multi_stage_retrieval.Mult
  iStageRetrievalPort` — `RetrievalTrace` field on
  `RetrievalResult`
- `pi_platform/ports/retrieval/hybrid_retrieval.HybridRet
  rievalPort` — `QueryFeatures` input,
  `ProtectedCandidate` output

New core types:

- `pi_platform/core/canonical/document_graph.DocumentRevi
  sion`
- `pi_platform/core/canonical/document_graph.Page`
- `pi_platform/core/canonical/document_graph.DocumentElem
  ent` (and `Heading`, `Paragraph`, `List`, `Table`,
  `Figure`, `Formula`)
- `pi_platform/core/canonical/document_graph.ElementKind`
- `pi_platform/core/canonical/document_graph.SourceAnchor`
- `pi_platform/core/canonical/document_graph.AssetRef`
- `pi_platform/core/canonical/document_graph.TableGrid`
- `pi_platform/core/canonical/document_graph.IngestionChe
  ckpoint`
- `pi_platform/core/retrieval/query_features.QueryFeature
  s`
- `pi_platform/core/retrieval/selection.SelectionState`
  (`PRIMARY | RESERVE | PROTECTED | SUPPORT |
  DROPPED_DUPLICATE`)
- `pi_platform/core/retrieval/selection.CandidateTrace`
- `pi_platform/core/retrieval/retrieval_trace.RetrievalTr
  ace`

New SQLite tables (all in `runtime.db`):

- `document_revisions`
- `pages`
- `document_elements`
- `assets`
- `table_cells`
- `table_payloads`
- `chunk_anchors`
- `embeddings`
- `ingestion_jobs`
- `index_state`

## ADR impact

New ADRs to author (all under `.ai/wiki/adr/`):

- `0024-rich-document-graph-as-additive-submodel.md` —
  the additive submodel rationale; the existing
  `Document` / `Section` / `Chunk` remain the public
  surface.
- `0025-rerank-direct-before-graph-expansion.md` — the
  stage-order rationale and the
  `DirectCandidate` / `SupportEvidence` split.
- `0026-embedding-profile-identity-and-vector-namespace.md`
  — the `EmbeddingProfile` identity, the SHA-256
  compatibility key, the namespace separation, and the
  rebuild semantics.
- `0027-inference-policy-separate-from-source-policy.md`
  — the `InferencePolicy` (NO_MODEL |
  LOCAL_MODEL_ALLOWED | EXTERNAL_MODEL_ALLOWED) split
  from `SourcePersistencePolicy` (LOCAL_ONLY | REFERENCE
  | SNAPSHOT).
- `0028-usearch-as-default-ann-backend.md` —
  configuration-driven selection (no hard-coded corpus
  size threshold) and the disposable-ANN index rationale.

ADRs to update / cross-reference:

- `0004-ports-and-adapters-extension-style.md` —
  cross-reference the new ports; the style is unchanged
  but the catalogue grows.
- `0008-embedded-storage-selection.md` — confirm the
  additive SQLite tables do not contradict the
  embedded-storage selection rationale.
- `0009-embedding-model-selection.md` — update to
  reflect the new `EmbeddingProfile` identity and the
  EmbeddingGemma 2 / Qwen3-Embedding-0.6B evaluation
  profiles; reference `0026`.
- `0010-hybrid-fusion-strategy.md` — reference
  `0025-rerank-direct-before-graph-expansion.md`.
- `0017-phase-8-enterprise-security-boundary.md` —
  cross-reference the host accelerator security contract
  in `0028`.

## Acceptance criteria

Knowledge / harness acceptance:

- [ ] Wiki nodes listed under "Knowledge to create" exist
      with stable `id` frontmatter, link to the
      corresponding accepted spec or change, and are
      reachable from `.ai/wiki/INDEX.md`.
- [ ] Wiki nodes listed under "Knowledge to update" are
      revised and reviewed for staleness.
- [ ] New ADRs are committed with the same author /
      review standard as the existing `0001..0023` series.
- [ ] `kb_search` returns compact navigation cards for
      the new nodes (after
      `python scripts/session_state.py ... ; python
      scripts/... kb_refresh` if used).
- [ ] `kb_validate` reports no broken internal links.
- [ ] Generated local context index
      (`tmp/local/project-context/`) is refreshed.
- [ ] `openspec/CURRENT.md` is updated to list any newly
      adopted specs; the proposed change folder is
      archived per the OpenSpec workflow.
- [ ] `ARTIFACT_MANIFEST.sha256` is refreshed after the
      implementation work that lands with this change.
- [ ] `distribution/licenses/model-licenses.json`
      records the pinned model revisions, and the
      License Gate (`pi_platform/control/policy_engine.py`
      + `distribution/license-gate/`) accepts the
      additions.
- [ ] Optional dependency groups in `pyproject.toml`
      (`documents`, `semantic-embeddings`, `ann`,
      `reranking`, `accelerator`, `multimodal`) keep
      `pip install -e .` working without any of them.
- [ ] Distribution bundles
      (`distribution/skills/project-intelligence/...`)
      embed the updated agent skill, including the
      `protected exact candidates`, `reserve escalation`,
      and `retrieval trace` guidance.
- [ ] Control Plane diagnostics
      (`pi_platform/control/...`) expose the active
      profile, model IDs/revisions, device, RAM/VRAM
      capability result, fallback state, index
      compatibility, and reranker status
      (plan §24, §32).
- [ ] `Makefile` and `harness.py` add the
      `project-intelligence eval retrieval` command and
      the Tier 2 pytest marker
      (`@pytest.mark.local_model`).
- [ ] The integration-quality-gate thresholds
      (plan §28.3) are recorded in
      `evals/quality_gates.yaml`.
- [ ] Spec/implementation mismatches found during
      review are resolved or explicitly documented in
      the corresponding Wiki page's "Known mismatches"
      section.
