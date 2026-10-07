# Design — implement-phase-3-storage

## Current state

The Phase 1 foundation is shipped and green; the Phase 2 ingestion
subsystem is shipped and green:

- the 14 accepted Phase 1 + Phase 2 capability specs live under
  `openspec/specs/2026-10-04-*/` (Phase 1: `project-knowledge-
  repository-layout`, `canonical-knowledge-schema`,
  `git-version-aware-runtime`, `bidirectional-canonical-runtime-
  sync`, `license-governance`; Phase 2: `ingestion-pipeline-driver`,
  `structured-code-intelligence`, `jar-dependency-intelligence`,
  `document-source-adapters`, `openspec-change-adapter`,
  `local-source-inbox`, `content-addressed-processing`,
  `semantic-structural-chunking`, `context-enrichment`);
- the `pi_platform/` Python 3.11 package is in place with the
  Phase 1 `core/{canonical,git,sync,licensing}` subpackages, the
  `ports/__init__.py` and `ports/ingest/` aggregate, the
  `adapters/{fs,git,markdown,html,pdf,openapi,java,openspec,ingest}`
  default adapters, the `runtime/cache.py` Phase 1 stub
  (documented as a Phase 1 placeholder that Phase 3 replaces) and
  the `cli/` entry point exposing `init-project`, `hydrate`,
  `materialise`, `license-gate`, `okf-validate`, `version-identity`,
  `wal-recover`, `health` and the Phase 2 `ingest-sources`
  subcommand;
- the Phase 1 + Phase 2 regression suite (200+ tests) and the
  `python harness.py check` gate are green;
- the nine Phase 3 capability specs are proposed and validated
  under `openspec/changes/prepare-phase-3-storage/specs/2026-10-04-*/`
  and mirrored under
  `openspec/changes/implement-phase-3-storage/specs/2026-10-04-*/`
  (copied verbatim so the implementation change carries the same
  delta set during archive).

The repository does not yet contain any Phase 3 production code
under `pi_platform/ports/runtime/`, `pi_platform/core/runtime/`,
`pi_platform/adapters/runtime/` or any related Phase 3 module. No
runtime storage library has been added to
`distribution/licenses/dependency-inventory.json`. The Phase 3 task
list (`plan-v0-8-platform-architecture/tasks.md` rows 61–69) is
still `[ ]`.

The Phase 1 round-trip invariant
`tests/test_canonical_roundtrip.py` is the canonical guard against
schema breakage. It MUST remain green byte-for-byte after this
change lands. The Phase 2 regression suite
`tests/test_platform_phase2.py` plus the property-based cross-branch
reuse test `tests/test_content_address_cross_branch.py` MUST also
remain green byte-for-byte.

## Proposed design

This change implements the Phase 3 production surface documented in
the design baseline at
[`openspec/changes/prepare-phase-3-storage/design.md`](../../changes/prepare-phase-3-storage/design.md).
The design below records the concrete module skeleton (file paths,
class names, exception hierarchy, lock-acquisition pattern) and the
per-test file list that the change creates. The semantic design
(RuntimeStore coordinator, SparseIndex / FullTextIndex / DenseIndex
port contracts, sharded-graph hash-prefix shards, KnowledgeState
state machine, freshness snapshot, embedded-storage selection) is
unchanged from `prepare-phase-3-storage/design.md`; this document
does NOT duplicate that rationale.

### Module skeleton

```
pi_platform/ports/runtime/
  runtime_store.py        # RuntimeStorePort, RuntimeStoreError,
                          # RuntimeEntry, RuntimeStatusReport
  sparse_index.py         # SparseIndexPort, SparseHit
  dense_index.py          # DenseIndexPort, DenseHit
  full_text_index.py      # FullTextIndexPort, FullTextHit
  graph.py                # GraphPort, GraphManifest, Shard,
                          # GraphPortError
  graph_expansion.py      # GraphExpansionPort, GraphExpansion,
                          # GraphExpansionError
  provenance.py           # ProvenancePort, ProvenanceEvent,
                          # ProvenanceError
  freshness.py            # FreshnessTrackerPort, FreshnessSnapshot,
                          # FreshnessError

pi_platform/core/runtime/
  runtime_store.py        # core coordinator (no DB; port-only)
  graph.py                # core graph port re-export
  provenance.py           # core provenance port re-export
  freshness.py            # core freshness port re-export

pi_platform/adapters/runtime/
  sqlite_runtime_store.py  # default RuntimeStorePort impl
                          # (sqlite3 stdlib; SHA-256 content
                          # addressing; WAL)
  bm25_sparse_index.py     # default SparseIndexPort impl
                          # (in-process BM25; no extra dependency)
  flat_dense_index.py      # default DenseIndexPort impl
                          # (in-process flat-search fallback;
                          # no extra dependency)
  sqlite_fts_full_text_index.py
                          # default FullTextIndexPort impl
                          # (SQLite FTS5; no extra dependency)
  sharded_graph.py         # default GraphPort impl
                          # (hash-prefix shards; 32 MiB per-file
                          # cap; gzipped JSONL)
  bounded_graph_expansion.py
                          # Phase 4 preview stub
  provenance_tracker.py    # default ProvenancePort impl
  last_verified_freshness_tracker.py
                          # default FreshnessTrackerPort impl
```

### Class / port / exception summary

| Path | Primary symbols |
|---|---|
| `pi_platform/ports/runtime/runtime_store.py` | `RuntimeStorePort`, `RuntimeStoreError`, `RuntimeEntry`, `RuntimeStatusReport` |
| `pi_platform/ports/runtime/sparse_index.py` | `SparseIndexPort`, `SparseHit` |
| `pi_platform/ports/runtime/dense_index.py` | `DenseIndexPort`, `DenseHit` |
| `pi_platform/ports/runtime/full_text_index.py` | `FullTextIndexPort`, `FullTextHit` |
| `pi_platform/ports/runtime/graph.py` | `GraphPort`, `GraphManifest`, `Shard`, `GraphPortError` |
| `pi_platform/ports/runtime/graph_expansion.py` | `GraphExpansionPort`, `GraphExpansion`, `GraphExpansionError` |
| `pi_platform/ports/runtime/provenance.py` | `ProvenancePort`, `ProvenanceEvent`, `ProvenanceError` |
| `pi_platform/ports/runtime/freshness.py` | `FreshnessTrackerPort`, `FreshnessSnapshot`, `FreshnessError` |
| `pi_platform/adapters/runtime/sqlite_runtime_store.py` | `SqliteRuntimeStore` (default `RuntimeStorePort` impl) |
| `pi_platform/adapters/runtime/bm25_sparse_index.py` | `Bm25SparseIndex` (default `SparseIndexPort` impl) |
| `pi_platform/adapters/runtime/flat_dense_index.py` | `FlatDenseIndex` (default `DenseIndexPort` impl) |
| `pi_platform/adapters/runtime/sqlite_fts_full_text_index.py` | `SqliteFtsFullTextIndex` (default `FullTextIndexPort` impl) |
| `pi_platform/adapters/runtime/sharded_graph.py` | `LocalShardedGraph` (default `GraphPort` impl) |
| `pi_platform/adapters/runtime/bounded_graph_expansion.py` | `BoundedGraphExpansion` (Phase 4 preview stub) |
| `pi_platform/adapters/runtime/provenance_tracker.py` | `LocalProvenanceTracker` (default `ProvenancePort` impl) |
| `pi_platform/adapters/runtime/last_verified_freshness_tracker.py` | `LastVerifiedFreshnessTracker` (default `FreshnessTrackerPort` impl) |

Exception hierarchy:

- `RuntimeStoreError` (parent) — `ContentAddressCollision`,
  `WALTailCorrupt`, `VersionStampMismatch`,
  `ProjectLockTimeout`;
- `SparseIndexError` (parent) — `DocumentMissing`,
  `MetadataMismatch`;
- `DenseIndexError` (parent) — `ChunkIdMissing`,
  `DimensionMismatch`, `BackendMissing`;
- `FullTextIndexError` (parent) — `DocumentMissing`,
  `BackendMissing`;
- `GraphPortError` (parent) — `EntityMissing`,
  `ShardCapExceeded`, `ManifestStale`;
- `GraphExpansionError` (parent) — `BudgetExhausted`,
  `EdgeTypeUnsupported`;
- `ProvenanceError` (parent) — `TransitionForbidden`,
  `EvidenceChainBroken`;
- `FreshnessError` (parent) — `SnapshotCorrupt`,
  `DerivedStalenessLoop`.

### Per-shard content-addressed cache

The `SqliteRuntimeStore` reuses the Phase 1 `content_address_bytes`
helper. Every cache entry is keyed by its SHA-256 hex digest; the
cache layout mirrors the §10.2
`objects/<prefix>/<hash>.json` sharding pattern (256 hash-prefix
directories). The store writes through the WAL
(`.project-intelligence-cache/wal/`) and reads under the Phase 1
advisory file lock from `pi_platform/core/sync/project_lock.py`.

The Phase 1 `pi_platform/runtime/cache.py` stub is preserved for
backward compatibility: the `put` / `get` / `has` / `evict` /
`stats` surface stays unchanged; the new default implementation is
the `SqliteRuntimeStore` adapter; the stub is rewritten to
delegate to the new adapter through a thin shim so existing
callers (init-project, hydrate, materialise, ingest-sources)
continue to work without modification.

### SparseIndex

The `Bm25SparseIndex` is an in-process BM25 implementation that
does NOT require the `rank-bm25` MIT library. The implementation
keeps the term-frequency / inverse-document-frequency tables in
memory and rebuilds incrementally as documents are added or
removed. The `query` operation applies metadata-aware scoring per
the `sparse-index` spec.

### DenseIndex

The `FlatDenseIndex` is an in-process flat-search implementation
that does NOT require the `hnswlib` MIT library. The
implementation keeps the embeddings in a numpy-compatible
in-memory array (or a pure-Python fallback when numpy is not
available) and computes cosine similarity by brute force. The
HNSW adapter is a future Phase 4 addition gated on the
`hnswlib` dependency.

### FullTextIndex

The `SqliteFtsFullTextIndex` reuses the SQLite FTS5 module that
ships with the `SqliteRuntimeStore` backend. The full-text index
is backed by a separate virtual table
(`runtime_fulltext_fts`) inside the same SQLite database file.

### ShardedGraph

The `LocalShardedGraph` uses the §10.1 hash-prefix shard layout
(`graph/nodes/<prefix>/` and `graph/edges/<prefix>/`) with
gzipped JSONL body files capped at 32 MiB uncompressed. The
50 000-entity property test (`tests/test_graph_50k.py`) asserts
both the shard count distribution and the 32 MiB cap.

The graph stores:

- entity families from §16 (`Requirement`, `Specification`,
  `OpenSpecChange`, `ADR`, `BusinessConcept`, `Component`,
  `Module`, `JavaClass`, `JavaMethod`, `Interface`, `API`,
  `Dependency`, `DatabaseTable`, `Protocol`, `Test`,
  `DocumentationSource`, `Document`, `Section`, `Chunk`);
- relation families from §16 (`IMPLEMENTS`, `SATISFIES`,
  `DEPENDS_ON`, `CALLS`, `USES`, `IMPLEMENTED_BY`, `DEFINED_BY`,
  `PART_OF`, `DOCUMENTED_BY`, `TESTED_BY`, `REFERENCES`,
  `SUPERSEDES`, `DESCRIBES`);
- the `Shard.contentHash` primary key (every entity body is
  stored by its SHA-256 content address under
  `objects/<prefix>/<hash>.json` so identical entity bodies
  across branches share one canonical artefact).

The graph keeps the ANN graph vs. knowledge graph separation
(§17 invariant); the dense index has no notion of `Entity` or
`Relation` families, and the graph has no notion of vector
similarity.

### GraphExpansion preview

The `BoundedGraphExpansion` is a Phase 4 preview stub that
documents the port contract and returns the seed entities
unchanged. Phase 4 task 73 implements the production expansion
algorithm.

### KnowledgeState and provenance

The `LocalProvenanceTracker` is the default `ProvenancePort`
implementation. It enforces the state machine:

```text
verified   ──→ inferred   (LLM-derived evidence)
inferred   ──→ stale      (source content changed)
stale      ──→ verified   (re-derived evidence matches)
stale      ──→ unknown    (source deleted)
verified   ──→ conflicting (parallel branch reports a
                         different authoritative value)
inferred   ──→ unknown    (LLM-disabled)
unknown    ──→ inferred   (new evidence becomes available)
```

The state is recorded in a dedicated SQLite table
(`runtime_provenance_state`); the evidence chain is recorded in
a separate SQLite table (`runtime_provenance_evidence`) so the
chain is replayable.

### Freshness tracking

The `LastVerifiedFreshnessTracker` is the default
`FreshnessTrackerPort` implementation. It records every
`mark_verified` call in a SQLite table
(`runtime_freshness_state`) with the `lastVerifiedAt` timestamp
and the `source_hash`. The `is_stale` operation compares the
recorded `source_hash` to the supplied `current_source_hash` and
returns `True` when they differ. The `derived_staleness` operation
delegates to the `ProvenancePort.current_state` call for every
upstream fact and returns `True` when any upstream is `stale` or
`unknown`.

The reconcile flow consumes `FreshnessTrackerPort.snapshot()` to
populate `ReconcileReport.stale_fact_ids` and the
`KnowledgeStateFilter.STALE` projection. The `runtime-status`
CLI subcommand reports the current snapshot so an operator can
inspect staleness without running a full reconcile.

### CLI subcommands

The change extends `pi_platform/cli/main.py` with two new
subcommands:

- `runtime-status` — prints the `RuntimeStatusReport` from the
  default `RuntimeStorePort` adapter (bound `VersionIdentity`,
  cache entry count, WAL tail length, stale fact count, active
  dense index backend, active storage backend);
- `graph-rebuild` — calls `GraphPort.rebuild_manifest()` and
  prints the regenerated `GraphManifest`.

Both subcommands honour `--target` and `--cache-root` flags so
they fit the existing CLI conventions.

### Containerfile

The change extends the `Containerfile` with the documented
install steps for the chosen storage libraries. The default
runtime uses Python stdlib `sqlite3` only, so the default
`Containerfile` does NOT add any new `pip install` lines; the
optional PostgreSQL backend install step is documented but
gated on the SPDX-tracked license inventory entry.

## Affected modules / interfaces

| Module / path | Phase | Touched by |
|---|---|---|
| `pi_platform/ports/runtime/` (new) | 3 | RuntimeStorePort, SparseIndexPort, DenseIndexPort, FullTextIndexPort, GraphPort, GraphExpansionPort, ProvenancePort, FreshnessTrackerPort |
| `pi_platform/core/runtime/` (new) | 3 | RuntimeStore, Graph, Provenance, Freshness core implementations |
| `pi_platform/adapters/runtime/` (new) | 3 | SqliteRuntimeStore, Bm25SparseIndex, FlatDenseIndex, SqliteFtsFullTextIndex, LocalShardedGraph, BoundedGraphExpansion, LocalProvenanceTracker, LastVerifiedFreshnessTracker |
| `pi_platform/runtime/cache.py` (shim) | 3 | Phase 1 stub preserved; thin shim delegates to the new default adapter |
| `tests/test_platform_phase3.py` (new) | 3 | per-port regression suite |
| `tests/test_graph_50k.py` (new) | 3 | 50 000-entity property test (task 68) |
| `distribution/licenses/dependency-inventory.json` | 3 | no new entries (default backend is stdlib-only) |
| `pi_platform/cli/main.py` (extend) | 3 | `runtime-status`, `graph-rebuild` subcommands |
| `Containerfile` (extend) | 3 | documented install steps for the optional PostgreSQL backend |
| `openspec/changes/implement-phase-3-storage/` (new) | 0 | this change |
| `.ai/wiki/modules/runtime-store.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/modules/graph.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/interfaces/runtime-store.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/interfaces/sparse-index.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/interfaces/dense-index.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/interfaces/full-text-index.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/interfaces/graph-expansion.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/interfaces/provenance.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/interfaces/freshness.md` (new) | 3 | Phase 3 surface |
| `.ai/wiki/adr/0008-embedded-storage-selection.md` (new) | 3 | ADR slot |

The Phase 1 + Phase 2 ports in `pi_platform/ports/` stay
language-neutral; no new port acquires a database-runtime
dependency. The storage engines are supplied as adapters under
`pi_platform/adapters/runtime/`.

## Data / persistence / concurrency impact

### Data flow

```
PipelineDriver (Phase 2)
       ↓
RuntimeStorePort.put(family, body)
       ↓
ContentAddress (Phase 1) → SHA-256 hex digest
       ↓
SqliteRuntimeStore (Phase 3 default) → per-shard cache
       ↓
SparseIndexPort.index_document   ──→  BM25 (in-process)
FullTextIndexPort.index_document ──→  SQLite FTS5
DenseIndexPort.index_chunk        ──→  flat-search (in-process)
GraphPort.upsert_entity           ──→  hash-prefix shards
ProvenancePort.transition         ──→  KnowledgeState table
FreshnessTrackerPort.mark_verified ──→  lastVerifiedAt table
```

The runtime cache is owned by the Phase 3 `RuntimeStore`. The
Phase 2 driver hands the content-addressed chunks and entities
/ relations to the store; the store then fans them out to the
indexes and the graph.

### Persistence

- canonical knowledge still lives under `project-knowledge/`
  per the Phase 1 `project-knowledge-repository-layout` spec;
- the runtime cache lives under `.project-intelligence-cache/`
  and is owned by the Phase 3 `RuntimeStore`. The SQLite database
  file is `.project-intelligence-cache/runtime.db`;
- the per-shard graph shards live under
  `.project-intelligence-cache/graph/{nodes,edges}/<prefix>/`
  with the gzipped JSONL body files capped at 32 MiB
  uncompressed;
- the WAL lives under `.project-intelligence-cache/wal/` (reused
  from the Phase 1 `WriteAheadLog` helper);
- the per-project advisory file lock from
  `pi_platform/core/sync/project_lock.py` is reused; no new lock
  primitive is introduced.

### Concurrency

- the `RuntimeStore` serialises mutation per target project via
  the Phase 1 advisory file lock;
- multiple stores MAY run in parallel against different target
  projects;
- the SQLite backend uses `BEGIN IMMEDIATE` to acquire the
  write-lock at the start of a mutation so concurrent readers do
  not block writers;
- the PostgreSQL backend uses the documented isolation level
  (`READ COMMITTED`) and serialises mutations through the same
  per-project advisory file lock so the cross-process WAL tail
  is consistent.

### Cancellation

- the runtime store does not observe a `CancellationToken`
  directly; the Phase 2 driver observes the token and stops
  calling the store;
- the WAL records partial mutations and the `wal-recover` CLI
  command continues to recover the partial state.

## Compatibility and migration

- the Phase 1 round-trip test in
  `tests/test_canonical_roundtrip.py` MUST continue to pass
  after Phase 3 introduces the storage layers (no schema
  breakage);
- the Phase 2 regression suite in `tests/test_platform_phase2.py`
  MUST continue to pass after Phase 3 introduces the storage
  layers (the Phase 2 driver writes through the Phase 3
  `RuntimeStorePort`, but the Phase 2 `InMemoryRuntimeCache` is
  preserved for tests);
- the Phase 1 license gate MUST pass (this change adds NO new
  dependencies);
- the Phase 1 + Phase 2 CLI subcommands (`init-project`,
  `hydrate`, `materialise`, `license-gate`, `okf-validate`,
  `version-identity`, `wal-recover`, `health`, `ingest-sources`)
  are unchanged; this change adds exactly two new subcommands,
  `runtime-status` and `graph-rebuild`, and does not modify the
  existing ones;
- `openspec/CURRENT.md` is updated to list the nine Phase 3
  capabilities when this change is archived;
- the Phase 1 `RuntimeCache` placeholder
  (`pi_platform/runtime/cache.py`) is rewritten as a thin shim
  that delegates to the new default `SqliteRuntimeStore`
  adapter; the public `put` / `get` / `has` / `evict` / `stats`
  surface stays backward-compatible.

## Risks and rollback

Risks:

- choosing the wrong runtime DB engine could lock in a poor
  write-throughput characteristic. Mitigated by the dual-
  backend design (SQLite default, PostgreSQL opt-in) and the
  documented rationale in the future
  `embedded-storage-selection` ADR;
- the sharded graph could exceed the 32 MiB single-file cap on
  projects with very large entity counts. Mitigated by the
  `tests/test_graph_50k.py` property test (task 68) that asserts
  the cap and the per-shard file-count budget;
- the `KnowledgeState` transition rules could over-eagerly mark
  derived facts as `stale`. Mitigated by the explicit
  `derived_staleness` rule that only marks derived facts stale
  when an upstream fact is stale or unknown;
- the in-process BM25 / flat-search fallback could over-rank
  similar chunks. Mitigated by the §28 documented "ANN is an
  implementation choice" invariant and the Phase 4 retrieval
  benchmark that records recall/precision.

Rollback:

- this change reverts cleanly by deleting
  `openspec/changes/implement-phase-3-storage/` and the new
  `pi_platform/ports/runtime/`, `pi_platform/core/runtime/`,
  `pi_platform/adapters/runtime/` modules;
- the Phase 1 `RuntimeCache` shim must be reverted to its
  pre-Phase-3 state so the Phase 1 round-trip test continues to
  pass byte-for-byte;
- before the change is archived, there is no production
  artefact to roll back beyond the new module folders;
- after the change is archived, the code reverts by archiving
  the implementation change back to a Phase-3 pre-state and
  rolling back the new dependency inventory entries (none in
  this change).