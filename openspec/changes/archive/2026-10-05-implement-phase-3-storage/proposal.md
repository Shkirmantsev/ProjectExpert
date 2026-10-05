# Proposal — Implement Phase 3 Storage

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the storage layer in §10.1-§10.4, §16, §17, §26, §28, §31,
§54, §55, §61-§67, §73. Nine Phase 3 capability specs are now
proposed under
[`openspec/changes/prepare-phase-3-storage/specs/2026-10-04-*/`](../../changes/prepare-phase-3-storage/specs/)
and `openspec validate prepare-phase-3-storage --type change --strict`
returns `valid`. The 14 accepted Phase 1 + Phase 2 capability specs
supply the canonical value-type catalogue, the SHA-256 content
address, the Git-version-aware runtime, the bidirectional sync, the
license gate, the `PipelineDriver`, the `SourceAdapter` family, the
`Chunker`, the `ContextEnricher`, the `LocalSourceInboxScanner`, the
`OpenSpecChangeAdapter`, the cross-branch reuse property test and the
nine Phase 2 capability specs that emit the canonical chunks and
entity / relation records the Phase 3 runtime store is expected to
host. The repository still ships zero production code under
`pi_platform/ports/runtime/`, `pi_platform/core/runtime/`,
`pi_platform/adapters/runtime/` or any related Phase 3 module. There
is therefore no `RuntimeStore`, no `SparseIndex`, no `DenseIndex`, no
`FullTextIndex`, no `ShardedGraph`, no `KnowledgeState` lifecycle,
no `FreshnessTracker`, no `embedded-storage-selection` ADR, no
runtime-DB dependency inventory entries, no `runtime-status` or
`graph-rebuild` CLI subcommands, and no 50 000-entity sharding
property test. The Phase 1 runtime cache stub at
`pi_platform/runtime/cache.py` is documented as a placeholder that
Phase 3 replaces with the real embedded runtime store. The runtime
has no way to host the canonical chunks and entities / relations
that Phase 2 produces, the canonical knowledge graph is not
materialised on disk, the freshness / provenance state machine is
not implemented, and `python -m pi_platform.cli` cannot report the
runtime-store state.

This change resolves the gap by implementing the Phase 3 production
code per the nine accepted specs, the per-port regression suite
(`tests/test_platform_phase3.py`), the 50 000-entity property test
(`tests/test_graph_50k.py`), the new `runtime-status` and
`graph-rebuild` CLI subcommands, the new dependency inventory entries
(for libraries whose SPDX identifier is recorded and that pass
`LicenseGate`), the Phase 3 Wiki nodes, the
`embedded-storage-selection` ADR and the `openspec/CURRENT.md`
adoption of the nine new capabilities. After this change is
archived, the Phase 3 spec deltas are promoted to
`openspec/specs/2026-10-04-*/`, the planning-change tasks 61-69 are
flipped to `[x]`, and the Phase 1 round-trip invariant
(`tests/test_canonical_roundtrip.py`) plus the Phase 2 regression
suite remain green byte-for-byte.

## Goal

Ship the Phase 3 production code per the nine accepted capability
specs in
[`prepare-phase-3-storage/specs/`](../../changes/prepare-phase-3-storage/specs/),
land the per-port regression suite and the 50 000-entity property
test, add the new `runtime-status` and `graph-rebuild` CLI
subcommands, and archive the change so the nine Phase 3 capability
specs are adopted into `openspec/specs/2026-10-04-*/` and listed in
`openspec/CURRENT.md`.

What this change ships:

- the additive ports under `pi_platform/ports/runtime/`
  (`runtime_store`, `sparse_index`, `dense_index`, `full_text_index`,
  `graph`, `graph_expansion`, `provenance`, `freshness`);
- the core implementations under `pi_platform/core/runtime/`
  (`runtime_store`, `graph`, `provenance`, `freshness`);
- the default adapters under `pi_platform/adapters/runtime/`
  (`sqlite_runtime_store`, `bm25_sparse_index`, `flat_dense_index`,
  `sqlite_fts_full_text_index`, `sharded_graph`,
  `bounded_graph_expansion`, `provenance_tracker`,
  `last_verified_freshness_tracker`);
- the SPDX-tracked `dependency-inventory.json` entries (only for
  libraries whose SPDX identifier is recorded and that pass
  `LicenseGate`); the default runtime uses Python stdlib
  `sqlite3` only, so the PostgreSQL driver and HNSW libraries are
  not strictly required for the default backend and are added only
  when their SPDX identifiers are recorded;
- the new regression suites
  (`tests/test_platform_phase3.py`,
  `tests/test_graph_50k.py`);
- the new `runtime-status` and `graph-rebuild` CLI subcommands;
- the new Wiki nodes, the `embedded-storage-selection` ADR, the
  `openspec/CURRENT.md` adoption row for the nine Phase 3
  capabilities, and the flip of plan-change tasks 61-69 from `[ ]`
  to `[x]`.

Out of scope for this change (future phases):

- the embedding model (Phase 4 task 70 `EmbeddingModelPort`);
- the hybrid retrieval, multi-stage retrieval, reranker,
  metadata-driven filters, context assembler, retrieval benchmark
  (Phase 4 tasks 71-77);
- the query orchestrator, local LLM, task context and capability
  discovery (Phase 5 tasks 79-83);
- the MCP server exposing the runtime store (Phase 6 task 85);
- the control plane, security, distribution, A2A (Phase 7+ tasks
  86-123).

Phase 3 only contracts the port surfaces for the `RuntimeStore`, the
three indexes, the sharded graph, the `GraphExpansion` preview, the
`KnowledgeState` lifecycle and the `FreshnessTracker`. Phase 4 owns
the retrieval composition and the production `GraphExpansion`
implementation.

## Affected capabilities

This change implements the nine Phase 3 capability specs in
[`prepare-phase-3-storage/specs/2026-10-04-*/`](../../changes/prepare-phase-3-storage/specs/)
and lists them in `openspec/CURRENT.md` on archive. No accepted
Phase 1 or Phase 2 capability spec is modified or retired; the 14
accepted Phase 1 + Phase 2 specs are unchanged and continue to pass
strict validation.

| Capability | Architecture sections | Phase 3 task(s) | Spec delta path |
|---|---|---|---|
| `embedded-storage-selection` | §61 | 61 | [`2026-10-04-embedded-storage-selection/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-embedded-storage-selection/spec.md) |
| `runtime-store` | §62, §10.2, §64 | 62, 69 | [`2026-10-04-runtime-store/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-runtime-store/spec.md) |
| `sparse-index` | §63, §26 | 63, 69 | [`2026-10-04-sparse-index/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-sparse-index/spec.md) |
| `dense-index` | §64, §28 | 64, 69 | [`2026-10-04-dense-index/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-dense-index/spec.md) |
| `full-text-index` | §65, §26 | 65, 69 | [`2026-10-04-full-text-index/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-full-text-index/spec.md) |
| `sharded-graph` | §66, §10.1, §16, §17 | 66, 68, 69 | [`2026-10-04-sharded-graph/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-sharded-graph/spec.md) |
| `graph-expansion` | §73, §31 | (Phase 4 preview) | [`2026-10-04-graph-expansion/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-graph-expansion/spec.md) |
| `provenance-state-model` | §67, §54 | 67, 69 | [`2026-10-04-provenance-state-model/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-provenance-state-model/spec.md) |
| `freshness-tracking` | §55, §67 | 67, 69 | [`2026-10-04-freshness-tracking/spec.md`](../../changes/prepare-phase-3-storage/specs/2026-10-04-freshness-tracking/spec.md) |

Cross-phase task responsibility (boundary with later phases):

- the `EmbeddingModelPort` (Phase 4 task 70), `HybridRetrieval`
  (Phase 4 task 71), `MultiStageRetrieval` (Phase 4 task 72),
  `GraphExpansion` (Phase 4 task 73), `RerankerPort` (Phase 4 task
  74), metadata-driven filters (Phase 4 task 75),
  `ContextAssembler` (Phase 4 task 76), retrieval benchmark (Phase
  4 task 77) are out of scope. Phase 3 ships the port surfaces
  (`SparseIndexPort`, `DenseIndexPort`, `FullTextIndexPort`,
  `GraphExpansionPort`) so Phase 4 does not have to invent the
  surface area in isolation;
- the query orchestrator, local LLM, task context and capability
  discovery (Phase 5 tasks 79-83) are out of scope;
- the MCP server that exposes the runtime store (Phase 6 task 85) is
  out of scope;
- the Wiki materialisation, control plane, security, distribution,
  A2A (Phase 7+ tasks 86-123) are out of scope.

## Compatibility / migration impact

This change is additive at every public contract surface. No accepted
Phase 1 or Phase 2 capability spec is modified. No Phase 1 value type
(`Chunk`, `ContextualChunk`, `Entity`, `Relation`, `Evidence`,
`Metadata`, `Source`, `ProjectVersion`, `WorkingTreeOverlay`) is
modified; the Phase 1 round-trip invariant
`tests/test_canonical_roundtrip.py` MUST continue to pass byte-for-
byte after this change lands. The Phase 1 + Phase 2 CLI subcommands
(`init-project`, `hydrate`, `materialise`, `license-gate`,
`okf-validate`, `version-identity`, `wal-recover`, `health`,
`ingest-sources`) are unchanged; this change adds exactly two new
subcommands, `runtime-status` and `graph-rebuild`, and does not
modify the existing ones.

New dependencies:

- the default runtime backend uses Python stdlib `sqlite3` only
  (no extra dependency); the PostgreSQL Python driver is opt-in
  (`project-context.yaml:storage.backend == "postgres"`);
- the BM25 default adapter ships as an in-process implementation so
  no `rank-bm25` dependency is required for the default backend;
- the HNSW default adapter ships with a flat-search fallback so
  no `hnswlib` dependency is required for the default backend;
- the secondary full-text index uses SQLite FTS5 (no extra
  dependency);
- this change therefore does NOT add any new dependency inventory
  entries beyond what is already documented in
  `distribution/licenses/dependency-inventory.json`. The future
  Phase 4 retrieval change may add the optional `rank-bm25` and
  `hnswlib` SPDX-tracked entries;
- the Python 3.11 platform source language decision recorded in
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  still holds. No new platform-level language dependency is
  introduced; the storage libraries are adapters under
  `pi_platform/adapters/runtime/`.

OpenSpec conventions:

- the change folder uses lowercase kebab-case without a date
  prefix (`implement-phase-3-storage`);
- the nine Phase 3 spec deltas remain under
  `openspec/changes/prepare-phase-3-storage/specs/2026-10-04-*/`
  until the archive step moves them to
  `openspec/specs/2026-10-04-*/` and renames the change folder to
  `openspec/changes/archive/2026-10-04-prepare-phase-3-storage/`
  per the OpenSpec experimental workflow;
- the archive step archives this implementation change to
  `openspec/changes/archive/2026-10-04-implement-phase-3-storage/`;
- `openspec/CURRENT.md` is updated to list the nine Phase 3
  capabilities under "Project product capabilities" once the
  archive promotes the deltas.

## Related knowledge

- `kb://architecture.platform-overview` — extended with the Phase 3
  module map (`pi_platform/core/runtime/`,
  `pi_platform/ports/runtime/`, `pi_platform/adapters/runtime/`).
- `kb://architecture.system-overview` — extended with the Phase 3
  storage reference.
- `kb://glossary.platform` — extended with `RuntimeStore`,
  `SparseIndex`, `DenseIndex`, `FullTextIndex`, `Graph`,
  `GraphExpansion`, `ProvenanceTracker`, `FreshnessTracker`,
  `KnowledgeState` (state machine), `Shard` (content-addressed
  primary key).
- `kb://glossary.domain` — cross-linked to the platform vocabulary.
- `kb://project.implementation-roadmap` — Phase 3 row flipped from
  `planned` to `complete` on archive.
- `kb://project.project-map` — Phase 3 module folders added under
  "Main source areas".
- `kb://modules.runtime-store`, `kb://modules.graph` — new Wiki
  module maps (Phase 3 surface).
- `kb://interfaces.runtime-store`,
  `kb://interfaces.sparse-index`, `kb://interfaces.dense-index`,
  `kb://interfaces.full-text-index`,
  `kb://interfaces.graph-expansion`,
  `kb://interfaces.provenance`, `kb://interfaces.freshness` — new
  Wiki interface nodes.
- `kb://adr.embedded-storage-selection` — new ADR recording the
  PostgreSQL + SQLite dual-backend (Apache-2.0 / BSD) choice and
  the rejected alternatives (DuckDB MIT, RocksDB Apache-2.0, `sled`
  MPL-2.0, LevelDB BSD-3-Clause, Badger Apache-2.0).
- `kb://adr.platform-source-language` — unchanged; the Phase 3
  storage libraries are adapters under
  `pi_platform/adapters/runtime/`, not new platform-level language
  dependencies.
- `kb://adr.canonical-runtime-separation` — unchanged; the Phase 3
  pipeline respects invariants #1-#4 by writing through the
  per-shard content-addressed cache keyed by the Phase 1 SHA-256
  content address and by reusing the Phase 1 advisory file lock.
- `kb://adr.license-governance-default` — every new dependency
  has an SPDX identifier in
  `distribution/licenses/dependency-inventory.json` and passes
  `LicenseGate` before the adapter is registered (this change adds
  no new dependencies).