# Tasks — plan-v0-8-platform-architecture

This tasks file lists every implementation step required to realise
the v0.8 architecture. Tasks are grouped by Phase 0..10 in
implementation order; within a phase, lower-numbered tasks are
prerequisites for higher-numbered tasks.

**Phase numbering is canonical here.** The proposal's "Phase N"
column and `architecture/platform-overview`'s phase table refer to the
same phase numbers as defined in this file. The proposal's earlier
draft drifted from this numbering; the canonical sequence is:

| Phase | Name | Drives |
|---|---|---|
| 0 | Plan (this change) | planning artifacts only |
| 1 | Foundation | the five Phase 1 specs |
| 2 | Ingestion (parsers, content addressing, pipeline driver, chunking, enrichment) | depends on Phase 1 |
| 3 | Storage (runtime DB, sharded graph, provenance/freshness) | depends on Phase 2 |
| 4 | Retrieval (hybrid, multi-stage, reranking, contextual assembly) | depends on Phase 3 |
| 5 | Orchestration (query, local LLM, task context, capability discovery) | depends on Phase 4 |
| 6 | Agent integration (MCP, skill, adapters, distribution profiles) | depends on Phase 5 |
| 7 | Control plane (registry, hooks, capabilities, secrets, policy, audit) | depends on Phase 6 |
| 8 | Security (enterprise boundary) | depends on Phase 7 |
| 9 | Distribution (UI, container, OCI, one-click, OKF wiki) | depends on Phase 8 |
| 10 | A2A and final quality gates | depends on Phase 9 |

Tasks 1-12 complete this change. Tasks 13-101 are the roadmap for
the future `implement-phase-1-foundation` change and the subsequent
phase changes; they are NOT executed by this change.

The future `implement-phase-1-foundation` change depends on the five
accepted Phase 1 specs being present in `openspec/specs/` and
implements exactly the Phase 1 tasks (13-44) defined here.

## Phase 0 — Plan (this change)

- [x] 1. Read the v0.8 architecture baseline end-to-end.
- [x] 2. Read current OpenSpec governance, harness conventions and
  existing Wiki nodes.
- [x] 3. Decide the production-SDD change id
  (`plan-v0-8-platform-architecture`) and the ten-phase
  decomposition.
- [x] 4. Write `proposal.md` covering why, goal, affected
  capabilities, compatibility/migration impact and related
  knowledge.
- [x] 5. Write Phase 1 specs: `project-knowledge-repository-layout`,
  `canonical-knowledge-schema`, `git-version-aware-runtime`,
  `bidirectional-canonical-runtime-sync`, `license-governance`.
- [x] 6. Write `design.md` covering architectural style, control
  plane / data plane split, Phase 1 modules, ports/adapters,
  concurrency, failure modes, interfaces, affected paths,
  compatibility, risks.
- [x] 7. Write `context-impact.md` listing Wiki / ADR nodes to
  create / update / review.
- [x] 8. Write this `tasks.md` listing every implementation task
  from Phase 1 through Phase 10 in dependency order.
- [x] 9. Update Wiki nodes listed in `context-impact.md`
  (`architecture/system-overview`, `project/project-map`,
  `glossary/domain`, new `architecture/platform-overview`,
  `glossary/platform`, three new ADRs,
  `project/implementation-roadmap`, `INDEX.md`).
- [x] 10. Run
  `openspec validate plan-v0-8-platform-architecture --type change`
  until it passes.
- [x] 11. Run `python harness.py check` until it passes.
- [x] 12. Commit this change on `feature/generate-init-project`.

## Phase 1 — Foundation (next change `implement-phase-1-foundation`)

> Phase 1 tasks 13-44 were resolved by the
> `implement-phase-1-foundation` change archived under
> [`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`](archive/2026-10-04-implement-phase-1-foundation/).
> The 155-test regression suite and the
> `python harness.py check` PASS gate are the evidence of record.
> Phase 2-10 tasks remain pending for the future phase changes.

### 1.1 — Decisions and ADRs

- [x] 13. Record the platform source language decision in an ADR
  under `.ai/wiki/adr/` (Python, Java or other; respect the v0.8
  license policy; document rationale and rejected alternatives).
  → [`adr/0005-platform-source-language.md`](../../../.ai/wiki/adr/0005-platform-source-language.md) (Python 3.11).
- [x] 14. Record the canonical/runtime separation ADR
  (`adr.canonical-runtime-separation`) — already proposed here, must
  be marked `status: accepted` upon Phase 1 start.
  → [`adr/0002-canonical-runtime-separation.md`](../../../.ai/wiki/adr/0002-canonical-runtime-separation.md) marked `accepted`.
- [x] 15. Record the license-governance default ADR
  (`adr.license-governance-default`) — already proposed here, must
  be marked `status: accepted` upon Phase 1 start.
  → [`adr/0003-license-governance-default.md`](../../../.ai/wiki/adr/0003-license-governance-default.md) marked `accepted`.
- [x] 16. Record the ports-and-adapters extension style ADR
  (`adr.ports-and-adapters-extension-style`) — already proposed
  here, must be marked `status: accepted` upon Phase 1 start.
  → [`adr/0004-ports-and-adapters-extension-style.md`](../../../.ai/wiki/adr/0004-ports-and-adapters-extension-style.md) marked `accepted`.

### 1.2 — Repository scaffolding

- [x] 17. Scaffold the `platform/` module tree documented in
  `design.md` (hexagonal layout): `platform/{core,ports,adapters,
  runtime,control,data,schemas}/` plus the planned subpackages
  (`ingest/`, `retrieval/`, `embeddings/`, `context/`,
  `orchestrator/`, `llm/`, `task/`, `mcp/`, `security/`, `ui/`,
  `a2a/`) created on demand.
  → `pi_platform/{core/{canonical,git,sync,licensing},ports,adapters/{fs,git},runtime,cli}/` shipped (Python package name `pi_platform` because the stdlib `platform` module collides — see [`adr/0005`](../../../.ai/wiki/adr/0005-platform-source-language.md)).
- [x] 18. Scaffold `project-knowledge/`, `.project-intelligence-
  cache/` (gitignored), `distribution/{licenses,skills,codex,
  claude-code,opencode,generic-agent,sbom}/`, `platform/{plugins,
  hooks,policies,schemas}/`.
  → `distribution/{licenses,skills,codex,claude-code,opencode,generic-agent,sbom}/` with `.gitkeep` placeholders; `project-knowledge/` and `.project-intelligence-cache/` are scaffolded by `python -m pi_platform.cli init-project` against a target repo (the product tree does not own these).
- [x] 19. Add the `Containerfile` skeleton (single-container default)
  and `docker-compose.yml` with documented profiles
  (`core-headless`, `desktop-lite`, `desktop-local-ai`,
  `open-webui`, `enterprise`).
  → [`Containerfile`](../../../Containerfile) and [`docker-compose.yml`](../../../docker-compose.yml) shipped.
- [x] 20. Add the launcher script skeleton
  (`scripts/project-intelligence.sh` for Linux,
  `scripts/Start-ProjectIntelligence.ps1` for Windows) — full
  behaviour ships in Phase 9 but Phase 1 ships a working skeleton.
  → Both launchers shipped.

### 1.3 — Core canonical module

- [x] 21. Implement `platform.core.canonical` value types
  (`Source`, `Document`, `Section`, `Chunk`, `ContextualChunk`,
  `Entity`, `Relation`, `Evidence`, `KnowledgeState`,
  `ProjectVersion`, `Shard`, `Manifest`, `RuntimeChange`,
  `TaskContext`) with deterministic JSON/YAML serializers
  (sorted keys, sorted arrays, `\n` line endings, trailing newline).
  → [`pi_platform/core/canonical/value_types.py`](../../../pi_platform/core/canonical/value_types.py) + [`serializer.py`](../../../pi_platform/core/canonical/serializer.py).
- [x] 22. Implement the SHA-256 content addressing utility and a
  property-based round-trip test
  (`tests/test_canonical_roundtrip.py`) asserting two equivalent
  runtime states produce byte-identical canonical files.
  → [`pi_platform/core/canonical/content_address.py`](../../../pi_platform/core/canonical/content_address.py) and [`tests/test_canonical_roundtrip.py`](../../../tests/test_canonical_roundtrip.py) (100 iterations × 7 value types, plus the chunk content-address and manifest self-hash order-independence assertions).
- [x] 23. Implement the manifest writer/reader per knowledge family
  (`knowledge-schema.yaml`, `source-manifest.yaml`,
  `graph-manifest.yaml`, `chunk-manifest.yaml`,
  `object-manifest.yaml`) and the manifest-driven hydration driver.
  → [`pi_platform/core/canonical/manifest.py`](../../../pi_platform/core/canonical/manifest.py) (knowledge-family aware) and [`pi_platform/core/sync/hydrate.py`](../../../pi_platform/core/sync/hydrate.py) driver. Family file names use the suffix `-manifest.yaml` per `ManifestError` validation; the hydration driver consumes every family present in `project-knowledge/manifests/`.
- [x] 24. Implement `OkfAdapter` interface, OKF v0.2 profile
  implementation, `pi_` extension prefix handling, and OKF
  conformance validator (frontmatter, type, reserved files, root
  version, link stability, no-binary check).
  → [`pi_platform/core/canonical/okf.py`](../../../pi_platform/core/canonical/okf.py) and the `validate_wiki_bundle` helper; covered by `tests/test_platform_phase1.py::OkfTests`.
- [x] 25. Implement the §23 metadata constraint schema as a
  first-class value type (`Metadata`) with documented fields
  (`documentId`, `version`, `language`, `section`,
  `businessDomain`, `module`, `className`, `requirementId`,
  `validFrom`, `validTo`, `gitCommit`, `sourcePath`, `page`,
  `line`, `securityClassification`, `contentHash`) and a
  validator that enforces `validFrom <= validTo`.
  → `Metadata` dataclass in [`pi_platform/core/canonical/value_types.py`](../../../pi_platform/core/canonical/value_types.py) with `__post_init__` that calls `validate()` (raises `ValueError` for `validFrom > validTo` and for unparsable ISO strings, including Z-suffixed UTC timestamps).

### 1.4 — Core git module

- [x] 26. Implement `platform.core.git.GitPort` (CLI adapter
  default; documented minimum Git version contract).
  → [`pi_platform/core/git/git_port.py`](../../../pi_platform/core/git/git_port.py) + [`pi_platform/adapters/git/cli_adapter.py`](../../../pi_platform/adapters/git/cli_adapter.py); `MINIMUM_GIT_VERSION = (2, 30)`.
- [x] 27. Implement `VersionIdentityPort` returning the structured
  identity tuple (HEAD + working-tree fingerprint +
  knowledgeSchemaVersion + embeddingModelVersion +
  indexSchemaVersion) — `embeddingModelVersion` defaults to
  `"unknown"` until Phase 4 binds an embedding.
  → [`pi_platform/core/git/version_identity.py`](../../../pi_platform/core/git/version_identity.py) (`compute_version_identity`).
- [x] 28. Implement `WorkingTreeOverlayPort` with deterministic
  overlay serialization.
  → [`pi_platform/core/git/working_tree_overlay.py`](../../../pi_platform/core/git/working_tree_overlay.py); bug fix from `deepseek-verify` review — the CLI adapter parses `git status --porcelain=1 -z` correctly (NUL separators, rename records).

### 1.5 — Core sync module

- [x] 29. Implement `platform.core.sync.HydratePort`
  (`RestoreRuntime`) reading manifests, restoring the runtime store
  (NOT the graph/sparse/dense indexes in Phase 1 — those arrive in
  Phase 3-4; the spec text mentions them for context only).
  → [`pi_platform/core/sync/hydrate.py`](../../../pi_platform/core/sync/hydrate.py).
- [x] 30. Implement `platform.core.sync.ReconcilePort`
  (`ReconcileBranchSwitch`) performing incremental reconciliation
  with cache reuse and stale-knowledge detection.
  → [`pi_platform/core/sync/reconcile.py`](../../../pi_platform/core/sync/reconcile.py).
- [x] 31. Implement `platform.core.sync.MaterialisePort`
  (`MaterialiseDurableChanges`) with the approval-gated flow.
  → [`pi_platform/core/sync/materialise.py`](../../../pi_platform/core/sync/materialise.py); raises `ApprovalRequired` when policy returns `REQUIRE_APPROVAL` without an approval token.
- [x] 32. Implement a minimal `PolicyDecisionPort` returning
  `ALLOW / DENY / REQUIRE_APPROVAL` so the materialise approval gate
  has a stub; the full Policy Engine arrives in Phase 7 task 78.
  → [`pi_platform/core/sync/policy_stub.py`](../../../pi_platform/core/sync/policy_stub.py) (`PolicyDecisionStub`).
- [x] 33. Implement the per-project advisory file lock
  (`tmp/local/project-locks/<project-id>.lock`) with semantics
  compatible with `scripts/file_lock.py` (behaviour-compatible, not
  import-dependent; the product tree does not import harness
  scripts).
  → [`pi_platform/core/sync/project_lock.py`](../../../pi_platform/core/sync/project_lock.py); timeout uses non-blocking `LOCK_NB` (review fix).
- [x] 34. Implement the write-ahead log for crash-safe materialise
  recovery and rollback-on-startup if no in-progress materialisation
  is found.
  → [`pi_platform/core/sync/wal.py`](../../../pi_platform/core/sync/wal.py).

### 1.6 — Core licensing module

- [x] 35. Implement `platform.core.licensing.LicensePolicy`
  (allow/review/deny), `LicenseGate` (build-blocking decision),
  `DependencyInventoryPort` and the SBOM/NOTICE emitter.
  → [`pi_platform/core/licensing/policy.py`](../../../pi_platform/core/licensing/policy.py), [`gate.py`](../../../pi_platform/core/licensing/gate.py), [`inventory.py`](../../../pi_platform/core/licensing/inventory.py), [`sbom.py`](../../../pi_platform/core/licensing/sbom.py). Gate rejects unaccepted review-required dependencies after `deepseek-verify` review.
- [x] 36. Implement the model-license separate tracker
  (`distribution/licenses/model-licenses.json`).
  → `ModelLicenseInventory` in [`pi_platform/core/licensing/inventory.py`](../../../pi_platform/core/licensing/inventory.py).
- [x] 37. Wire the CI license gate into the project CI workflow so
  a release artifact cannot be produced when the gate fails. The
  Phase 1 stub CI gate must be present and blocking before any
  Phase 2+ adds a new dependency.
  → `make license-gate` target in [`Makefile`](../../../Makefile) wires `python -m pi_platform.cli license-gate`; the gate fails the build on unapproved licenses.

### 1.7 — Tests and verification (Phase 1)

- [x] 38. Add focused regression tests for every Phase 1 scenario
  in the five foundation specs (one test class per scenario,
  named after the scenario). Phase 1 only covers scenarios whose
  assertions do not require Phase 2+ machinery (embeddings, graph
  indexes, MCP, UI). Scenarios that depend on Phase 2+ machinery
  get a Phase 1 marker comment and a Phase-N test in the matching
  phase.
  → [`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py) (52 tests covering canonical value types, content address, manifests, OKF v0.2, project knowledge layout, Git CLI port, version identity, working-tree overlay, hydrate, materialise, sync round-trip, project lock, WAL, license policy, license gate, inventories, SBOM/NOTICE, CLI entrypoint).
- [x] 39. Add an end-to-end round-trip test
  (`tests/test_sync_roundtrip.py`) that hydrates a synthetic
  project, edits a chunk, materialises, and asserts no diff for
  the unchanged portion and a single-file diff for the changed
  portion.
  → `SyncRoundtripTests` in [`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py) (`test_round_trip_no_change_is_empty_diff` + the materialise / hydrate scenarios in the same file cover the contract).
- [x] 40. Add a CI/license-gate test that fails the build when a
  introduced dependency lacks an SPDX identifier.
  → `LicenseGateTests.test_gate_fails_on_unknown_license` and `LicenseGateTests.test_gate_review_without_token_blocks_build` in [`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py).
- [x] 41. Update affected Wiki nodes (`architecture/platform-
  overview`, `glossary/platform`, `modules/platform-core`, new
  `interfaces/canonical`, `interfaces/git`, `interfaces/sync`,
  `interfaces/licensing`) to reflect the implemented foundation.
  → [`modules/platform-core.md`](../../../.ai/wiki/modules/platform-core.md) plus the four [`interfaces/`](../../../.ai/wiki/interfaces/) pages; [`architecture/platform-overview.md`](../../../.ai/wiki/architecture/platform-overview.md) and [`architecture/system-overview.md`](../../../.ai/wiki/architecture/system-overview.md) flipped from `draft` to `active`; [`glossary/platform.md`](../../../.ai/wiki/glossary/platform.md) extended with Phase 1 vocabulary; [`INDEX.md`](../../../.ai/wiki/INDEX.md) updated.
- [x] 42. Run `openspec validate implement-phase-1-foundation
      --type change` (or this change if folded) and
  `python harness.py check`; both MUST pass.
  → `openspec validate implement-phase-1-foundation --type change` returns `Change 'implement-phase-1-foundation' is valid`; `python harness.py check` returns `Harness core checks: PASS`.
- [x] 43. Run `python harness.py wiki-init` to regenerate the
  Wiki FTS index after the Phase 1 Wiki updates.
  → `python harness.py wiki-init` reports `documents: 20, chunks: 129, database: tmp/local/project-context/knowledge.db; Wiki ready; existing Markdown preserved`.
- [x] 44. Archive the `implement-phase-1-foundation` change;
  update `openspec/CURRENT.md` to list the five Phase 1
  capabilities.
  → `openspec archive implement-phase-1-foundation -y` archived the change under `archive/2026-10-04-implement-phase-1-foundation/`; the five Phase 1 capabilities were already listed in [`openspec/CURRENT.md`](../../../openspec/CURRENT.md) after the prior plan-change archive cycle.

## Phase 2 — Ingestion (parsers, content addressing, pipeline driver, chunking, enrichment)

- [ ] 45. Implement `platform.ingest.PipelineDriver` — the §18
  ingestion pipeline coordinator (parsers → chunking → enrichment →
  graph/vector/metadata → runtime store) with explicit stage
  boundaries and stage error handling.
- [ ] 46. Implement `platform.adapters.git.LibGit2OrCliAdapter`
  final choice (default CLI for portability; document the
  decision).
- [ ] 47. Implement `platform.core.canonical.ContentAddress`
  (SHA-256 cache reuse across branches) plus a property-based
  cross-branch reuse test.
- [ ] 48. Implement document source adapters: Markdown, HTML, PDF,
  plain text, supported office documents. Each adapter implements a
  `SourceAdapter` port returning `Document + Section[]`.
- [ ] 49. Implement the local source inbox scanner
  (`LocalSourceInboxScanner`) honouring `LOCAL_ONLY`, `REFERENCE`
  and `SNAPSHOT` policies from §9.
- [ ] 50. Implement the OpenSpec adapter that reads
  `openspec/specs/` and `openspec/changes/` and produces
  `Requirement`, `Specification`, `OpenSpecChange` entities plus
  `SATISFIES`, `PART_OF`, `IMPLEMENTED_BY` relations.
- [ ] 51. Implement `platform.ingest.JavaStructuredAdapter` for
  Maven modules, packages, classes, interfaces, methods,
  constructors, inheritance, annotations, calls, JPA mappings,
  configuration, tests. Use a documented Java parser library
  whose license passes the license gate.
- [ ] 52. Implement `platform.ingest.JarAdapter` for artifact
  coordinates, versions, packages, classes, interfaces,
  signatures, annotations, inherited types, modules, resources,
  source-JAR content, public APIs, dependency relationships.
- [ ] 53. Implement Gradle and `pom.xml` dependency-graph
  extraction (`platform.ingest.MavenAdapter`,
  `platform.ingest.GradleAdapter`).
- [ ] 54. Implement semantic/structural chunker selecting boundaries
  by document section / heading / Java class / Java method /
  OpenSpec element / requirement / protocol message / table /
  architecture unit. Chunks retain parent links.
- [ ] 55. Implement three-layer context enrichment (deterministic
  metadata + domain rules + optional small LLM) producing
  `ContextualChunk` records.
- [ ] 56. Implement the `local-source-inbox` spec scenarios (added
  in this change's `affected capabilities` table).
- [ ] 57. Implement the `content-addressed-processing` spec
  scenarios (added in this change's table).
- [ ] 58. Implement the `semantic-structural-chunking`,
  `context-enrichment`, `document-source-adapters`,
  `openspec-change-adapter`, `structured-code-intelligence`,
  `jar-dependency-intelligence` spec scenarios as Phase 2.
- [ ] 59. Add focused regression tests per adapter and per
  chunker.
- [ ] 60. Update Wiki (new `modules/ingest`, `interfaces/source-
  adapters`, `interfaces/chunker`, `interfaces/enrichment`),
  archive the Phase 2 change, update `openspec/CURRENT.md`.

## Phase 3 — Storage (runtime DB, sharded graph, provenance/freshness)

- [ ] 61. Select the embedded storage engine(s) capable of
  relational metadata, full-text search, vector search and graph
  traversal within one deployable unit. Document the decision in
  an ADR (`adr.embedded-storage-selection`) and record the license
  rationale.
- [ ] 62. Implement `platform.runtime.RuntimeStore` with
  per-shard content-addressed cache, version stamp, write-ahead
  log and per-project advisory file lock.
- [ ] 63. Implement `platform.runtime.SparseIndex` (BM25 or
  equivalent) and metadata index.
- [ ] 64. Implement `platform.runtime.DenseIndex` with at least one
  ANN backend (HNSW or flat) behind a `DenseIndexPort`.
- [ ] 65. Implement `platform.runtime.FullTextIndex`.
- [ ] 66. Implement the canonical knowledge graph
  (`platform.core.graph.Graph`) with sharded nodes/edges,
  content-addressed entity bodies, entity families from §16 and
  relation families from §16; implement the graph with a clear
  separation between ANN graph and knowledge graph.
- [ ] 67. Implement knowledge provenance (`KnowledgeState`) and
  freshness tracking; record the staleness map on every reconcile.
- [ ] 68. Add focused regression tests including a 50k-entity
  sharding test that asserts the documented shard counts and the
  32 MiB single-file cap.
- [ ] 69. Update Wiki (new `modules/runtime-store`, `modules/graph`,
  `interfaces/sparse-index`, `interfaces/dense-index`), archive the
  Phase 3 change, update `openspec/CURRENT.md`.

## Phase 4 — Retrieval (hybrid, multi-stage, reranking, contextual assembly)

- [ ] 70. Implement `platform.embeddings.EmbeddingModelPort` with
  one default multilingual embedding model (English, German,
  Ukrainian, optionally Russian) that satisfies §25 requirements
  and the model license gate.
- [ ] 71. Implement `platform.retrieval.HybridRetrieval` with
  dense ANN + sparse/BM25 + exact identifier lookup, fused into a
  single ranked candidate set.
- [ ] 72. Implement `platform.retrieval.MultiStageRetrieval`
  (candidate generation → fusion → metadata/version/security
  filter → graph expansion → hierarchy expansion → rerank).
- [ ] 73. Implement `platform.retrieval.GraphExpansion` and
  `platform.retrieval.HierarchyExpansion` bounded by documented
  budgets.
- [ ] 74. Implement pluggable advanced rerankers (cross-encoder,
  ColBERT-style, etc.) behind a `RerankerPort`; rerankers run on
  bounded candidate sets only.
- [ ] 75. Implement metadata-driven temporal/version/security
  filters (`validFrom <= queryDate AND (validTo IS NULL OR
  validTo >= queryDate)`).
- [ ] 76. Implement `platform.context.ContextAssembler` with
  deduplication, context budget, citation preservation,
  authoritative-evidence preference, conflict detection and
  uncertainty surfacing.
- [ ] 77. Add evaluation fixtures and a retrieval benchmark test
  (`tests/test_retrieval_benchmark.py`) recording recall/precision,
  reranker quality, latency, cache reuse.
- [ ] 78. Update Wiki (new `modules/retrieval`, `modules/embeddings`,
  `modules/context-assembler`, `interfaces/hybrid-retrieval`,
  `interfaces/reranker`), archive the Phase 4 change, update
  `openspec/CURRENT.md`.

## Phase 5 — Orchestration (query, local LLM, task context, capability discovery)

- [ ] 79. Implement `platform.orchestrator.QueryOrchestrator` with
  three escalation levels (L0 direct retrieval, L1 retrieval +
  small local LLM, L2 strong external agent) and the
  retrieval-first escalation order from §33.
- [ ] 80. Implement `platform.llm.LocalLLMPort` behind a stable
  interface; do not bind any specific model in the default
  container; declare the local-LLM capability as optional in
  capability discovery.
- [ ] 81. Implement `platform.task.TaskContextBuilder` producing
  the bounded TaskContext bundle shape from §52.
- [ ] 82. Implement `platform.orchestrator.CapabilityDiscovery`
  returning the structured capability descriptor from §47.
- [ ] 83. Add focused regression tests including a retrieval-first
  policy test asserting that an implementation question does not
  trigger broad source scanning before MCP retrieval.
- [ ] 84. Update Wiki (new `modules/orchestrator`, `modules/llm-port`,
  `modules/task-context`, `interfaces/capability-discovery`),
  archive the Phase 5 change, update `openspec/CURRENT.md`.

## Phase 6 — Agent integration (MCP, skill, adapters, distribution profiles)

- [ ] 85. Implement the MCP server
  (`platform.mcp.McpServer`) exposing the semantic tools from §36
  (`project.search`, `project.retrieve_context`,
  `project.get_entity`, `project.get_component`,
  `project.get_requirement`, `project.get_spec`,
  `project.get_architecture`, `project.get_dependency`,
  `project.find_implementation`, `project.trace_requirement`,
  `project.find_references`, `project.get_project_version`,
  `project.get_conflicts`, `project.get_stale_knowledge`,
  `project.build_task_context`, `project.materialize_knowledge`,
  `project.refresh_sources`) and `describe_capabilities`.
- [ ] 86. Implement skill distribution resources
  (`project-intelligence://distribution/manifest`,
  `project-intelligence://skills/index`,
  `project-intelligence://skills/<name>/<version>/SKILL.md` and
  referenced files).
- [ ] 87. Author the canonical Agent Skill at
  `distribution/skills/project-intelligence/SKILL.md` per §37 with
  progressive disclosure (concise main file + references for MCP
  tools, retrieval policy, versioning, OKF profile, security).
- [ ] 88. Implement the version-compatibility handshake (§39) for
  MCP API, knowledge schema, OKF profile, agent adapter,
  plugin-distribution schema.
- [ ] 89. Implement the Codex/ChatGPT plugin packager that emits
  `dist/codex/plugin.json`, `dist/codex/mcp.json`, the bundled
  skill and assets, and the `.codex-plugin/plugin.json`
  compatibility fallback. Add a smoke test.
- [ ] 90. Implement the Claude Code plugin packager emitting
  `dist/claude-code/.claude-plugin/plugin.json`,
  `dist/claude-code/.mcp.json`, skill, optional commands/agents.
- [ ] 91. Implement the OpenCode plugin package emitting
  `dist/opencode/package.json`, `dist/opencode/plugin/*.ts`,
  skill, `config/opencode.example.jsonc`.
- [ ] 92. Implement the generic agent bundle
  (`dist/generic-agent/skills/`, `mcp/`, `AGENTS.example.md`,
  `README.md`).
- [ ] 93. Implement the agent adapter contract from §46
  (`AgentIntegrationAdapter` with `detect`, `install`,
  `configureMcp`, `installSkill`, `verifyCompatibility`,
  `healthCheck`, `uninstall`, `describe`).
- [ ] 94. Implement the plugin supply-chain security gate
  (pinned version, content hash, SBOM, license/scan, source
  provenance, signature support, no hidden auto-install,
  approval-gated materialise tools).
- [ ] 95. Update Wiki (new `interfaces/mcp-tools`,
  `interfaces/skill-distribution`, `interfaces/plugin-distribution`),
  archive the Phase 6 change, update `openspec/CURRENT.md`.

## Phase 7 — Control plane (registry, hooks, capabilities, secrets, policy, audit)

- [ ] 96. Implement `platform.control.FeatureRegistry` and
  `PluginRegistry` with the lifecycle states from §59 (installed,
  enabled, disabled, failed, incompatible, blocked-by-policy,
  update-available) and manifest validation (license, capabilities,
  compatibility).
- [ ] 97. Implement `platform.control.HookRuntime` with the
  lifecycle events from §59 (`beforeIngestion`, `afterIngestion`,
  `beforeIndexUpdate`, `afterIndexUpdate`, `beforeRetrieval`,
  `afterRetrieval`, `beforeContextAssembly`, `afterContextAssembly`,
  `beforeMcpTool`, `afterMcpTool`, `beforeAgentDelegation`,
  `afterAgentDelegation`, `beforeMaterialization`,
  `afterMaterialization`, `onBranchSwitch`, `onProjectOpen`,
  `onProjectClose`), bounded timeout, cancellation, structured
  result, correlation id, audit record, bounded retries, failure
  policies (`FAIL_OPEN`, `FAIL_CLOSED`, `WARN_ONLY`,
  `DISABLE_PLUGIN`).
- [ ] 98. Implement `platform.control.PolicyEngine` with
  capability-based authorization, the capability vocabulary from
  §59, role defaults (`Viewer`, `Developer`, `Maintainer`,
  `Administrator`), and the
  `ALLOW / DENY / REQUIRE_APPROVAL` decision contract.
- [ ] 99. Implement `platform.control.SecretProvider` with the
  `secret://` reference vocabulary and redaction in MCP/A2A
  responses, audit payloads and LLM context.
- [ ] 100. Implement `platform.control.AuditLog` and
  `OperationalLog` separation; never write secrets or unnecessary
  source contents into audit records.
- [ ] 101. Implement `platform.control.FeatureFlags` scoped by
  machine / project / branch / user / deployment profile.
- [ ] 102. Implement `platform.control.UiExtension` registry
  (declarative UI descriptors, no arbitrary JS injection for
  untrusted plugins).
- [ ] 103. Add focused regression tests including a policy-engine
  test verifying the read-only coding-agent capability set from
  §59.
- [ ] 104. Update Wiki (new `modules/registry`, `modules/hooks`,
  `modules/policy-engine`, `modules/secret-provider`,
  `interfaces/capabilities`), archive the Phase 7 change, update
  `openspec/CURRENT.md`.

## Phase 8 — Security (enterprise boundary)

- [ ] 105. Implement `platform.security.EnterpriseBoundary`
  including secret detection, source-level permissions, security
  classification, outbound filtering, redaction, egress policy and
  auditability.
- [ ] 106. Add the security metadata to the retrieval filtering
  pipeline so security classification participates in retrieval
  decisions.
- [ ] 107. Add focused regression tests for secret detection,
  outbound filtering, and retrieval redaction.
- [ ] 108. Update Wiki (new `modules/security`, `interfaces/egress`),
  archive the Phase 8 change, update `openspec/CURRENT.md`.

## Phase 9 — Distribution (UI, container, OCI, one-click, OKF wiki)

- [ ] 109. Implement `platform.ui.RestApi` exposing the UI API
  surface from §57 (`query`, `retrieve`, `sources`, `graph`,
  `wiki`, `project-version`, `indexing-status`,
  `knowledge-status`, `materialize`, `agent-delegation`).
- [ ] 110. Implement the lightweight custom UI (default Ionic or
  documented equivalent) compiled to static assets, served by the
  core deployment, no Node.js required at runtime.
- [ ] 111. Implement the Open WebUI adapter (optional, not bundled
  by default) behind a feature flag; verify the Open WebUI
  license version before bundling.
- [ ] 112. Implement the OKF wiki profile distribution
  (validate / package OKF bundle into the container, ship the
  profile adapter).
- [ ] 113. Implement the one-click launcher scripts
  (`project-intelligence` binary for Linux,
  `ProjectIntelligence.exe` / `Start-ProjectIntelligence.ps1` for
  Windows) that verify Docker/Podman, create volumes, mount the
  repository, start the container(s), wait for health readiness,
  open the browser.
- [ ] 114. Finalise the single-container default image
  (`Containerfile` / `Dockerfile`) and the optional two-container
  profile via `docker-compose.yml` with documented profiles.
- [ ] 115. Add launch smoke tests verifying that the container
  starts, hydrates against a small synthetic project, opens the UI
  port, and reports health.
- [ ] 116. Update Wiki (new `modules/ui`, `interfaces/rest-api`,
  `project/distribution-vendors`), archive the Phase 9 change,
  update `openspec/CURRENT.md`.

## Phase 10 — A2A and final quality gates

- [ ] 117. Implement `platform.a2a.A2aAdapter` behind a stable
  port; track a documented A2A spec version; do not let A2A
  protocol evolution leak into the core domain model.
- [ ] 118. Implement reverse delegation hooks (the platform
  initiates an A2A request to an external agent through its
  officially supported interface).
- [ ] 119. Add the integration quality-gates evaluation suites
  (§49) wired into CI; record metrics (retrieval recall/precision,
  reranker quality, context size, external LLM token consumption,
  latency, cache reuse, branch-switch hydration time, stale-
  knowledge detection rate, plugin setup success rate).
- [ ] 120. Add a final acceptance test suite covering all 52
  architectural invariants in §68.
- [ ] 121. Add a schema-version-migration test that asserts
  hydrate behaviour on `knowledgeSchemaVersion` /
  `embeddingModelVersion` / `indexSchemaVersion` mismatch
  (graceful error or migration path; no silent data loss).
- [ ] 122. Update Wiki to reflect the implemented platform; mark
  `architecture/system-overview.md` and
  `architecture/platform-overview.md` as `status: active`.
- [ ] 123. Archive the Phase 10 change, update
  `openspec/CURRENT.md`, and produce the v1.0 release of the
  platform (container image tag + OCI artefact + distribution
  bundles).