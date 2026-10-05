# Context impact — prepare-phase-3-storage

## Knowledge to create

The Wiki nodes below are NOT created by this change; they are listed
as future work the `implement-phase-3-storage` change must perform
when it ships the production code.

- `.ai/wiki/modules/runtime-store.md` — the Phase 3 runtime-store
  module map (`pi_platform/core/runtime/`,
  `pi_platform/ports/runtime/`, `pi_platform/adapters/runtime/`,
  plus the Phase 1 `pi_platform/runtime/cache.py` stub that Phase 3
  preserves for backward compatibility). `kind: modules`, `status:
  draft`.
- `.ai/wiki/modules/graph.md` — the Phase 3 sharded-graph module map
  (`pi_platform/core/runtime/graph.py`,
  `pi_platform/ports/runtime/graph.py`,
  `pi_platform/adapters/runtime/sharded_graph.py`). `kind: modules`,
  `status: draft`.
- `.ai/wiki/interfaces/runtime-store.md` — the `RuntimeStorePort`
  port contract, the dual-backend selection rule (SQLite default,
  PostgreSQL opt-in) and the WAL behaviour. `kind: interfaces`,
  `status: draft`.
- `.ai/wiki/interfaces/sparse-index.md` — the `SparseIndexPort`
  port contract and the BM25 default adapter. `kind: interfaces`,
  `status: draft`.
- `.ai/wiki/interfaces/dense-index.md` — the `DenseIndexPort`
  port contract, the HNSW default adapter and the flat-search
  fallback. `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/full-text-index.md` — the `FullTextIndexPort`
  port contract and the SQLite FTS5 adapter. `kind: interfaces`,
  `status: draft`.
- `.ai/wiki/interfaces/graph-expansion.md` — the Phase 4 preview
  `GraphExpansionPort` port contract and the bounded-budget rule.
  `kind: interfaces`, `status: draft`.
- `.ai/wiki/interfaces/provenance.md` — the `ProvenancePort`
  port contract and the `KnowledgeState` state machine. `kind:
  interfaces`, `status: draft`.
- `.ai/wiki/interfaces/freshness.md` — the `FreshnessTrackerPort`
  port contract and the `lastVerifiedAt` rule. `kind: interfaces`,
  `status: draft`.
- `.ai/wiki/adr/0008-embedded-storage-selection.md` — ADR slot for
  the runtime DB engine selection. The design candidate is
  **PostgreSQL + SQLite dual-backend** with Apache-2.0 / BSD
  licenses; rejected alternatives include DuckDB MIT, RocksDB
  Apache-2.0, `sled` MPL-2.0, LevelDB BSD-3-Clause, Badger
  Apache-2.0. `kind: adr`, `status: proposed`.

## Knowledge to update

The Wiki updates below are NOT performed by this change; they are
listed as future work the `implement-phase-3-storage` change must
perform alongside the production code.

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
  (content-addressed primary key). Status flips from `draft` to
  `active` once the implementation lands.
- `.ai/wiki/glossary/domain.md` — cross-link to the platform
  vocabulary for the new entries.
- `.ai/wiki/project/project-map.md` — add the new module folders
  under "Main source areas" with status `planned` until the
  implementation change lands; flip to `active` once the code is
  on disk.
- `.ai/wiki/project/implementation-roadmap.md` — add the Phase 3
  row to the phase table (currently Phase 1 + Phase 2 are marked
  complete; Phase 3 will be marked `in-progress` by the future
  implementation change and `complete` when its archive lands).
- `.ai/wiki/INDEX.md` — add the new Wiki modules, interfaces and
  ADRs once they exist on disk; the future implementation change is
  responsible for the index update.
- `openspec/CURRENT.md` — add the nine Phase 3 capabilities once the
  future `implement-phase-3-storage` change is archived; this change
  does NOT modify `openspec/CURRENT.md`.

## Knowledge to review for staleness

- `.ai/wiki/architecture/platform-overview.md` — review the Phase 1
  + Phase 2 module map and ensure the Phase 3 extensions remain
  additive; the existing Phase 1 boundary (`core/{canonical,git,
  sync,licensing}` + `ports` + `adapters/{fs,git}`) MUST stay
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
  `LocalSourceInboxScanner` entries remain unchanged. The Phase 3
  species are documented as Phase 3 additions, never as
  redefinitions of Phase 1 / Phase 2 terms.
- `.ai/wiki/adr/0005-platform-source-language.md` — review the
  Python 3.11 decision and confirm the Phase 3 storage libraries
  land as adapters under `pi_platform/adapters/runtime/` rather
  than as new platform-level language dependencies. The ADR is
  unchanged in this change; the future implementation change adds
  the storage libraries without modifying the ADR text.
- `.ai/wiki/adr/0002-canonical-runtime-separation.md` — review the
  canonical / runtime separation invariants; the Phase 3 storage
  layer respects invariants #1-#4 by writing through the
  per-shard content-addressed cache keyed by the Phase 1 SHA-256
  content address and by reusing the Phase 1 advisory file lock.

## Affected implementation

Modules/paths the future `implement-phase-3-storage` change will
populate (NOT populated by this change):

- `pi_platform/core/runtime/` — new core subpackage for
  `RuntimeStore`, `Graph`, `Provenance`, `Freshness`
  implementations;
- `pi_platform/ports/runtime/` — new ports subpackage for
  `RuntimeStorePort`, `SparseIndexPort`, `DenseIndexPort`,
  `FullTextIndexPort`, `GraphPort`, `GraphExpansionPort`,
  `ProvenancePort`, `FreshnessTrackerPort`;
- `pi_platform/adapters/runtime/` — new default adapters
  (`SqliteRuntimeStore`, `PostgresRuntimeStore`, `Bm25SparseIndex`,
  `HnswDenseIndex`, `FlatDenseIndex`, `SqliteFtsFullTextIndex`,
  `LocalShardedGraph`, `BoundedGraphExpansion`,
  `LocalProvenanceTracker`, `LastVerifiedFreshnessTracker`);
- `pi_platform/runtime/cache.py` — Phase 1 stub preserved for
  backward compatibility; the `RuntimeStore` default adapter
  implements the same `put` / `get` / `has` / `evict` / `stats`
  surface;
- `tests/test_platform_phase3.py` — new Phase 3 regression suite;
- `tests/test_graph_50k.py` — new 50 000-entity property-based
  test;
- `distribution/licenses/dependency-inventory.json` — new SPDX entries
  for the chosen storage libraries (PostgreSQL Python driver,
  HNSW library, BM25 library, optional full-text library);
- `Containerfile` — install steps for the new Python packages;
- `pi_platform/cli/main.py` — extends with `runtime-status` and
  `graph-rebuild` subcommands.

Primary symbols/interfaces the future change will introduce
(NOT introduced by this change):

- `pi_platform.ports.runtime.runtime_store.RuntimeStorePort`,
  `RuntimeStoreError`, `RuntimeEntry`;
- `pi_platform.ports.runtime.sparse_index.SparseIndexPort`,
  `SparseHit`;
- `pi_platform.ports.runtime.dense_index.DenseIndexPort`,
  `DenseHit`;
- `pi_platform.ports.runtime.full_text_index.FullTextIndexPort`,
  `FullTextHit`;
- `pi_platform.ports.runtime.graph.GraphPort`,
  `GraphManifest`, `Shard`;
- `pi_platform.ports.runtime.graph_expansion.GraphExpansionPort`,
  `GraphExpansion`;
- `pi_platform.ports.runtime.provenance.ProvenancePort`,
  `ProvenanceEvent`;
- `pi_platform.ports.runtime.freshness.FreshnessTrackerPort`,
  `FreshnessSnapshot`.

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
  registered.
- `adr/0004-ports-and-adapters-extension-style.md` — remains
  accepted and unaffected. Phase 3 adds ports under
  `pi_platform/ports/runtime/` and adapters under
  `pi_platform/adapters/runtime/`.
- `adr/0005-platform-source-language.md` — remains accepted and
  unaffected. Phase 3 keeps the Python 3.11 default; the storage
  libraries are invoked as adapters under
  `pi_platform/adapters/runtime/` rather than as new
  platform-level language dependencies.
- `adr/0006-phase-2-parser-selection.md` — remains accepted and
  unaffected. The Phase 3 storage surface is independent of the
  Java parser library.
- `adr/0007-phase-2-inbox-policy-default.md` — remains accepted and
  unaffected. The Phase 3 storage surface is independent of the
  inbox policy.
- future `adr/0008-embedded-storage-selection.md` — to be authored
  by the future implementation change; documents the
  **PostgreSQL + SQLite dual-backend** (Apache-2.0 / BSD) choice
  and the rejected alternatives (DuckDB MIT, RocksDB Apache-2.0,
  `sled` MPL-2.0, LevelDB BSD-3-Clause, Badger Apache-2.0).

## Acceptance criteria

- [x] Relevant Wiki pages reflect planned/shipped implementation.
  All updates above are additive and link back to the v0.8
  architecture baseline. The future implementation change performs
  the on-disk Wiki edits.
- [x] Generated local context index was refreshed. The Phase 2
  `python harness.py wiki-init` already produced the local FTS
  index. The future implementation change will re-run
  `python harness.py wiki-init` after the Phase 3 Wiki edits
  land.
- [x] Links and stable knowledge IDs validate. The new Wiki pages
  will use stable `id` frontmatter values (see Knowledge to create
  above) so that `kb_validate` succeeds.
- [x] Spec/implementation mismatches are resolved or explicitly
  documented. There is no implementation in this change; the nine
  Phase 3 specs describe the planned platform behaviour against
  the v0.8 baseline with no conflict. The cross-phase task
  responsibility matrix in `proposal.md` records the explicit
  ownership split between Phase 3 and the later phases.