# Proposal — Improve ingestion, retrieval, and local-model execution (v0.8 refinement)

## Why

The v0.8 Project Intelligence Platform is shipped and accepted
(`openspec/specs/2026-10-04-*` and Phase 5/6/7/8/9/10 additions in
`openspec/CURRENT.md`). The architecture is sound: canonical Git
knowledge, ports/adapters, content addressing, local source inbox,
SQLite runtime store, sparse/FTS/dense index ports, hybrid retrieval,
multi-stage retrieval, metadata filtering, graph expansion, reranker
port, context assembler, local-LLM port, query orchestrator, MCP/skill
distribution, Control Plane, and the enterprise security boundary
are all present.

What is not yet production-quality for the next refi nement layer
(per `ProjectExpert-v0.8-ingestion-retrieval-improvement-plan.md`,
sections 1 and 3):

- PDF is declared (`SourceContentFamily.PDF`) but the
  `pi_platform/adapters/pdf/` package is empty; the old `pdfplumber`
  plan is stale.
- The current canonical model loses rich PDF structure (no page
  geometry, no first-class tables/figures/formulas, no per-element
  provenance).
- Chunking is structural but byte-based, not tokenizer-aware.
- `LayeredContextEnricher` calls an optional local LLM but its output
  is only stored as metadata; the LLM does not contribute to the text
  actually passed to the embedding model.
- The semantic embedding adapter (`MultilingualSentenceTransformerEmbeddingModel`)
  is a contract stub; the hashing model is the de-facto default.
- The dense index is a flat fallback only; no USearch / ANN adapter.
- Hybrid retrieval treats any query containing an engineering
  identifier as exact-only, dropping the semantic channel for mixed
  queries such as "Why is ILO-5193 handled in PackingService?".
- `MultiStageRetrievalCore` performs graph/hierarchy expansion before
  reranking, displacing direct answers with support nodes and wasting
  reranker CPU.
- There is no non-destructive candidate selection layer
  (`PRIMARY / RESERVE / PROTECTED / SUPPORT / DROPPED_DUPLICATE`) and
  no persistent retrieval trace.
- Embedding vectors are not namespaced by model/dimension/revision,
  so different vector spaces can be silently mixed.
- The cross-encoder reranker adapter is still a placeholder; the
  Qwen3-Reranker / Qwen3-Embedding profiles are not bound.
- Evaluation is deterministic-synthetic only; there is no real
  local-model evaluation tier, no chunk-size sweep, no
  PDF/table/figure fixtures, no `project-intelligence eval retrieval`
  command.

These gaps are not architectural defects — they are missing
production-quality refinements of ports the platform already
exposes. Replacing the architecture would lose the v0.8 invariants
(plan §39: Git canonical truth, runtime rebuildability, branch
awareness, content-addressed reuse, OpenSpec normativity, source
provenance, license governance, offline operation, CPU fallback,
single-container default, MCP retrieval-first behavior, Control Plane
authorization, agent/vendor neutrality).

This change therefore creates the OpenSpec artifacts (proposal, design,
delta specs, tasks, context-impact) that turn the plan into a
verifiable, prioritized, dependency-ordered v0.8 refinement. After
this change is adopted, implementation can proceed package by package
(A through H) without violating the v0.8 invariants.

## Goal

Adopt OpenSpec change artifacts for the v0.8 ingestion/retrieval
refinement that:

- split the 41 plan sections into **eight bounded Change Packages**
  (A retrieval correctness, B tokenizer-aware chunking, C production
  embeddings, D ANN backend, E rich PDF document graph + resumable
  Docling ingestion, F quality reranker, G optional host accelerator,
  H optional multimodal figures) plus a P0 baseline-measurement
  gate, with explicit ordering and dependencies (plan §38);
- define **new additive behavioural specs** for capabilities that
  are genuinely new (rich document graph, resumable document
  ingestion, retrieval candidate selection, embedding execution
  profile, retrieval trace, embedding profile identity) without
  duplicating or rewriting accepted specs;
- declare **delta requirements** against the accepted capabilities
  the plan touches (canonical-knowledge-schema, document-source-
  adapters, ingestion-pipeline-driver, semantic-structural-chunking,
  context-enrichment, runtime-store, dense-index, embedding-model,
  hybrid-retrieval, multi-stage-retrieval, reranker-port, context-
  assembler, retrieval-benchmark, capability-discovery, one-click-
  distribution, integration-quality-gates);
- describe a **technical design** that extends the existing
  `pi_platform/{core,ports,adapters}/` tree, leaves the control
  plane, MCP server, distribution, and security boundary untouched,
  and explicitly preserves the v0.8 invariant list (plan §39);
- identify the **Wiki, ADR, manifest, SBOM, License Gate, and
  Control Plane** updates that must accompany implementation
  (plan §31, §32, §33);
- enumerate a **fine-grained, dependency-ordered task list** an
  agent or developer can execute top-to-bottom to deliver the eight
  change packages without regressing the v0.8 architecture or
  weakening any accepted requirement.

Out of scope for this change:

- writing any platform source code, configuration, container build
  step, plugin bundle, distribution artefact, or any other runtime
  artefact;
- downloading or binding any embedding, reranker, or LLM model
  weights; this change decides the contracts and tasks, not the
  weight fetches;
- re-architecting the control plane, MCP server, or the
  enterprise security boundary; these are touched only via
  additive integration points and the existing capability/policy
  registry;
- changing the accepted `runtime_entries` schema or any
  accepted contract that would invalidate existing accepted
  requirements; the additive new stores live alongside it (plan
  §22, §34.1).

What this change does:

- creates the change folder
  `openspec/changes/improve-ingestion-retrieval-local-models/`
  with `proposal.md`, `design.md`, `tasks.md`, `context-impact.md`,
  and a `specs/` tree;
- introduces the five new capability delta folders:
  - `rich-document-graph`
  - `resumable-document-ingestion`
  - `retrieval-candidate-selection`
  - `embedding-execution-profile`
  - `retrieval-trace`
- introduces delta spec folders against accepted capabilities,
  matching their existing dated identity (e.g.
  `2026-10-04-hybrid-retrieval`) so the harness gate keeps them
  recognized;
- defines the **EmbeddingProfile** identity, namespace, and
  compatibility key (plan §13) as a normative contract;
- defines the **SelectionState** and **CandidateTrace** contracts
  (plan §5) as runtime-only, non-canonical evaluation state;
- defines the **TokenizerPort**, **RetrievalTextBuilderPort**,
  **LocalContextualizer**, **IngestionJobStorePort**,
  **VectorRecordStorePort**, **DocumentGraphStorePort** as new
  port interfaces under the existing `pi_platform/ports/` tree;
- declares the **stage order** for multi-stage retrieval
  (plan §4.2) and the **Context Assembler evidence order**
  (plan §6) as normative;
- defines the **chunking composition** (semantic boundary →
  structural candidate → token-budget normalizer) as a normative
  composition rule without removing any existing structural
  chunker (plan §8);
- defines the **PDF ingestion pipeline** (prescan → batched parse →
  job checkpoint → selective OCR → tables/figures/assets) behind the
  existing `SourceAdapterPort` and `ChunkerPort` (plan §21);
- defines the **retrieval trace** contract, its serialisability,
  its redaction rules, and its Control Plane integration (plan §7);
- defines the **deployment / model profiles** (minimal,
  semantic-cpu, semantic-gpu, quality, contextualized, multimodal)
  as configuration presets, not as code paths (plan §24);
- declares the **evaluation tiers** (synthetic CI, local model
  integration, `project-intelligence eval retrieval` command)
  (plan §28);
- declares the **incremental processing rules** that distinguish
  content change, enrichment change, embedding model change, and
  ANN implementation change for cache reuse (plan §30);
- lists the **model and dependency licensing** requirements and the
  existing License Gate interaction (plan §31).

## Affected capabilities

### New capabilities (delta spec folders created in this change)

| Proposed capability | Plan reference |
| --- | --- |
| Rich document graph | §3.2, §19, §20 |
| Resumable document ingestion | §21.1–§21.6 |
| Retrieval candidate selection | §5, §5.1–§5.4 |
| Embedding execution profile | §13, §14, §15, §24 |
| Retrieval trace | §7 |

New capability folders retain semantic names until adoption; on
adoption they receive the date of first Git acceptance and move to
`openspec/specs/YYYY-MM-DD-domain-capability/`.

### Accepted capabilities extended by deltas

| Accepted capability | Plan reference | Delta intent |
| --- | --- | --- |
| Canonical knowledge schema | §3.2, §19, §20 | add `DocumentRevision`, `Page`, `DocumentElement`, `ElementKind`, `SourceAnchor`, `AssetRef`, `TableGrid`, `IngestionCheckpoint`; add `Chunk.anchors`; bump schema version; add migration. |
| Document source adapters | §3.1, §21 | implement `DoclingPdfAdapter` behind `SourceAdapterPort`; deprecate the `pdfplumber` plan. |
| Ingestion pipeline driver | §21 | bind PDF family to the new resumable job model. |
| Semantic structural chunking | §3.3, §8, §9 | retain structural strategies; add token-aware normalization + Docling `HybridChunker` adapter for PDF; extend `ChunkerContext` additively. |
| Context enrichment | §3.4, §10, §11 | introduce `RetrievalTextBuilderPort`; add `LocalContextualizer`; separate `InferencePolicy` from source persistence policy. |
| Runtime store | §22 | add `DocumentGraphStorePort`, `IngestionJobStorePort`, `VectorRecordStorePort`; share `runtime.db` physically, decouple logically. |
| Dense index | §3.6, §17 | add `USearchDenseIndex` behind the existing `DenseIndexPort`; selection driven by configuration/capabilities. |
| Embedding model | §3.5, §12, §13, §14, §15, §16 | bind one real local semantic adapter (EmbeddingGemma 2 as the first profile); introduce `EmbeddingProfile`; persist vectors via `VectorRecordStorePort`. |
| Hybrid retrieval | §4.1, §5.2 | add `QueryFeatures` and protected candidates; preserve pure-identifier fast path. |
| Multi stage retrieval | §4.2, §5.3 | reorder stages so direct evidence reranks before graph/hierarchy expansion; introduce `DirectCandidate` vs `SupportEvidence` separation. |
| Reranker port | §18, §18.1, §18.2 | keep BM25-light fallback; add minimal/fast/quality/experimental profiles; build a separate `rerank_text`; timeouts and CPU fallback. |
| Context assembler | §6, §5.3 | PRIMARY/PROTECTED/SUPPORT/RESERVE awareness; reserve escalation; near-duplicate collapse while preserving links. |
| Retrieval benchmark | §28.1–§28.4 | add Tier 2 (local model) and Tier 3 (`project-intelligence eval retrieval`); chunk-size sweep. |
| Capability discovery | §24 | expose active profile, model IDs/revisions, device, fallback state, index compatibility, reranker status. |
| One-click distribution | §23, §31 | keep minimal profile lightweight; host accelerator is an optional profile, not part of the default container. |
| Integration quality gates | §37 | add `recall@5/recall@10`, `MRR`, `NDCG`, `protected-hit retention`, `context coverage`, `avg context tokens`, `p50/p95 latency`, `peak RAM`, `embedding throughput`, `reranker throughput`, `cache reuse`, `branch-switch hydration` to the quality gates. |

## Compatibility / migration impact

This change is **strictly additive**. It does not delete or
re-serialize any existing accepted capability body, and it does
not replace the existing `RuntimeStorePort` API.

Migration rules:

1. **Schema version bump.** Only the canonical-knowledge schema
   version is bumped, and only for the additive fields
   (`DocumentRevision`, `SourceAnchor`, `Chunk.anchors`). Existing
   `Document` / `Section` / `Chunk` / `Entity` / `Relation` /
   `Evidence` records remain valid; new fields are optional and
   absent on legacy records.
2. **Runtime store.** New tables
   (`document_revisions`, `pages`, `document_elements`, `assets`,
   `table_cells`, `table_payloads`, `chunk_anchors`, `embeddings`,
   `ingestion_jobs`, `index_state`) are added in their own
   migrations; existing `runtime_entries` content is untouched.
3. **Embedding vector records.** No existing on-disk vector is
   invalidated. New vectors are stored under a new
   `embedding_profile_hash` namespace; mixing with legacy
   `HashingEmbeddingModel` vectors is explicitly disallowed
   (plan §13).
4. **ANN index.** The ANN index (USearch) is a disposable derived
   artefact stored under
   `.project-intelligence-cache/indexes/<embedding_profile_hash>/`;
   it is not committed to Git and can be rebuilt from
   `VectorRecordStorePort` without re-embedding (plan §16, §17.1).
5. **PDF source family.** `SourceContentFamily.PDF` already exists;
   the existing `pdfplumber` plan is replaced in `PLANNED_ADAPTERS`
   by the Docling adapter. If a target project already started a
   PDF ingestion with the placeholder, that ingestion must be
   aborted and the source is re-registered; the platform does not
   attempt to upgrade an empty partial ingestion.
6. **Local LLM.** `LocalLLMPort` and `LocalContextualizer` are
   introduced as an opt-in profile. When disabled, the deterministic
   `RetrievalTextBuilder` produces identical output to today's
   `LayeredContextEnricher` for documents where no local LLM is
   available (plan §34.8).
7. **Reranker.** When the reranker profile is `minimal`, the system
   must produce byte-identical rerank output to today's
   `BM25-light fallback` so the synthetic Tier 1 benchmark stays
   green. `CrossEncoderRerankerAdapter` becomes a real adapter
   behind a profile, not a constructor placeholder.
8. **CLI.** `project-intelligence eval retrieval` is added without
   changing existing CLI commands.

If a target project's ingestion, embedding, or reranker data is
incompatible with a new profile, the platform rejects the operation
with a clear, security-redacted error (plan §13, §23.1). It never
silently mixes vector spaces.

## Related knowledge

Wiki nodes that explain the v0.8 baseline this change builds on:

- `kb://architecture/platform-overview`
- `kb://architecture/system-overview`
- `kb://architecture/platform-overview` — Phase 4 retrieval
  pipeline and the existing ports.
- `kb://interfaces/source-adapters`
- `kb://interfaces/chunker`
- `kb://interfaces/enrichment`
- `kb://interfaces/hybrid-retrieval`
- `kb://interfaces/reranker`
- `kb://modules/ingest`
- `kb://modules/retrieval`
- `kb://modules/embeddings`
- `kb://modules/runtime-store`
- `kb://modules/mcp-server`
- `kb://modules/security`
- `kb://modules/registry` (Control Registry / Hook Runtime / Policy
  Engine / Secret Provider / Audit Log / Feature Flags)
- `kb://modules/eval`
- `kb://adr/0004-ports-and-adapters-extension-style`
- `kb://adr/0008-embedded-storage-selection`
- `kb://adr/0009-embedding-model-selection`
- `kb://adr/0010-hybrid-fusion-strategy`
- `kb://adr/0017-phase-8-enterprise-security-boundary`
- `kb://invariants/v0.8`

New Wiki knowledge to author in the implementation packages
(see `context-impact.md` for the full list):

- `kb://architecture/rich-document-graph`
- `kb://architecture/retrieval-candidate-selection`
- `kb://architecture/embedding-profile-identity`
- `kb://modules/retrieval-trace`
- `kb://modules/host-embedding-accelerator`
- `kb://adr/0024-rich-document-graph-as-additive-submodel`
- `kb://adr/0025-rerank-direct-before-graph-expansion`
- `kb://adr/0026-embedding-profile-identity-and-vector-namespace`
- `kb://adr/0027-inference-policy-separate-from-source-policy`
- `kb://invariants/v0.8-ingestion-retrieval`
- `kb://interfaces/tokenizer`
- `kb://interfaces/retrieval-text-builder`
- `kb://interfaces/vector-record-store`
- `kb://interfaces/document-graph-store`
- `kb://interfaces/ingestion-job-store`
- `kb://interfaces/selection`
- `kb://interfaces/embedding-profile`

This proposal is the gate. The implementation work, the
per-package design choices, and the verification gates live in
`tasks.md` and `design.md`. The new capability folder layout,
schema bumps, and per-capability delta bodies live under
`specs/`.
