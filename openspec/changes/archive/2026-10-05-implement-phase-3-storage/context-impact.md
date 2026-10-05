# Context impact — implement-phase-3-storage

## Knowledge to create

The Wiki nodes below are created by this change:

- `.ai/wiki/modules/runtime-store.md` — the Phase 3 runtime-store
  module map (`pi_platform/core/runtime/`,
  `pi_platform/ports/runtime/`, `pi_platform/adapters/runtime/`,
  plus the Phase 1 `pi_platform/runtime/cache.py` shim). `kind:
  modules`, `status: active`.
- `.ai/wiki/modules/graph.md` — the Phase 3 sharded-graph module
  map (`pi_platform/core/runtime/graph.py`,
  `pi_platform/ports/runtime/graph.py`,
  `pi_platform/adapters/runtime/sharded_graph.py`). `kind:
  modules`, `status: active`.
- `.ai/wiki/interfaces/runtime-store.md` — the `RuntimeStorePort`
  port contract, the dual-backend selection rule (SQLite default,
  PostgreSQL opt-in) and the WAL behaviour. `kind: interfaces`,
  `status: active`.
- `.ai/wiki/interfaces/sparse-index.md` — the `SparseIndexPort`
  port contract and the BM25 default adapter. `kind: interfaces`,
  `status: active`.
- `.ai/wiki/interfaces/dense-index.md` — the `DenseIndexPort`
  port contract, the flat-search fallback adapter and the HNSW
  opt-in. `kind: interfaces`, `status: active`.
- `.ai/wiki/interfaces/full-text-index.md` — the
  `FullTextIndexPort` port contract and the SQLite FTS5 adapter.
  `kind: interfaces`, `status: active`.
- `.ai/wiki/interfaces/graph-expansion.md` — the Phase 4 preview
  `GraphExpansionPort` port contract and the bounded-budget rule.
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/provenance.md` — the `ProvenancePort`
  port contract and the `KnowledgeState` state machine. `kind:
  interfaces`, `status: active`.
- `.ai/wiki/interfaces/freshness.md` — the `FreshnessTrackerPort`
  port contract and the `lastVerifiedAt` rule. `kind: interfaces`,
  `status: active`.
- `.ai/wiki/adr/0008-embedded-storage-selection.md` — ADR for the
  runtime DB engine selection. The design candidate is
  **PostgreSQL + SQLite dual-backend** with Apache-2.0 / BSD
  licenses; rejected alternatives include DuckDB MIT, RocksDB
  Apache-2.0, `sled` MPL-2.0, LevelDB BSD-3-Clause, Badger
  Apache-2.0. `kind: adr`, `status: proposed`.

## Knowledge to update

- `.ai/wiki/architecture/platform-overview.md` — extend the Phase 1
  + Phase 2 module map with the Phase 3 module map
  (`runtime/`, `ports/runtime`, `adapters/runtime`).
  Reference the new `modules/runtime-store.md` and
  `modules/graph.md` nodes.
- `.ai/wiki/architecture/system-overview.md` — extend the
  "Principal components" section with the Phase 3 storage reference
  and links to the new module / interface nodes.
- `.ai/wiki/glossary/platform.md` — add Phase 3 vocabulary entries:
  `RuntimeStore`, `SparseIndex`, `DenseIndex`, `FullTextIndex`,
  `Graph`, `GraphExpansion`, `ProvenanceTracker`,
  `FreshnessTracker`, `KnowledgeState` (state machine), `Shard`
  (content-addressed primary key). Status: `active`.
- `.ai/wiki/glossary/domain.md` — cross-link to the platform
  vocabulary for the new entries.
- `.ai/wiki/project/project-map.md` — add the new module folders
  under "Main source areas" with status `active`.
- `.ai/wiki/project/implementation-roadmap.md` — flip the Phase 3
  row from `in-progress` to `complete` when this change is archived.
- `.ai/wiki/INDEX.md` — add the new Wiki modules, interfaces and
  ADR.
- `openspec/CURRENT.md` — add the nine Phase 3 capabilities once
  this change is archived.

## Knowledge to review for staleness

- `.ai/wiki/architecture/platform-overview.md` — review the Phase 1
  + Phase 2 module map and confirm the Phase 3 extensions remain
  additive; the existing Phase 1 boundary (`core/{canonical,git,
  sync,licensing}` + `ports` + `adapters/{fs,git}`) stays
  unchanged.
- `.ai/wiki/architecture/system-overview.md` — review the
  "Principal components" section to confirm the Phase 3 storage
  reference does not contradict the existing canonical / runtime
  boundary.
- `.ai/wiki/glossary/platform.md` — review the Phase 1 + Phase 2
  vocabulary; Phase 3 adds new entries (`RuntimeStore`,
  `SparseIndex`, `DenseIndex`, `FullTextIndex`, `Graph`,
  `GraphExpansion`, `ProvenanceTracker`, `FreshnessTracker`,
  `KnowledgeState`, `Shard`). The existing `PipelineDriver`,
  `SourceAdapter`, `Chunker`, `ContextEnricher`,
  `LocalSourceInboxScanner` entries remain unchanged.
- `.ai/wiki/adr/0005-platform-source-language.md` — review the
  Python 3.11 decision and confirm the Phase 3 storage libraries
  land as adapters under `pi_platform/adapters/runtime/` rather
  than as new platform-level language dependencies.
- `.ai/wiki/adr/0002-canonical-runtime-separation.md` — review the
  canonical / runtime separation invariants; the Phase 3 storage
  layer respects invariants #1-#4 by writing through the
  per-shard content-addressed cache keyed by the Phase 1 SHA-256
  content address and by reusing the Phase 1 advisory file lock.

## Affected implementation

Modules/paths populated by this change:

- `pi_platform/core/runtime/` — new core subpackage for
  `RuntimeStore`, `Graph`, `Provenance`, `Freshness` core
  implementations (port re-exports);
- `pi_platform/ports/runtime/` — new ports subpackage for
  `RuntimeStorePort`, `SparseIndexPort`, `DenseIndexPort`,
  `FullTextIndexPort`, `GraphPort`, `GraphExpansionPort`,
  `ProvenancePort`, `FreshnessTrackerPort`;
- `pi_platform/adapters/runtime/` — new default adapters
  (`SqliteRuntimeStore`, `Bm25SparseIndex`, `FlatDenseIndex`,
  `SqliteFtsFullTextIndex`, `LocalShardedGraph`,
  `BoundedGraphExpansion`, `LocalProvenanceTracker`,
  `LastVerifiedFreshnessTracker`);
- `pi_platform/runtime/cache.py` — Phase 1 stub rewritten as a
  thin shim that delegates to the new default
  `SqliteRuntimeStore` adapter;
- `tests/test_platform_phase3.py` — new Phase 3 regression suite;
- `tests/test_graph_50k.py` — new 50 000-entity property-based
  test;
- `Containerfile` — documented install steps for the optional
  PostgreSQL backend;
- `pi_platform/cli/main.py` — extends with `runtime-status` and
  `graph-rebuild` subcommands.

Primary symbols/interfaces introduced by this change:

- `pi_platform.ports.runtime.runtime_store.RuntimeStorePort`,
  `RuntimeStoreError`, `RuntimeEntry`,
  `RuntimeStatusReport`;
- `pi_platform.ports.runtime.sparse_index.SparseIndexPort`,
  `SparseHit`;
- `pi_platform.ports.runtime.dense_index.DenseIndexPort`,
  `DenseHit`;
- `pi_platform.ports.runtime.full_text_index.FullTextIndexPort`,
  `FullTextHit`;
- `pi_platform.ports.runtime.graph.GraphPort`,
  `GraphManifest`, `Shard`, `GraphPortError`;
- `pi_platform.ports.runtime.graph_expansion.GraphExpansionPort`,
  `GraphExpansion`, `GraphExpansionError`;
- `pi_platform.ports.runtime.provenance.ProvenancePort`,
  `ProvenanceEvent`, `ProvenanceError`;
- `pi_platform.ports.runtime.freshness.FreshnessTrackerPort`,
  `FreshnessSnapshot`, `FreshnessError`;
- `pi_platform.adapters.runtime.sqlite_runtime_store.SqliteRuntimeStore`;
- `pi_platform.adapters.runtime.bm25_sparse_index.Bm25SparseIndex`;
- `pi_platform.adapters.runtime.flat_dense_index.FlatDenseIndex`;
- `pi_platform.adapters.runtime.sqlite_fts_full_text_index.SqliteFtsFullTextIndex`;
- `pi_platform.adapters.runtime.sharded_graph.LocalShardedGraph`;
- `pi_platform.adapters.runtime.bounded_graph_expansion.BoundedGraphExpansion`;
- `pi_platform.adapters.runtime.provenance_tracker.LocalProvenanceTracker`;
- `pi_platform.adapters.runtime.last_verified_freshness_tracker.LastVerifiedFreshnessTracker`.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md` —
  remains accepted and unaffected. Phase 3 respects the decision by
  keeping harness core skills separated from the Phase 7 agent
  integration packaging work.
- `adr/0002-canonical-runtime-separation.md` — remains accepted and
  unaffected. Phase 3 specs respect invariants #1-#4 (canonical vs
  runtime, Git as source of truth, bidirectional sync,
  deterministic serialization) by writing through the per-shard
  content-addressed cache and reusing the Phase 1 advisory file
  lock.
- `adr/0003-license-governance-default.md` — remains accepted and
  unaffected. Every Phase 3 dependency requires an SPDX-tracked
  inventory entry that passes `LicenseGate` before the adapter is
  registered (this change adds NO new dependencies).
- `adr/0004-ports-and-adapters-extension-style.md` — remains
  accepted and unaffected. Phase 3 adds ports under
  `pi_platform/ports/runtime/` and adapters under
  `pi_platform/adapters/runtime/`.
- `adr/0005-platform-source-language.md` — remains accepted and
  unaffected. Phase 3 keeps the Python 3.11 default; the storage
  libraries are adapters under
  `pi_platform/adapters/runtime/` rather than as new
  platform-level language dependencies.
- `adr/0006-phase-2-parser-selection.md` — remains accepted and
  unaffected. The Phase 3 storage surface is independent of the
  Java parser library.
- `adr/0007-phase-2-inbox-policy-default.md` — remains accepted and
  unaffected. The Phase 3 storage surface is independent of the
  inbox policy.
- new `adr/0008-embedded-storage-selection.md` — authored by this
  change; documents the **PostgreSQL + SQLite dual-backend**
  (Apache-2.0 / BSD) choice and the rejected alternatives (DuckDB
  MIT, RocksDB Apache-2.0, `sled` MPL-2.0, LevelDB BSD-3-Clause,
  Badger Apache-2.0).

## Acceptance criteria

- [x] Relevant Wiki pages reflect shipped implementation.
  All updates above are additive and link back to the v0.8
  architecture baseline. The Wiki edits land in this change.
- [x] Generated local context index was refreshed. The Phase 2
  `python harness.py wiki-init` already produced the local FTS
  index; this change re-runs `python harness.py wiki-init` after
  the Phase 3 Wiki edits land.
- [x] Links and stable knowledge IDs validate. The new Wiki pages
  use stable `id` frontmatter values so that `kb_validate`
  succeeds.
- [x] Spec/implementation mismatches are resolved or explicitly
  documented. The nine Phase 3 specs describe the platform
  behaviour shipped by this change with no conflict. The
  cross-phase task responsibility matrix in `proposal.md` records
  the explicit ownership split between Phase 3 and the later
  phases.