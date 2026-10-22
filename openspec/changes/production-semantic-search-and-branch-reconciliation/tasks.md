# Tasks — production-semantic-search-and-branch-reconciliation

Ordered by plan §79–§80. This checklist distinguishes implementation from
executed acceptance. A test module existing, or a model-free suite passing,
does not prove real-model, PDF inference, container, or semantic-quality
acceptance. Unchecked items remain required even when related code exists.
The original plan's suggested filenames were not all created: the mappings
below name the actual implementation and test modules instead.

## PR1 — Production configuration and truthfulness

- [x] Implement configuration types and precedence in
  `pi_platform/adapters/config/runtime_configuration_resolver.py`; share local
  model selection through `pi_platform/core/control/retrieval_settings.py`.
- [x] Expose production/minimal/development profiles and reject implicit hashing
  or absent real production dependencies. Route CLI status through resolved
  configuration and report unavailable components truthfully.
- [ ] Verify every entry point preserves CLI → environment → local settings →
  project defaults → built-in precedence, including the running HTTP/MCP surfaces.
- [ ] Run focused configuration/capability checks and the final harness gate.
  Actual coverage: `tests/test_runtime_configuration_resolver.py`,
  `tests/test_native_generation_recovery.py` (initial project defaults and live
  operator override precedence), `tests/test_production_capability_gate.py`,
  `tests/test_production_packaging.py`, `tests/test_one_command_production_ux.py`,
  `tests/test_v2_production_wiring.py`. These replace the prescribed separate
  runtime-configuration/startup-profile/capability-truthfulness test files.

## PR2 — Query/document embedding roles

- [x] Add role/task/title requests and convenience wrappers in
  `pi_platform/ports/retrieval/embedding_model.py`; include instruction policy in
  `pi_platform/ports/retrieval/embedding_profile.py` identity.
- [x] Index documents with DOCUMENT role and embed each dense query once with
  QUERY role. Keep hashing explicit to minimal/test use.
- [ ] Verify role/task behavior across both real models and all callers.
  Actual coverage: `tests/test_repository_indexing_runtime.py`
  (`test_dense_query_is_embedded_once_with_query_role`),
  `tests/test_embedding_profile_identity.py`,
  `tests/test_hashing_embedding_fallback.py`, and real adapter tests below.

## PR3 — Real EmbeddingGemma 2

- [x] Implement the real adapter, immutable revision, 512d normalization and
  role-aware prompts in
  `pi_platform/adapters/retrieval/embeddinggemma2_embedding_model.py`.
  Factory/cache/device behavior resides in
  `pi_platform/adapters/retrieval/embedding_model_factory.py`,
  `pi_platform/adapters/config/runtime_device.py`, and CLI model commands;
  there is no separate prescribed `model_cache.py` implementation.
- [ ] Complete real-weight acceptance: load the pinned snapshot, validate
  numerical policy, dimensions, normalization, role/task prompts, batching,
  repeatability, offline restart and semantic ranking (plan §65, §93).
- [x] Execute unskipped real-weight tests in the installed modern runtime:
  `PI_RUN_MODEL_TESTS=1 python -m unittest tests.test_embeddinggemma2_embedding_model tests.test_qwen3_embedding_model -v`
  passed 19 tests (parent evidence). `tests/test_production_end_to_end.py` also
  passed the real offline Gemma → Qwen → Gemma retrieval story. Comprehensive
  multilingual evaluation and all numerical/device policies remain separate
  acceptance above.

## PR4 — Real Qwen3 embedding 0.6B

- [x] Implement the pinned real 1024d adapter, query-only instruction and
  normalization in `pi_platform/adapters/retrieval/qwen3_embedding_model.py`.
- [ ] Complete real-weight batching/padding, role, repeatability, offline restart
  and semantic-ranking acceptance (plan §65, §93). A successful single 1024d,
  norm-one probe is useful evidence but does not complete this item.
- [x] Execute the real Qwen adapter tests as part of the 19-test installed-runtime
  run above; the native real-model end-to-end switch test also passed (parent
  evidence). This does not certify every multilingual/device/long-input case.

## PR5 — Persistent semantic indexing

- [x] Implement vector reuse, profile namespaces, count validation, removed chunk
  handling and deterministic generations in
  `pi_platform/core/retrieval/semantic_index_service.py`.
- [x] Connect actual repository parsing, persisted source/chunk cache and SQLite
  vectors through `pi_platform/core/orchestration/repository_indexing.py`.
- [x] Verify minimal-profile restart reuse and old-source removal in
  `tests/test_repository_indexing_runtime.py` and
  `tests/test_runtime_version_lifecycle.py`. UX profile-switch contracts use
  explicit injected embeddings, not real Gemma/Qwen weights.
- [x] Complete the real Gemma → Qwen → Gemma reuse/no-Git-churn story in
  `tests/test_production_end_to_end.py`: parent recorded PASS, 17.8 seconds,
  offline cached weights, native USearch, live service/MCP ranked-result equality,
  refund semantic ranking and switch-back embedded_count=0. Additional unit coverage is
  `tests/test_semantic_index_service.py`,
  `tests/test_embedding_profile_identity.py`, and
  `tests/test_one_command_production_ux.py`; there are no separate prescribed
  vector-reuse-key or model-switch-namespace test modules.

## PR6 — Real USearch

- [x] Implement native USearch, persistent numeric/string key mapping,
  generation metadata and atomic file replacement in
  `pi_platform/adapters/runtime/usearch_dense_index.py`. `DenseKeyStore` lives
  in this module, not a separate prescribed module.
- [x] Run the existing 28 USearch tests with the native package installed
  (`tests/test_usearch_dense_index.py`; parent verification evidence).
- [x] Verify native generation loading without rewriting its file, corrupted
  native/metadata/key-sidecar recovery from SQLite without document inference,
  profile/dimension/count validation and sample-query rejection before rename
  in `tests/test_native_generation_recovery.py`. These use controlled embeddings
  with actual USearch 2.26.5 and are not model-quality evidence.
  Additional unit coverage: `tests/test_semantic_index_service.py` and
  `tests/test_persisted_runtime_snapshot.py`. No separate prescribed
  dense-key-store/index-generation/atomic-activation test files exist.
- [x] Record a bounded native ANN recall benchmark against exact cosine:
  `test_seeded_native_ann_recall_against_exact_cosine` uses seed 20261020,
  1,000 normalized 64d vectors and 50 held-out queries, top 10,
  HNSW connectivity/expansion 32/200/100. USearch 2.26.5 achieved
  Recall@10 0.998 against the explicit 0.90 floor (retain nine of ten true
  neighbors on average); mean query latency was 0.170 ms. Evidence:
  `/tmp/projectexpert-native-ann-recall.json`. This calibrates this bounded
  synthetic ANN configuration, not semantic-model or production-scale quality.

## PR7 — Unified retrieval composition

- [x] Use `pi_platform/core/orchestration/retrieval_composition.py` for actual
  source indexing and the published retrieval proxy shared by UI and MCP.
  Remove live UI hash-scan composition; query embedding occurs once.
- [x] Verify actual minimal-profile retrieval and source-removal behavior in
  `tests/test_runtime_version_lifecycle.py`.
- [x] Verify ranked retrieval equality through the live UI service and MCP handler
  using both real models in `tests/test_production_end_to_end.py` (parent PASS).
- [ ] Complete result equivalence with CLI and evaluation, including metadata, exact identifiers, selection, graph
  support and context assembly. Actual mapped modules:
  `tests/test_production_retrieval_composition.py`,
  `tests/test_repository_indexing_runtime.py`,
  `tests/test_mcp_retrieval_output.py`, `tests/test_mcp_context_factory.py`,
  `tests/test_multi_stage_order.py`.

## PR8 — Persisted snapshots and branch reconciliation

- [x] Persist successful active/manifest/source state atomically in
  `pi_platform/core/sync/version_snapshot.py`. No separate prescribed
  port/runtime-version-state files were needed.
- [x] Implement portable 2–5 second HEAD/branch/content polling in
  `pi_platform/core/sync/version_monitor.py`, including actual canonical graph
  JSONL shards. Serialize mutation with project locks; fail closed while
  bootstrapping/refreshing; retry failed candidates and edits during indexing.
- [x] Validate actual minimal A → B additions/removals → A retrieval, vector
  reuse, dirty-content detection, HTTP availability during failure and
  persisted-failure readiness in `tests/test_runtime_version_lifecycle.py`.
- [ ] Complete all fifteen plan §68 scenarios as real refresh/retrieval tests,
  particularly graph-edge changes, concurrent indexing/query, process crashes,
  and corrupted active native indexes. Coverage distinctions are listed below.
- [x] Construct candidate graph generations from active parsed/canonical/runtime
  records, return actual graph node IDs for snapshot publication, and verify
  changed edges/removed nodes with
  `tests/test_repository_indexing_runtime.py::RepositoryIndexingRuntimeTests.test_graph_edge_changes_publish_new_graph_without_old_entities`.
- [ ] Complete graph/support reconciliation proof across a real Git branch switch
  and all consumer query paths; graph-construction and detector tests are partial.
- [x] Prove switch-back loads the valid native generation without file rewrite or
  document re-embedding; missing snapshot recovery also reuses the valid cache
  (`tests/test_native_generation_recovery.py`).
- [x] Preserve a coherent previous snapshot across a real child-process exit
  after a manifest mirror write and across legacy-format migration failure;
  `snapshot.json` is the authoritative atomic bundle, with backward-compatible
  three-file projections. Regression: `SnapshotBundleCrashTests`.
- [ ] Complete plan §70 duration/deletion metrics and remaining process-crash
  boundaries, rather than treating a single injected failure as the full matrix.
- [x] Execute the existing snapshot/lifecycle suites: 20 snapshot tests and the
  lifecycle/distribution runs recorded below passed. Actual mapped command:
  `python -m unittest tests.test_persisted_runtime_snapshot tests.test_runtime_version_lifecycle tests.test_content_address_cross_branch -v`.
  The content-address module is an additional mapped regression; its execution
  is not included in the lifecycle run counts below.

## PR9 — Incremental source discovery

- [x] Implement includes/excludes, content fingerprints and persisted inventory
  in `pi_platform/core/ingest/repository_source_discovery.py`; feed actual
  sources into the indexing pipeline.
- [x] Verify actual added/removed sources and unchanged vector reuse through
  `tests/test_runtime_version_lifecycle.py` and
  `tests/test_one_command_production_ux.py`.
- [x] Persist actual aggregated model-independent retrieval-text hashes returned
  by the indexing pipeline into discovery state; native bootstrap regression
  checks the persisted Markdown source hash is populated.
- [ ] Complete parser-version invalidation proof and prove unchanged sources
  are not reparsed.
  Actual focused coverage: `tests/test_repository_source_discovery.py`,
  `tests/test_repository_indexing_runtime.py`; no separate prescribed
  incremental-discovery-state test file exists.

## PR10 — Real Docling

- [x] Implement real converter and neutral PDF projection, selective OCR,
  provenance, tables/figures and real tokenizer-aware HybridChunker adapters.
  Actual files: `pi_platform/adapters/pdf/docling_pdf_adapter.py`,
  `pi_platform/adapters/pdf/docling_chunker.py`,
  `pi_platform/adapters/pdf/real_docling.py`.
- [x] Add pinned production/document dependencies and explicit model-asset
  inventory checks. Dependency installation is separate from inference proof.
- [ ] Complete real native/scanned/mixed PDF, tables/figures/captions,
  multipage-table header preservation, 100/600-page bounded-memory and resume
  acceptance (plan §71, §96), with model assets available.
- [x] Run the unskipped real conversion suite:
  `PI_RUN_PDF_TESTS=1 python -m unittest tests.test_docling_production_binding -v`.
  Additional actual coverage: `tests/test_docling_pdf_adapter.py`,
  `tests/test_real_docling_binding.py`, `tests/test_pdf_production_mapping.py`,
  `tests/test_document_graph_roundtrip.py`, `tests/test_ingestion_job_store.py`,
  `tests/test_pdf_batch_resume.py`. Tier2 markers and injected converters do not
  by themselves prove real Docling inference. There is no separate prescribed
  Docling-chunker test file.

## PR11 — One-command UX

- [x] Implement serving `start` (explicit `--no-serve` for one-shot bootstrap),
  model commands, early HTTP, progress, setup and real administrative workers.
  MCP and HTTP retrieval remain closed before successful publication.
- [x] Keep settings in runtime cache; preserve selected model/device on restart;
  serialize monitor and administrative reindex workers.
- [x] Implement product Makefile/Compose/container surfaces and model-cache
  volume. Static packaging checks are not a built-image acceptance result.
- [x] Run actual mapped UX/lifecycle/admin/distribution tests:
  `python -m unittest tests.test_one_command_production_ux tests.test_runtime_version_lifecycle tests.test_retrieval_admin_routes tests.test_phase_9_distribution -q`
  passed 72 tests before the additional JSONL regression; the six monitor tests
  including JSONL detection subsequently passed separately.
  Additional mapped modules are `tests/test_first_start_wizard.py`,
  `tests/test_retrieval_settings.py`, `tests/test_production_packaging.py`,
  `tests/test_oci_pipeline_and_standalone_container.py`.
- [ ] Complete fresh-machine Docker + real Gemma first run/restart, Qwen switch,
  switch-back and live branch switch with no stale evidence (plan §72, §99).

## PR12 — Production release gates

- [x] Implement inventory-only versus strict runtime capability checks in
  `pi_platform/core/orchestration/production_capability_gate.py` and its CLI.
  Actual tests: `tests/test_production_capability_gate.py`.
- [x] Add `.github/workflows/verify-production-runtime.yml` with manual/release,
  dev push and scheduled triggers, actual Docling conversion tests,
  `tests/test_production_end_to_end.py`, and a production container build.
- [ ] Execute the complete heavy tier in CI, including all branch scenarios,
  actual PDF fixture breadth and offline container restart; implemented workflow
  wiring does not certify a successful production release.
- [ ] Build and run the real production image, verify its installed dependency
  closure, licence/SBOM/NOTICE, model cache persistence and offline deployment.
  Actual mapped packaging/licence coverage: `tests/test_production_packaging.py`,
  `tests/test_oci_pipeline_and_standalone_container.py`,
  `tests/test_supply_chain_gate.py`, `tests/test_phase_10_quality_gates.py`.
  There are no separate prescribed first-run/offline/licence-SBOM test files.
- [x] Run real Gemma and Qwen semantic evaluation against dated golden queries;
  record Recall@5/@10, MRR, NDCG, protected retention, evidence coverage,
  latency/memory/index size (plan §91). `tests/test_retrieval_benchmark.py`
  validates benchmark machinery; it is not a two-model quality result.
- [x] Run `python harness.py check` on the final integrated tree and record the
  exact PASS/FAIL/NOT RUN results and remaining acceptance gaps in checkpoint.

## Plan §68 coverage matrix

“Detector” means change recognition only; “contract” means injected collaborators.
Neither is a substitute for a native production refresh/retrieval acceptance run.

| Scenario | Actual current coverage | Remaining acceptance |
|---|---|---|
| A → B identical knowledge | `VersionMonitorTests.test_branch_and_dirty_content_matrix` detector | Reused native generation + returned corpus |
| A → B added chunk | Actual minimal refresh in lifecycle/one-command tests | Real model/native ANN integration |
| A → B modified chunk | Detector matrix; semantic-index changed-text contract | Actual branch refresh/query, dependency invalidation |
| A → B removed chunk | Actual minimal refresh/query + snapshot tombstone contract | Native ANN and dependent graph/support evidence |
| A → B changed graph edge | JSONL detector + actual candidate graph removed-edge/node regression | Git checkout and stale support removal across consumers |
| A → B changed source code | One-command added source; monitor modified source detector | Modified-code retrieval/version integration |
| B → A return | Actual minimal Git retrieval + native corpus generation reload without rewrite/inference | Combined real-model/native Git-switch acceptance |
| Same HEAD + dirty working tree | Multiple dirty-content detector ticks | Refreshed retrieval/version assertion |
| Dirty → clean | Detector matrix uses Git restore | Refreshed retrieval/version assertion |
| Clean → dirty | Detector matrix | Refreshed retrieval/version assertion |
| Switch while model indexing | Callback edits source; bootstrap rejects mismatched version | Actual checkout during blocked model/native generation |
| Switch while query arrives | HTTP returns 503 when readiness false | Concurrent checkout/in-flight retrieval under active worker |
| Crash during reconciliation | Native rename/sample validation rejection; real process exit after manifest mirror; legacy migration failure | Remaining publication/index process-kill boundaries |
| Corrupted active index | Actual corrupt native file/metadata/keys and wrong profile/count/dimension rebuild without inference | Combined live server corruption/restart |
| Missing previous runtime snapshot | Native bootstrap recovers existing valid generation without inference | Combined real-model server restart acceptance |

## Recorded verification limits

The lifecycle worker executed an expanded 108-test run covering lifecycle,
snapshots, one-command UX, phase9 distribution/launch and standalone container
contracts: PASS, one Docker smoke test skipped. A later focused run passed
72 tests. These used explicit minimal profiles/injected contract embeddings
where appropriate; they do not certify production model or container behavior.
The installed native USearch 28-test run, both real adapter suites (19 tests),
and the real offline Gemma → Qwen → Gemma end-to-end test (17.8 seconds) were
reported PASS by the parent. The latest model-free/native regression command
passed 111 tests in 9.5 seconds, including actual USearch recovery, subprocess
snapshot-crash, operator override and source inventory persistence checks.
The subsequent native/snapshot/monitor run passed 61 tests in 9.2 seconds,
including the seeded ANN recall benchmark (0.998 against a 0.90 floor).
Full PDF fixture breadth, a built Docker image, all fifteen combined branch
scenarios and multilingual semantic-quality acceptance remain unchecked until
their evidence is recorded.


## Integrated runtime acceptance recorded 2026-10-21

Real CPU Gemma→Qwen→Gemma plus committed Git A→B→A (including removed
canonical graph nodes), UI/MCP hit equality, unchanged source bytes, zero
switch-back inference and loaded native generation: PASS. Both model suites
passed19 tests without skipped inference. Strict production capability gate
passed six checks. Two-model multilingual golden fixture passed; measured
metrics and limitations are retained in
`docs/verification/production-runtime-2026-10-21.json`.

Actual native/table/figure/scanned/mixed/two-page-table conversion passed;
PDF→realGemma→USearch integration passed. Actual600-page proof passed in734.533s,
max16-page windows, peakRSS2.13GiB. Pending the final combinedsuite check, these
are individual executed proofs, not a CI or production-container claim.

Production license policy intentionally blocks12 coordinates; see
`docs/PRODUCTION_LICENSE_REVIEW.md`. Docker production build/start and remote
heavy CI are NOT RUN. Broad combined15-scenario/performance/airgap requirements
remain unchecked. No current spec was silently weakened to mark these complete.


Final realPDF combinedsuite:6 tests PASS211.955s, no skipped inference. Shared
runtime CLI `eval-retrieval --target` now uses the published repository pipeline;
28 evaluation/repository/standalone tests PASS. Generic fixture evaluation stays
explicit and distinct. See production reconciliation report for complete limits.


Final integrated `python3 harness.py check`: PASS1429 unittest invocations;
13 optional integration skips in core lane, separate realmodel/PDF checks
executed unskipped. Wiki/OpenSpec/manifest/MCP checks PASS. Final source and
container release limits are recorded in docs/PRODUCTION_RECONCILIATION_STATUS.md.
