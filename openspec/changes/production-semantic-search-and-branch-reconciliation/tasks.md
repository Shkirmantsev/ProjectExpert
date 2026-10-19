# Tasks — production-semantic-search-and-branch-reconciliation

Ordered by the plan §80 dependency graph:
`PR1 → PR2 → PR3 → PR4 → PR5 → PR6 → PR7 → PR8 → PR9 → PR10 → PR11 → PR12`.
Each block is exactly one logical PR slice from plan §79. PR10 (Docling)
depends on PR2 only and may execute in parallel with PR3–PR9; PR11 waits
for PR8, PR9 and PR10; PR12 waits for PR11. Every block ends with focused
verification and `python harness.py check`.

---

## PR1 — Production configuration and truthfulness

Plan §2, §19, §20, §61, §63. Delta:
`specs/2026-10-18-production-runtime-configuration-resolver/`.

- [ ] 1. Add `pi_platform/core/config/runtime_configuration.py` and
      `pi_platform/adapters/config/runtime_configuration_resolver.py`
      implementing one precedence chain: CLI argument → environment
      variable (`PI_EMBEDDING_MODEL`, `PI_EMBEDDING_DEVICE`,
      `PI_DENSE_INDEX`, `PI_MODEL_CACHE`, `PI_DOCLING_ENABLED`) → local
      runtime settings (`.project-intelligence-cache/settings.json`) →
      `project-context.yaml` default → built-in default
      (`gemma` / `auto` / `usearch`).
- [ ] 2. Implement the three public startup profiles `production`,
      `minimal`, `development`; `minimal` MUST be selected explicitly and
      is the only profile where hashing is allowed; `production` MUST NOT
      silently substitute hashing and MUST fail startup with an
      actionable error when a selected production dependency is missing.
- [ ] 3. Implement truthful capability reporting: never report
      available=true for a stub; report real-and-available,
      real-and-not-installed or disabled with model id, revision,
      dimension and device. Route `embedding-status`, `retrieval-status`
      and `capabilities` through the resolved runtime configuration
      (remove the hard-coded `active_backend = hashing`).
- [ ] 4. Focused tests: `tests/test_runtime_configuration_resolver.py`,
      `tests/test_startup_profiles.py`,
      `tests/test_capability_truthfulness.py` (precedence chain,
      production missing-model failure, explicit minimal hashing,
      truthful report).
- [ ] 5. Verification: `python -m pytest tests/test_runtime_configuration_resolver.py tests/test_startup_profiles.py tests/test_capability_truthfulness.py -q`
      then `python harness.py check`.

---

## PR2 — Embedding port query/document roles

Plan §7, §8, §11. Delta:
`specs/2026-10-18-embedding-port-query-document-roles/`.

- [ ] 1. Extend `pi_platform/ports/retrieval/embedding_model.py` with a
      role-aware request contract: role (`query` / `document`), task
      (`search` / `code-retrieval` / `question-answering`), optional
      title; convenience helpers delegate to exactly one underlying
      semantic contract. Update `pi_platform/core/retrieval/embedding_model.py`
      callers so every call site declares the role explicitly.
- [ ] 2. Add the profile instruction-version field to
      `pi_platform/ports/retrieval/embedding_profile.py` and include it
      in `EmbeddingProfile.identity()`.
- [ ] 3. Update `pi_platform/adapters/retrieval/hashing_embedding_model.py`
      and existing embedding tests for role-aware requests (deterministic
      per role in test/minimal profiles).
- [ ] 4. Focused tests: `tests/test_embedding_roles.py`,
      `tests/test_hashing_embedding_fallback.py`,
      `tests/test_embedding_profile_identity.py`.
- [ ] 5. Verification: `python -m pytest tests/test_embedding_roles.py tests/test_hashing_embedding_fallback.py tests/test_embedding_profile_identity.py -q`
      then `python harness.py check`.

---

## PR3 — Real EmbeddingGemma 2

Plan §6.1, §9, §12–§14, §101. Delta:
`specs/2026-10-18-real-embeddinggemma2-binding/`.

- [ ] 1. Replace the stub body of
      `pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py`
      with the real SentenceTransformer/Transformers binding: pinned
      immutable revision of `google/embeddinggemma-2`, 512d output with
      post-truncation L2 normalization, task-aware query/document
      prompting, text-only loading (unused encoders disabled),
      float32 on CPU and bfloat16 on supported accelerators (never
      float16 by default), batch encoding, health checks.
- [ ] 2. Add `pi_platform/adapters/retrieval/embedding_model_factory.py`
      and `pi_platform/adapters/retrieval/model_cache.py`: alias
      resolution (`gemma` / `embeddinggemma2` / `qwen` / `qwen3`),
      dependency and licence validation, cache path and device
      resolution (auto → CPU when safe accelerator memory is missing),
      model health check. Replace `pinned-stub` in the Gemma profile and
      in `distribution/licenses/model-licenses.json` with the real
      immutable revision.
- [ ] 3. Focused tests: `tests/test_embeddinggemma2_embedding_model.py`
      (real weights, marked integration),
      `tests/test_embedding_model_factory.py`,
      `tests/test_model_cache.py`, plus numerical assertions for 512d,
      normalization and float policy.
- [ ] 4. Verification: `python -m pytest tests/test_embeddinggemma2_embedding_model.py tests/test_embedding_model_factory.py tests/test_model_cache.py -q`
      then `python harness.py check`.

---

## PR4 — Real Qwen3 embedding 0.6B

Plan §6.2, §10, §12–§14, §101. Delta:
`specs/2026-10-18-real-qwen3-embedding-binding/`.

- [ ] 1. Replace the stub body of
      `pi_platform/adapters/retrieval/qwen3_embedding_model.py` with the
      real binding: pinned immutable revision of
      `Qwen/Qwen3-Embedding-0.6B`, 1024d output with L2 normalization,
      query instruction enabled, document encoding without instruction,
      correct batched padding, device policy and health checks.
- [ ] 2. Wire the `qwen` / `qwen3` aliases through the PR3 factory and
      model cache; replace `pinned-stub` for the Qwen profile in
      `pi_platform/ports/retrieval/embedding_profile.py` and
      `distribution/licenses/model-licenses.json`.
- [ ] 3. Focused tests: `tests/test_qwen3_embedding_model.py` (real
      weights, marked integration), batch-vs-single equivalence,
      instruction applied only to query role, dimension and
      normalization assertions.
- [ ] 4. Verification: `python -m pytest tests/test_qwen3_embedding_model.py tests/test_embedding_model_factory.py -q`
      then `python harness.py check`.

---

## PR5 — Persistent semantic indexing service

Plan §24–§26. Delta:
`specs/2026-10-18-semantic-index-service/`.

- [ ] 1. Add `pi_platform/core/retrieval/semantic_index_service.py`:
      find active chunks → build retrieval text → look up
      `VectorRecordStorePort` → embed only misses → persist vectors →
      build/load dense index → validate counts → activate generation.
      Reuse key = retrieval-text hash + profile identity hash.
- [ ] 2. Model-switch namespace handling: switching profiles reuses
      source/chunk knowledge, builds or reuses the selected vector
      namespace, and never mixes profile spaces; canonical Git files are
      read-only during the switch.
- [ ] 3. Focused tests: `tests/test_semantic_index_service.py`,
      `tests/test_vector_reuse_key.py`, `tests/test_model_switch_namespaces.py`
      (no re-embedding of unchanged text, namespace isolation, count
      validation).
- [ ] 4. Verification: `python -m pytest tests/test_semantic_index_service.py tests/test_vector_reuse_key.py tests/test_model_switch_namespaces.py -q`
      then `python harness.py check`.

---

## PR6 — Real USearch dense backend

Plan §21–§23, §29, §30, §42. Delta:
`specs/2026-10-18-real-usearch-dense-backend/`.

- [ ] 1. Replace the stub body of
      `pi_platform/adapters/runtime/usearch_dense_index.py` with a real
      `usearch.index.Index` binding (cosine, add/search, save/load/view,
      pinned connectivity/expansion settings); production dense backend
      becomes `usearch`; the flat backend stays for tests/small corpora.
- [ ] 2. Add `pi_platform/adapters/runtime/dense_key_store.py` mapping
      string chunk IDs to stable numeric keys and back; persist
      generation metadata (`embedding_profile_hash`,
      `source_generation`, `vector_count`, `index_schema_version`).
- [ ] 3. Atomic build/activation: write
      `<generation>.usearch.tmp`, validate profile hash, dimension,
      expected vector count and sample queries, atomically rename, then
      update `runtime-state/active-version.json`; support rebuild from
      the vector store without re-embedding.
- [ ] 4. Focused tests: `tests/test_usearch_dense_index.py`,
      `tests/test_dense_key_store.py`, `tests/test_index_generation_identity.py`,
      `tests/test_atomic_index_activation.py`.
- [ ] 5. Verification: `python -m pytest tests/test_usearch_dense_index.py tests/test_dense_key_store.py tests/test_index_generation_identity.py tests/test_atomic_index_activation.py -q`
      then `python harness.py check`.

---

## PR7 — Unified production retrieval composition

Plan §27, §28. Delta:
`specs/2026-10-18-unified-production-retrieval-composition/`.

- [ ] 1. Introduce the shared composition root
      (`build_production_retrieval_runtime`) over the existing ports:
      embedding model, vector store, dense index, sparse/exact indexes,
      hybrid retrieval, reranker, selection, graph expansion, context
      assembler, multi-stage retrieval. Consume it from
      `pi_platform/adapters/ui/composition.py`, `pi_platform/mcp/context.py`,
      `pi_platform/cli/main.py` and evaluation.
- [ ] 2. Remove the UI hash-scan dense path: query embedding runs once;
      dense + sparse + exact channels fuse; filters, rerank, selection,
      graph support and context assembly follow the accepted stage
      order.
- [ ] 3. Focused tests: `tests/test_production_retrieval_composition.py`,
      extend `tests/test_mcp_retrieval_output.py` and
      `tests/test_mcp_context_factory.py` with same-query-same-result
      assertions across UI and MCP.
- [ ] 4. Verification: `python -m pytest tests/test_production_retrieval_composition.py tests/test_mcp_retrieval_output.py tests/test_mcp_context_factory.py -q`
      then `python harness.py check`.

---

## PR8 — Persisted runtime snapshot reconciliation

Plan §31–§42, §68–§70. Delta:
`specs/2026-10-18-persisted-runtime-snapshot-reconciliation/`.

- [ ] 1. Add `pi_platform/ports/git/version_snapshot.py`,
      `pi_platform/core/sync/version_snapshot.py` and
      `pi_platform/adapters/runtime/runtime_version_state.py` persisting
      `runtime-state/active-version.json`, `manifest-snapshot.json`,
      `source-snapshot.json` (last successfully served state only).
- [ ] 2. Rewrite `pi_platform/core/sync/reconcile.py` to diff the
      persisted previous snapshot against a freshly built current
      snapshot (HEAD + working-tree fingerprint + manifests + source
      inventory): UNCHANGED reuse, ADDED process, MODIFIED invalidate and
      rebuild, REMOVED tombstone/remove from active sparse, dense and
      graph state. Fix startup wiring that passes current HEAD as both
      previous and current.
- [ ] 3. Add `pi_platform/core/sync/version_monitor.py` (portable 2–5 s
      polling of HEAD + working-tree fingerprint) and wire
      `pi_platform/core/sync/readiness.py` so refreshes hold readiness
      false, requests get "refreshing" / 503 semantics, only one
      reconciliation runs per project (`project_lock.py`), and
      activation is atomic per plan §42.
- [ ] 4. Focused tests: the plan §68 branch matrix in
      `tests/test_branch_reconciliation_matrix.py`,
      `tests/test_version_monitor.py`,
      `tests/test_removed_data_tombstones.py`,
      `tests/test_working_tree_fingerprint.py`, plus existing
      `tests/test_content_address_cross_branch.py`.
- [ ] 5. Verification: `python -m pytest tests/test_branch_reconciliation_matrix.py tests/test_version_monitor.py tests/test_removed_data_tombstones.py tests/test_working_tree_fingerprint.py tests/test_content_address_cross_branch.py -q`
      then `python harness.py check`.

---

## PR9 — Repository source discovery

Plan §43, §44. Delta:
`specs/2026-10-18-repository-source-discovery-incremental/`.

- [ ] 1. Add `pi_platform/core/ingest/repository_source_discovery.py`
      with the default include set (sources, build descriptors,
      `openspec/**`, `docs/**`, `requirements/**`, Markdown/HTML, API and
      spec files) and exclude set (`.git/**`,
      `.project-intelligence-cache/**`, `tmp/local/**`, build outputs,
      vendored generated trees), feeding the ingestion pipeline driver.
- [ ] 2. Persist incremental discovery state (path, source family,
      content hash, parser version, last effective retrieval-text hash);
      never reparse unchanged files; report added/modified/removed to the
      PR8 reconciliation diff.
- [ ] 3. Focused tests: `tests/test_repository_source_discovery.py`,
      `tests/test_incremental_discovery_state.py` (new file discovered,
      unchanged file skipped, removed file tombstoned, excludes honoured).
- [ ] 4. Verification: `python -m pytest tests/test_repository_source_discovery.py tests/test_incremental_discovery_state.py -q`
      then `python harness.py check`.

---

## PR10 — Real Docling PDF adapter and hybrid chunker

Plan §45–§50 (depends on PR2 only; may run parallel to PR3–PR9). Delta:
`specs/2026-10-18-real-docling-pdf-adapter-and-hybrid-chunker/`.

- [ ] 1. Replace the synthetic body of
      `pi_platform/adapters/pdf/docling_pdf_adapter.py` with real
      `DocumentConverter` conversion; map `DoclingDocument` to the
      neutral document model only at the adapter boundary (no vendor
      types past it); enable tables, figures and selective OCR per
      `pi_platform/adapters/pdf/ocr_policy.py`.
- [ ] 2. Replace the stub delegation in
      `pi_platform/adapters/pdf/docling_chunker.py` with the real
      `HybridChunker` configured with a tokenizer aligned to the active
      embedding model; keep canonical chunking model-independent and
      treat tokenizer splits as runtime embedding projections
      (`pi_platform/core/retrieval/` optional segment type per plan §50);
      resume checkpoints reuse `IngestionJobStorePort`.
- [ ] 3. Add the pinned Docling dependency group to `pyproject.toml`
      (via the orchestrator-owned source gate) and inventory Docling /
      OCR model asset licences separately in
      `distribution/licenses/`.
- [ ] 4. Focused tests: `tests/test_docling_pdf_adapter.py`,
      `tests/test_docling_chunker.py`, `tests/test_document_graph_roundtrip.py`,
      `tests/test_ingestion_job_store.py`, per-document failure
      isolation, and a no-Git-churn assertion on model switch.
- [ ] 5. Verification: `python -m pytest tests/test_docling_pdf_adapter.py tests/test_docling_chunker.py tests/test_document_graph_roundtrip.py tests/test_ingestion_job_store.py -q`
      then `python harness.py check`.

---

## PR11 — One-command production UX

Plan §15–§18, §55–§60, §83–§88, §99 (after PR8, PR9, PR10). Delta:
`specs/2026-10-18-one-command-production-ux/`.

- [ ] 1. Add `project-intelligence start` and the `models` command group
      (`list` / `status` / `pull` / `verify` / `use`) to
      `pi_platform/cli/main.py`; startup sequence: start HTTP early
      (readiness false) → ensure model → hydrate → reconcile → discover →
      ingest → embed → index → atomic activation → readiness true;
      MCP stays fail-closed while not ready.
- [ ] 2. First-start wizard at `/` when no local embedding configuration
      exists (target repository, EmbeddingGemma 2 vs Qwen3-Embedding-0.6B,
      device auto/CPU/GPU, enable document processing, initialize and
      build); bootstrap progress surface while indexing runs.
- [ ] 3. Admin retrieval settings
      (`pi_platform/core/control/retrieval_settings.py`,
      `pi_platform/adapters/ui/retrieval_admin_routes.py`): model and
      device switching with the model-switch state machine (plan §87),
      stored in `.project-intelligence-cache/settings.json`, never in
      canonical Git.
- [ ] 4. Product Makefile targets (`pi-help`, `pi-up`, `pi-model`,
      `pi-status`, `pi-reindex`, `pi-doctor`, `pi-down`), production
      Docker profile and persistent model volume
      (`docker-compose.yml`, `Containerfile` edits owned by the
      orchestrator gate).
- [ ] 5. Focused tests: `tests/test_start_command.py`,
      `tests/test_first_start_wizard.py`,
      `tests/test_retrieval_settings.py`, `tests/test_model_switch_state_machine.py`,
      `tests/test_makefile_product_targets.py`.
- [ ] 6. Verification: `python -m pytest tests/test_start_command.py tests/test_first_start_wizard.py tests/test_retrieval_settings.py tests/test_model_switch_state_machine.py tests/test_makefile_product_targets.py -q`
      then `python harness.py check`.

---

## PR12 — Production capability and release gates

Plan §64–§74, §89–§92, §97 (after PR11). Delta:
`specs/2026-10-18-production-capability-and-release-gates/`.

- [ ] 1. Add the `production-capability-gate` test/CI step that fails on
      `pinned-stub`, `not bound`, `usearch-stub`, synthetic document
      adapters, unconditionally failing production model adapters, or
      `pinned-stub` entries in
      `distribution/licenses/model-licenses.json` (plan §64, §97).
- [ ] 2. Heavy integration tier (merge to dev / nightly / release): real
      cached EmbeddingGemma 2 and Qwen weights, real USearch, real
      Docling fixtures, branch-switch matrix, model-switch integration,
      offline deployment check (plan §65–§73, §90). Fast PR CI keeps the
      deterministic hashing/test profile.
- [ ] 3. End-to-end one-command acceptance covering the plan §99 user
      story (`make pi-up …`, model switch via `make pi-model …`, branch
      switch) with licence/SBOM verification
      (`distribution/licenses/dependency-inventory.json`).
- [ ] 4. Focused tests: `tests/test_production_capability_gate.py`,
      `tests/test_license_sbom_gate.py`,
      `tests/test_first_run_end_to_end.py`, `tests/test_offline_deployment.py`.
- [ ] 5. Verification: `python -m pytest tests/test_production_capability_gate.py tests/test_license_sbom_gate.py tests/test_first_run_end_to_end.py tests/test_offline_deployment.py -q`
      then `python harness.py check`; record each gate result in the
      session checkpoint before handoff.