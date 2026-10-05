# Design — prepare-phase-3-storage

## Current state

The repository contains the v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)),
the Phase 1 foundation change archived at
[`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`](../../archive/2026-10-04-implement-phase-1-foundation/),
the Phase 2 ingestion subsystem archived at
[`openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`](../../archive/2026-10-04-implement-phase-2-ingestion/),
the active `plan-v0-8-platform-architecture` change that owns the
Phase 3–10 task ordering, and the 14 accepted Phase 1 + Phase 2
capability specs under `openspec/specs/2026-10-04-*/`:

Phase 1:

- `project-knowledge-repository-layout`
- `canonical-knowledge-schema`
- `git-version-aware-runtime`
- `bidirectional-canonical-runtime-sync`
- `license-governance`

Phase 2:

- `ingestion-pipeline-driver`
- `structured-code-intelligence`
- `jar-dependency-intelligence`
- `document-source-adapters`
- `openspec-change-adapter`
- `local-source-inbox`
- `content-addressed-processing`
- `semantic-structural-chunking`
- `context-enrichment`

The Phase 1 product source tree is in place at `pi_platform/` with
the `core/{canonical,git,sync,licensing}` subpackages, the
`ports/__init__.py` aggregate, the `adapters/{fs,git}` default
adapters, the `runtime/cache.py` Phase 1 placeholder runtime cache
(documenting that Phase 3 replaces it), and the `cli/` entry point
exposing `init-project`, `hydrate`, `materialise`, `license-gate`,
`okf-validate`, `version-identity`, `wal-recover`, `health` and the
Phase 2 `ingest-sources` subcommand.

The Phase 2 production source tree is in place at `pi_platform/` with
the `core/ingest/` subpackage (`pipeline_driver`,
`local_source_inbox_scanner`, `runtime_cache`, `records`, `config`),
the `ports/ingest/` aggregate (eight port modules), and the
per-family `adapters/{fs,markdown,html,pdf,openapi,java,openspec,ingest}/`
adapters. The Phase 2 regression suite
(`tests/test_platform_phase2.py`,
`tests/test_content_address_cross_branch.py`) plus the Phase 1 round-
trip invariant (`tests/test_canonical_roundtrip.py`) and the
full `python harness.py check` gate are green.

The repository does not yet contain any Phase 3 production code under
`pi_platform/runtime/` (only the Phase 1 stub `cache.py`),
`pi_platform/ports/runtime/`, `pi_platform/core/runtime/`,
`pi_platform/adapters/runtime/` or any related Phase 3 module. No
embedded-storage library has been added to
`distribution/licenses/dependency-inventory.json` (the inventory still
holds only the optional `tree-sitter-java` MIT entry added by Phase
2). The Phase 3 task list (`tasks.md` rows 61–69) is still `[ ]` in
the planning change.

## Proposed design

This change is a planning artifact: it ships no production code.
The design below describes the technical approach the future
`implement-phase-3-storage` change will implement, expressed as
module boundaries, port contracts, adapter composition, data flow,
concurrency, compatibility and risks. The design records the
embedded-storage-engine selection rationale, the sharding strategy,
the `KnowledgeState` lifecycle and the freshness-tracking rules so
the implementation work has unambiguous technical contracts.

### RuntimeStore coordinator (§62, §10.2, §64)

The `RuntimeStore` lives in
`pi_platform/core/runtime/runtime_store.py` and exposes a
`RuntimeStorePort` abstract class in
`pi_platform/ports/runtime/runtime_store.py`. The default adapters
live in `pi_platform/adapters/runtime/`:

- `SqliteRuntimeStore` — default embedded backend for the
  desktop-default profile;
- `PostgresRuntimeStore` — optional enterprise-scale backend.

Both adapters are interchangeable behind the same port. The default
selection (SQLite vs. PostgreSQL) is decided by the
`project-context.yaml:storage.backend` value (`sqlite` by default;
`postgres` opt-in) at `init-project` time.

Storage boundaries:

1. **Per-shard content-addressed cache** — every cached artefact is
   keyed by its SHA-256 content address (the Phase 1
   `content_address_bytes` helper); the cache layout mirrors the §10.2
   `objects/<prefix>/<hash>.json` sharding pattern so the runtime and
   canonical representations share the same addressing scheme;
2. **Version stamp** — every write records the
   `VersionIdentity` tuple (`gitHead`, `workingTreeFingerprint`,
   `knowledgeSchemaVersion`, `embeddingModelVersion`,
   `indexSchemaVersion`) from the Phase 1 `git-version-aware-runtime`
   spec, so the `runtime-status` CLI can report which project version
   the store is bound to;
3. **Write-ahead log** — every mutation appends to a per-store WAL
   under `.project-intelligence-cache/wal/` (the Phase 1
   `WriteAheadLog` helper is reused and extended); the
   `wal-recover` Phase 1 CLI command continues to recover the
   materialise flow, and the new `runtime-status` CLI reports the
   outstanding WAL tail length;
4. **Per-project advisory file lock** — the Phase 1
   `pi_platform/core/sync/project_lock.py` advisory lock is reused; no
   new lock primitive is introduced.

Cross-branch reuse:

- the runtime cache is keyed by SHA-256 content address so an
  unchanged artefact is reused across Git branches, satisfying the
  Phase 2 `content-addressed-processing` cross-branch invariant;
- the cache honours `KnowledgeStateFilter.DURABLE` by default
  (`exclude LOCAL_ONLY`), and `KnowledgeStateFilter.ALL` is opt-in
  via the `runtime-status` CLI;
- the cache honours `KnowledgeStateFilter.STALE` via the freshness
  tracking layer below.

### SparseIndex port (§63, §26)

`SparseIndexPort` lives in
`pi_platform/ports/runtime/sparse_index.py`. The default BM25 adapter
lives in `pi_platform/adapters/runtime/bm25_sparse_index.py`.

The port contract:

- `SparseIndexPort.index_document(family: str, documentId: str,
  text: str, metadata: Mapping[str, object]) -> None` — add or
  replace the document's BM25 contribution;
- `SparseIndexPort.delete_document(documentId: str) -> None` — drop
  the document from the index;
- `SparseIndexPort.query(text: str, top_k: int = 10) ->
  Sequence[SparseHit]` where `SparseHit = (documentId, score,
  snippet)`;
- `SparseIndexPort.stats() -> Mapping[str, int]` — returns
  `{"documents": ..., "terms": ..., "bytes": ...}`.

Dependency license (planned):

| Adapter | Dependency | License | LicenseGate action |
|---|---|---|---|
| `Bm25SparseIndex` | `rank-bm25` | MIT | allow |
| `Bm25SparseIndex` (alt) | stdlib only (term-frequency BM25, in-process) | n/a | allow |

The chosen dependency is recorded in
`distribution/licenses/dependency-inventory.json` and passes
`LicenseGate` before the adapter is registered. The default adapter
ships as an in-process BM25 implementation so the `runtime-status`
CLI works without any optional dependency.

### DenseIndex port (§64, §28)

`DenseIndexPort` lives in
`pi_platform/ports/runtime/dense_index.py`. The default HNSW adapter
lives in `pi_platform/adapters/runtime/hnsw_dense_index.py`.

The port contract:

- `DenseIndexPort.index_chunk(chunkId: str, vector:
  Sequence[float], metadata: Mapping[str, object]) -> None`;
- `DenseIndexPort.delete_chunk(chunkId: str) -> None`;
- `DenseIndexPort.query(vector: Sequence[float], top_k: int = 10)
  -> Sequence[DenseHit]` where `DenseHit = (chunkId, score)`;
- `DenseIndexPort.stats() -> Mapping[str, int]`.

Backend selection (planned):

| Adapter | Dependency | License | LicenseGate action |
|---|---|---|---|
| `HnswDenseIndex` | `hnswlib` | MIT | allow |
| `FlatDenseIndex` (fallback) | stdlib only (numpy-compatible, in-process) | BSD-like (numpy) | allow |
| `UsearchDenseIndex` (alt) | `usearch` | Apache-2.0 | allow |

The default adapter ships with a flat-search fallback (numpy-compatible
cosine / dot-product) so the Phase 3 surface and the `runtime-status`
CLI work without any optional dependency. The HNSW adapter is enabled
when `project-context.yaml:storage.denseIndex.backend == "hnsw"`
and the dependency is present; the flat fallback handles the
absent-dependency case.

### FullTextIndex port (§65, §26)

`FullTextIndexPort` lives in
`pi_platform/ports/runtime/full_text_index.py`. The default
secondary-text-index adapter lives in
`pi_platform/adapters/runtime/sqlite_fts_full_text_index.py` and
reuses the SQLite FTS5 module that ships with the SQLite backend.

The port contract:

- `FullTextIndexPort.index_document(family: str, documentId: str,
  text: str, metadata: Mapping[str, object]) -> None`;
- `FullTextIndexPort.delete_document(documentId: str) -> None`;
- `FullTextIndexPort.query(text: str, top_k: int = 10) ->
  Sequence[FullTextHit]` where `FullTextHit = (documentId, score,
  snippet)`;
- `FullTextIndexPort.stats() -> Mapping[str, int]`.

The full-text index is intentionally separate from the
`SparseIndex`: `SparseIndex` exposes BM25-style ranking with chunk
metadata awareness; `FullTextIndex` exposes substring / FTS5-style
ranking that is closer to a database `LIKE` query. The two ports are
composed by the Phase 4 `HybridRetrieval` pipeline.

### ShardedGraph (§66, §10.1, §16, §17)

`GraphPort` lives in `pi_platform/ports/runtime/graph.py`. The
canonical `LocalShardedGraph` adapter lives in
`pi_platform/adapters/runtime/sharded_graph.py` (the file
`pi_platform/core/runtime/graph.py` re-exports the port).

The port contract:

- `GraphPort.upsert_entity(entity: Entity) -> None` — keyed by
  `Entity.id`, atomic across files
- `GraphPort.upsert_relation(relation: Relation) -> None`
- `GraphPort.get_entity(entity_id: str) -> Optional[Entity]`
- `GraphPort.get_relations(entity_id: str, *,
  edge_type: Optional[str] = None, direction: str = "outgoing") ->
  Sequence[Relation]`
- `GraphPort.shard_by(content_hash: str) -> Shard` — returns the
  shard that owns the content address (mod 256 hash-prefix shard)
- `GraphPort.rebuild_manifest() -> GraphManifest` — regenerates the
  §10.3 graph manifest from the on-disk shards

Shard strategy:

- **Hash-prefix shards** — the §10.1 alternative layout
  (`graph/nodes/00/`, `graph/nodes/01/`, …, `graph/nodes/ff/` and
  `graph/edges/00/`, …, `graph/edges/ff/`) is the default; 256 shard
  directories per family keep the per-shard file count bounded;
- **Single-file cap** — every shard directory holds at most one
  entities file (`entities.jsonl.gz`) and one relations file
  (`relations.jsonl.gz`); the gzipped JSONL files cap at 32 MiB
  uncompressed per the §66 documented budget; the
  `tests/test_graph_50k.py` 50 000-entity property test asserts both
  the shard count distribution and the 32 MiB cap (task 68);
- **Content-addressed entity bodies** — every entity body is stored
  by its SHA-256 content address under `objects/<prefix>/<hash>.json`
  so identical entity bodies across branches share one canonical
  artefact;
- **ANN vs. knowledge graph** — the `GraphPort` only operates on the
  knowledge graph (§17 invariant); the `DenseIndexPort` operates on
  the ANN graph. The two remain separate.

### GraphExpansion preview (§73, §31)

`GraphExpansionPort` lives in
`pi_platform/ports/runtime/graph_expansion.py`. The default stub
adapter lives in
`pi_platform/adapters/runtime/bounded_graph_expansion.py` and
implements the bounded budget contract so Phase 4 does not have to
invent the surface area in isolation.

The port contract:

- `GraphExpansionPort.expand(seeds: Sequence[str], *,
  hops: int = 1, edge_types: Optional[Sequence[str]] = None,
  budget: int = 100) -> GraphExpansion` where `GraphExpansion` lists
  `expandedEntities: Sequence[Entity]` and
  `expandedRelations: Sequence[Relation]`;
- `GraphExpansionPort.stats() -> Mapping[str, int]`.

The Phase 3 implementation is a stub that documents the contract and
returns the seed entities unchanged. Phase 4 task 73 implements the
production expansion algorithm.

### Provenance state model (§67, §54)

`KnowledgeState` is the canonical provenance enum. The model lives in
`pi_platform/core/canonical/value_types.py` (Phase 1 value-type
catalogue) and the `ProvenanceTracker` port lives in
`pi_platform/ports/runtime/provenance.py`. The default
`LocalProvenanceTracker` adapter lives in
`pi_platform/adapters/runtime/provenance_tracker.py`.

The state machine:

```text
verified   ──→ inferred   (LLM-derived evidence; deterministic
                         unchanged)
inferred   ──→ stale      (source content changed; old evidence
                         no longer matches)
stale      ──→ verified   (re-derived evidence matches the new
                         source content)
stale      ──→ unknown    (source deleted; canonical snapshot
                         gone)
verified   ──→ conflicting (parallel branch reports a different
                         authoritative value; resolved by the
                         `canonical-vs-runtime` reconciliation
                         flow)
inferred   ──→ unknown    (LLM-disabled; no deterministic
                         evidence remains)
unknown    ──→ inferred   (new evidence becomes available)
```

The port contract:

- `ProvenancePort.transition(entity_id: str, *, from_state:
  KnowledgeState, to_state: KnowledgeState, evidence:
  Mapping[str, object]) -> None` — atomic, content-addressed by
  evidence hash;
- `ProvenancePort.current_state(entity_id: str) ->
  Optional[KnowledgeState]`;
- `ProvenancePort.evidence(entity_id: str) -> Sequence[Evidence]`;
- `ProvenancePort.staleness_map() -> Mapping[str, KnowledgeState]`
  — the legacy-staleness view used by the freshness tracker.

### Freshness tracking (§55, §67)

`FreshnessTrackerPort` lives in
`pi_platform/ports/runtime/freshness.py`. The default
`LastVerifiedFreshnessTracker` adapter lives in
`pi_platform/adapters/runtime/last_verified_freshness_tracker.py`.

The freshness contract:

- every durable fact carries a `lastVerifiedAt: ISO-8601` field;
- the `FreshnessTrackerPort.mark_verified(fact_id: str, *,
  source_hash: str, version: VersionIdentity) -> None` records
  the timestamp;
- the `FreshnessTrackerPort.is_stale(fact_id: str, *,
  current_source_hash: str) -> bool` returns `True` when the
  fact's recorded `source_hash` differs from the current
  `current_source_hash`;
- the `FreshnessTrackerPort.derived_staleness(derived_fact_id:
  str, *, depends_on: Sequence[str]) -> bool` returns `True` when
  any upstream fact is `stale` or `unknown`;
- the `FreshnessTrackerPort.snapshot() -> FreshnessSnapshot`
  records the per-fact `lastVerifiedAt` and the current
  `current_source_hash` so a subsequent reconcile can replay the
  freshness delta without re-reading every fact.

The reconcile flow (§62 conceptual flow step 14, "Detect stale
durable knowledge") uses `FreshnessTrackerPort.snapshot()` to
populate `ReconcileReport.stale_fact_ids` and the
`KnowledgeStateFilter.STALE` projection. The `runtime-status` CLI
reports the current snapshot so an operator can inspect staleness
without running a full reconcile.

### Embedded-storage selection (§61)

`embedded-storage-selection` is the ADR slot for the runtime DB
engine. The design candidate is **PostgreSQL + SQLite dual-backend**
(Apache-2.0 / BSD) for the following reasons:

- the §61 constraint forbids Elasticsearch, Neo4j, Qdrant and
  PostgreSQL for the *default* desktop deployment. The platform
  therefore ships the SQLite backend as the default; PostgreSQL is
  opt-in for the enterprise-scale profile;
- SQLite (BSD-3-Clause-ish public domain) ships in the Python stdlib
  (`sqlite3`) so no extra runtime dependency is required for the
  default backend;
- the PostgreSQL backend (`psycopg` Apache-2.0) is opt-in for the
  enterprise-scale profile and is gated on the project-context.yaml
  `storage.backend: postgres` configuration plus a LicenseGate pass;
- both backends expose the same `RuntimeStorePort` so adapters and
  the rest of the platform stay backend-agnostic.

Rejected alternatives (recorded in the future
`embedded-storage-selection` ADR):

- **DuckDB** (MIT) — strong analytical SQL, weak at concurrent
  writes; the runtime store is write-heavy (every Phase 2 ingestion
  appends to the WAL). Rejected for the default backend;
- **RocksDB** (Apache-2.0) — strong key-value performance, no
  relational queries, no full-text integration. Would require a
  second relational engine alongside the KV store, violating the §61
  "one embedded engine" preference;
- **`sled`** (MPL-2.0) — embedded Rust KV store. Rejected for two
  reasons: (a) MPL-2.0 is on the Phase 1 `review` license list and
  would force every distribution ship to carry a per-file licence
  review; (b) no relational queries;
- **LevelDB** (BSD-3-Clause) — KV-only. Same relational-query gap
  as RocksDB. Rejected;
- **Badger** (Apache-2.0) — Go KV store; not embeddable from a
  Python adapter without a sidecar.

The ADR records the rationale and the rejected alternatives so a
future contributor who revisits the choice has the documented
trade-off matrix.

## Affected modules / interfaces

| Module / path | Phase | Touched by |
|---|---|---|
| `pi_platform/ports/runtime/` (new) | 3 | RuntimeStorePort, SparseIndexPort, DenseIndexPort, FullTextIndexPort, GraphPort, GraphExpansionPort, ProvenancePort, FreshnessTrackerPort |
| `pi_platform/core/runtime/` (new) | 3 | RuntimeStore, Graph, Provenance, Freshness core implementations |
| `pi_platform/adapters/runtime/` (new) | 3 | SqliteRuntimeStore, PostgresRuntimeStore, Bm25SparseIndex, HnswDenseIndex, FlatDenseIndex, SqliteFtsFullTextIndex, LocalShardedGraph, BoundedGraphExpansion, LocalProvenanceTracker, LastVerifiedFreshnessTracker |
| `pi_platform/runtime/cache.py` (replace) | 3 | Phase 1 stub replaced by the SQLite-backed RuntimeStore; `RuntimeCache` continues to expose the same `put`/`get`/`has`/`evict`/`stats` surface for backward compatibility |
| `tests/test_platform_phase3.py` (new) | 3 | per-port regression suite |
| `tests/test_graph_50k.py` (new) | 3 | 50 000-entity property test (task 68) |
| `distribution/licenses/dependency-inventory.json` | 3 | SPDX-tracked entries for the chosen runtime storage libraries |
| `pi_platform/cli/main.py` (extend) | 3 | `runtime-status`, `graph-rebuild` subcommands |
| `Containerfile` (extend) | 3 | install steps for the new Python packages |
| `openspec/changes/prepare-phase-3-storage/` (new) | 0 | this change (planning only) |

The Phase 1 + Phase 2 ports in `pi_platform/ports/` stay
language-neutral; no new port acquires a database-runtime dependency.
The storage engines are supplied as adapters under
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
Per-shard cache (objects/<prefix>/<hash>.json)
       ↓
SparseIndexPort.index_document  ──→  BM25 / metadata index
FullTextIndexPort.index_document ──→  secondary text index
DenseIndexPort.index_chunk        ──→  HNSW / flat ANN index
GraphPort.upsert_entity           ──→  sharded graph nodes/edges
ProvenancePort.transition         ──→  KnowledgeState transitions
FreshnessTrackerPort.mark_verified ──→  lastVerifiedAt + source_hash
```

The runtime cache is owned by the Phase 3 `RuntimeStore`. The Phase 2
driver hands the content-addressed chunks and entities/relations to
the store; the store then fans them out to the indexes and the graph.

### Persistence

- canonical knowledge still lives under `project-knowledge/` per the
  Phase 1 `project-knowledge-repository-layout` spec;
- the runtime cache lives under `.project-intelligence-cache/` and is
  owned by the Phase 3 `RuntimeStore`;
- the per-shard graph shards live under
  `.project-intelligence-cache/graph/{nodes,edges}/<prefix>/` with
  the gzipped JSONL body files capped at 32 MiB uncompressed;
- the WAL lives under `.project-intelligence-cache/wal/` (reused
  from the Phase 1 `WriteAheadLog` helper);
- the per-project advisory file lock from
  `pi_platform/core/sync/project_lock.py` is reused; no new lock
  primitive is introduced.

### Concurrency

- the `RuntimeStore` serialises mutation per target project via the
  Phase 1 advisory file lock;
- multiple stores MAY run in parallel against different target
  projects;
- the SQLite backend uses `BEGIN IMMEDIATE` to acquire the
  write-lock at the start of a mutation so concurrent readers do
  not block writers;
- the PostgreSQL backend uses the documented isolation level
  (`READ COMMITTED`) and serialises mutations through the same
  per-project advisory file lock so the cross-process WAL tail is
  consistent.

### Cancellation

- the runtime store does not observe a `CancellationToken` directly;
  the Phase 2 driver observes the token and stops calling the store;
- the WAL records partial mutations and the `wal-recover` CLI
  command continues to recover the partial state.

## Compatibility and migration

- the Phase 1 round-trip test in `tests/test_canonical_roundtrip.py`
  MUST continue to pass after Phase 3 introduces the storage layers
  (no schema breakage);
- the Phase 2 regression suite in `tests/test_platform_phase2.py`
  MUST continue to pass after Phase 3 introduces the storage layers
  (the Phase 2 driver writes through the Phase 3 `RuntimeStorePort`,
  but the Phase 2 `InMemoryRuntimeCache` is preserved for tests);
- the Phase 1 license gate MUST pass after the new dependency
  inventory entries (PostgreSQL Python driver, HNSW library, BM25
  library) land in
  `distribution/licenses/dependency-inventory.json`;
- the Phase 1 CLI (`init-project`, `hydrate`, `materialise`,
  `license-gate`, `okf-validate`, `version-identity`, `wal-recover`,
  `health`, `ingest-sources`) is unchanged; Phase 3 MAY add new
  `runtime-status` and `graph-rebuild` CLI commands but does not
  modify the existing ones;
- `openspec/CURRENT.md` is updated by the future
  `implement-phase-3-storage` change when the nine Phase 3 specs are
  adopted, not by this change;
- the Phase 1 `RuntimeCache` placeholder
  (`pi_platform/runtime/cache.py`) is replaced by the Phase 3
  SQLite-backed default; the public `put` / `get` / `has` / `evict` /
  `stats` surface stays backward-compatible.

## Risks and rollback

Risks:

- choosing the wrong runtime DB engine could lock in a poor
  write-throughput characteristic. Mitigated by the dual-backend
  design (SQLite default, PostgreSQL opt-in) and the documented
  rationale in the future `embedded-storage-selection` ADR;
- accepting a GPL-family storage library by mistake would break the
  Phase 1 permissive license policy. Mitigated by requiring every
  new dependency to be SPDX-tracked and pass `LicenseGate` before
  the adapter is registered, and by running the Phase 1
  `LicenseGateTests.test_gate_fails_on_unknown_license` and
  `test_gate_review_without_token_blocks_build` tests;
- the sharded graph could exceed the 32 MiB single-file cap on
  projects with very large entity counts. Mitigated by the
  `tests/test_graph_50k.py` property test (task 68) that asserts the
  cap and the per-shard file-count budget;
- the `KnowledgeState` transition rules could over-eagerly mark
  derived facts as `stale`. Mitigated by the explicit
  `derived_staleness` rule that only marks derived facts stale when
  an upstream fact is stale or unknown;
- the HNSW / flat-ANN fallback could over-rank similar chunks.
  Mitigated by the §28 documented "ANN is an implementation choice"
  invariant and the Phase 4 retrieval benchmark that records
  recall/precision.

Rollback:

- this change reverts cleanly by deleting
  `openspec/changes/prepare-phase-3-storage/` and the
  `.openspec.yaml` registration; the Phase 1 and Phase 2 surfaces are
  unchanged;
- before the future `implement-phase-3-storage` change is adopted,
  there is no runtime artifact to roll back;
- after the future implementation change is adopted, the Phase 3
  code reverts by archiving the implementation change back to a
  Phase-3 pre-state and removing the new dependency inventory
  entries (the LicenseGate rejects activation when entries are
  missing).