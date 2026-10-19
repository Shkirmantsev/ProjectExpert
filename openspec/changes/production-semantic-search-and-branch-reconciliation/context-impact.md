# Context impact — production-semantic-search-and-branch-reconciliation

Wiki, ADR, spec and gate impact accompanying the twelve PR slices of
plan §79. Behaviour lives in `specs/`; the technical shape is in
`design.md`; the executable checklist is in `tasks.md`. Knowledge IDs
below are placeholders to be bound to real stable IDs when the nodes are
authored.

## Knowledge to create

Reference = task block in `tasks.md`, plan section:

- `kb://production.semantic-binding` — Task PR3/PR4, plan §6, §9, §10,
  §101. Real EmbeddingGemma 2 and Qwen3-Embedding-0.6B bindings, pinned
  revisions, 512d/1024d profiles, float32/bfloat16 policy, text-only
  loading, query/document prompt policy, verified upstream URLs.
- `kb://production.runtime-configuration` — Task PR1, plan §2, §19, §20,
  §61, §63. Single configuration precedence chain, truthful capability
  report, no-silent-stub policy, `production` / `minimal` /
  `development` public modes, local `settings.json`.
- `kb://production.embedding-roles` — Task PR2, plan §7, §8. Role-aware
  embedding contract (query vs document, task, title), single underlying
  semantic contract, profile instruction version.
- `kb://production.semantic-index` — Task PR5, plan §24–§26. Persistent
  vector namespace per profile, reuse key, embed-misses-only, model
  switch namespace handling.
- `kb://production.usearch-generations` — Task PR6, plan §21–§23, §29,
  §30, §42. Real ANN backend, numeric key mapping, generation identity,
  atomic activation, rebuild-from-vector-store.
- `kb://production.retrieval-composition` — Task PR7, plan §27, §28. One
  composition root shared by UI, MCP, CLI and evaluation; end of the
  hash-scan UI path.
- `kb://production.branch-reconciliation` — Task PR8, plan §31–§42.
  Persisted previous-served snapshot diff, tombstones for removed data,
  working-tree fingerprints, version monitor, atomic swap, concurrency.
- `kb://production.source-discovery` — Task PR9, plan §43, §44. Default
  include/exclude sets, incremental discovery state.
- `kb://production.docling-pipeline` — Task PR10, plan §45–§50. Real
  document conversion, neutral mapping at the adapter boundary, hybrid
  chunking with tokenizer alignment, model-independent canonical
  knowledge.
- `kb://production.one-command-ux` — Task PR11, plan §15–§18, §55–§60,
  §83–§88. `start` / `models` commands, first-start wizard, bootstrap
  progress, product Makefile targets, admin retrieval settings, model
  switch state machine.
- `kb://production.release-gates` — Task PR12, plan §64–§74, §89–§92,
  §97. No-stub gate, real-model/ANN/Docling CI tiers, branch-switch and
  end-to-end acceptance, licence/SBOM verification.

## Knowledge to update

- `kb://architecture/platform-overview` — add the plan §102 topology
  (canonical → runtime → one model → vectors → ANN → hybrid → context)
  and the production stub-eradication status.
- `kb://architecture/system-overview` — replace "hashing default" and
  "USearch stub" descriptions with the real production path; document the
  three public startup modes.
- `kb://modules/embeddings` — role-aware contract, real bindings, model
  cache, device policy, profile revisions no longer `pinned-stub`.
- `kb://modules/retrieval` — unified composition root, generation-based
  dense index, semantic index service.
- `kb://modules/ingest` — repository source discovery, incremental state,
  real Docling pipeline.
- `kb://modules/runtime-store` — vector record authority, dense key
  store, runtime version state files.
- `kb://modules/mcp-server` — MCP consumes the same production retrieval
  runtime and stays fail-closed while readiness is false.
- `kb://invariants/v0.8` — add the plan §102 guarantees (no production
  stubs, no silent hashing fallback, no cross-model vector mixing, no
  stale previous-branch evidence, no model-switch Git churn).
- `openspec/CURRENT.md` — on adoption, add the twelve
  `2026-10-18-*` capabilities and update the affected accepted rows
  listed in `proposal.md` (orchestrator-owned; not edited by this
  change).

## Knowledge to review for staleness

- Any Wiki text claiming "EmbeddingGemma 2 / Qwen3 are not bound" or
  "USearch is a stub" — becomes stale as PR3/PR4/PR6 land.
- `kb://modules/security` and Control Plane notes about the UI retrieval
  path — the hash-scan composition disappears (PR7).
- One-click distribution quick-start docs that do not mention
  `make pi-up TARGET=… MODEL=…` (PR11).
- Any documentation implying implicit hashing fallback is acceptable in
  production.

## Affected implementation

Modules/paths (additions):

- `pi_platform/core/config/runtime_configuration.py`
- `pi_platform/adapters/config/runtime_configuration_resolver.py`
- `pi_platform/adapters/retrieval/embedding_model_factory.py`
- `pi_platform/adapters/retrieval/model_cache.py`
- `pi_platform/core/retrieval/semantic_index_service.py`
- `pi_platform/ports/git/version_snapshot.py`
- `pi_platform/core/sync/version_snapshot.py`
- `pi_platform/core/sync/version_monitor.py`
- `pi_platform/adapters/runtime/runtime_version_state.py`
- `pi_platform/adapters/runtime/dense_key_store.py`
- `pi_platform/core/ingest/repository_source_discovery.py`
- `pi_platform/core/control/retrieval_settings.py`
- `pi_platform/adapters/ui/retrieval_admin_routes.py`

Modules/paths (major updates):

- `pi_platform/ports/retrieval/embedding_model.py`
- `pi_platform/ports/retrieval/embedding_profile.py`
- `pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py`
- `pi_platform/adapters/retrieval/qwen3_embedding_model.py`
- `pi_platform/adapters/retrieval/hashing_embedding_model.py`
- `pi_platform/adapters/runtime/usearch_dense_index.py`
- `pi_platform/adapters/runtime/dense_index_backend.py`
- `pi_platform/adapters/runtime/sqlite_vector_record_store.py`
- `pi_platform/adapters/ui/composition.py`
- `pi_platform/mcp/context.py`
- `pi_platform/core/sync/reconcile.py`
- `pi_platform/core/sync/readiness.py`
- `pi_platform/adapters/pdf/docling_pdf_adapter.py`
- `pi_platform/adapters/pdf/docling_chunker.py`
- `pi_platform/cli/main.py`
- `pyproject.toml`, `Containerfile`, `docker-compose.yml`, `Makefile`
- `distribution/licenses/model-licenses.json`
- `distribution/licenses/dependency-inventory.json`

Primary symbols/interfaces:

- `EmbeddingModelPort`, `EmbeddingProfile`, `EmbeddingProfileRegistry`
  (`pi_platform/ports/retrieval/`)
- `DenseIndexPort` (`pi_platform/ports/runtime/dense_index.py`)
- `VectorRecordStorePort`, `VectorRecord`
  (`pi_platform/ports/runtime/vector_record_store.py`)
- `ReconcilePort`, `KnowledgeReadinessPort`, `RuntimeNotReadyError`
  (`pi_platform/ports/__init__.py`)
- `RuntimeCache`, `RuntimeCacheEntry` (`pi_platform/runtime/cache.py`)
- `ReconcileService` (`pi_platform/core/sync/reconcile.py`)
- new: `RuntimeConfigurationResolver`, `SemanticIndexService`,
  `ProjectVersionMonitor`, `RepositorySourceDiscovery`,
  `RuntimeVersionState`, `DenseKeyStore`

## ADR impact

Create:

- `kb://adr/production-no-silent-stubs` — component states
  (real-and-available / real-and-not-installed / disabled) and the
  production failure contract; hashing restricted to minimal/development.
- `kb://adr/production-embedding-role-contract` — why query and document
  roles are first-class and why prompt policy stays inside adapters.
- `kb://adr/production-generation-based-ann` — generation identity,
  atomic activation and rebuild-from-vector-store.
- `kb://adr/production-snapshot-reconciliation` — previous-served
  snapshot as the comparison baseline; tombstones; working-tree
  fingerprints.

Update:

- `kb://adr/0009-embedding-model-selection` — selected production models
  are EmbeddingGemma 2 (512d) and Qwen3-Embedding-0.6B (1024d) with
  immutable revisions per plan §101.
- `kb://adr/0008-embedded-storage-selection` — production dense backend
  is real USearch; flat remains test/small fallback.
- `kb://adr/0004-ports-and-adapters-extension-style` — confirm the
  slices add adapters behind existing ports without a new abstraction
  layer.

## Acceptance criteria

- [ ] Relevant Wiki pages reflect the shipped behaviour of each merged
      slice; stale stub claims are removed.
- [ ] Generated local context index was refreshed after Wiki updates.
- [ ] Links and stable knowledge IDs validate
      (`kb://production.*` placeholders resolved to real IDs).
- [ ] Spec/implementation mismatches are resolved or explicitly
      documented (the four reconciliation notes in `proposal.md`).
- [ ] `openspec/CURRENT.md` lists the twelve adopted
      `2026-10-18-*` capabilities (orchestrator action at adoption).
- [ ] `distribution/licenses/model-licenses.json` contains no
      `pinned-stub` revision or status for production capabilities.
- [ ] Each PR slice records its focused verification result and runs
      `python harness.py check` before handoff.