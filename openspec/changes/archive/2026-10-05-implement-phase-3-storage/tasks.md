# Tasks — implement-phase-3-storage

This tasks file mirrors the Phase 3 tasks 61–69 from the canonical
[`plan-v0-8-platform-architecture/tasks.md`](../../plan-v0-8-platform-architecture/tasks.md).
The tasks below are the production work for this change.

The 9 Phase 3 capability specs under
[`specs/`](specs) are the authoritative behavioural contract for
the implementation work. The specs are already validated by
`openspec validate prepare-phase-3-storage --type change --strict`
(returned `valid`).

Verification commands referenced below:

- `python -m unittest tests.<module> -v` — focused regression tests;
- `openspec validate implement-phase-3-storage --type change
  --strict` (this change), `openspec validate --all --strict`
  (canonical harness check);
- `python harness.py check` — full harness core gate
  (license-gate, openspec-check, wiki-validate, artifact-manifest).

## Phase 3 — Storage (implementation)

### 3.1 — Embedded storage engine selection (task 61)

- [ ] 61. Select the embedded storage engine(s) capable of
  relational metadata, full-text search, vector search and graph
  traversal within one deployable unit. Document the decision in
  an ADR (`adr.embedded-storage-selection`) and record the license
  rationale.
  → `.ai/wiki/adr/0008-embedded-storage-selection.md` (new ADR;
  the design candidate is **PostgreSQL + SQLite dual-backend**
  with Apache-2.0 / BSD licenses; rejected alternatives include
  DuckDB MIT, RocksDB Apache-2.0, `sled` MPL-2.0, LevelDB
  BSD-3-Clause, Badger Apache-2.0).
  Verification:
  - `python harness.py check` MUST pass;
  - `python -m pi_platform.cli license-gate` MUST pass with no
    unapproved dependencies.

### 3.2 — RuntimeStore (task 62)

- [ ] 62. Implement `platform.runtime.RuntimeStore` with
  per-shard content-addressed cache, version stamp, write-ahead
  log and per-project advisory file lock.
  → `pi_platform/ports/runtime/runtime_store.py` (new port),
  `pi_platform/core/runtime/runtime_store.py` (new core
  re-export), `pi_platform/adapters/runtime/sqlite_runtime_store.py`
  (new default adapter), `pi_platform/runtime/cache.py` (Phase 1
  stub rewritten as a thin shim that delegates to the new default
  adapter).
  Verification:
  - `python -m unittest tests.test_platform_phase3.RuntimeStoreTests -v`
  - the Phase 1 `python -m unittest tests.test_canonical_roundtrip
    -v` MUST continue to pass byte-for-byte;
  - `python -m pi_platform.cli runtime-status` MUST exit zero.

### 3.3 — SparseIndex (task 63)

- [ ] 63. Implement `platform.runtime.SparseIndex` (BM25 or
  equivalent) and metadata index.
  → `pi_platform/ports/runtime/sparse_index.py` (new port),
  `pi_platform/adapters/runtime/bm25_sparse_index.py` (new
  default adapter; in-process BM25, no extra dependency).
  Verification:
  - `python -m unittest tests.test_platform_phase3.SparseIndexTests -v`

### 3.4 — DenseIndex (task 64)

- [ ] 64. Implement `platform.runtime.DenseIndex` with at least one
  ANN backend (HNSW or flat) behind a `DenseIndexPort`.
  → `pi_platform/ports/runtime/dense_index.py` (new port),
  `pi_platform/adapters/runtime/flat_dense_index.py` (new
  in-process flat-search adapter; no extra dependency).
  Verification:
  - `python -m unittest tests.test_platform_phase3.DenseIndexTests -v`

### 3.5 — FullTextIndex (task 65)

- [ ] 65. Implement `platform.runtime.FullTextIndex`.
  → `pi_platform/ports/runtime/full_text_index.py` (new port),
  `pi_platform/adapters/runtime/sqlite_fts_full_text_index.py`
  (new SQLite FTS5 adapter; reuses the SQLite backend from task
  62).
  Verification:
  - `python -m unittest tests.test_platform_phase3.FullTextIndexTests -v`

### 3.6 — ShardedGraph (task 66)

- [ ] 66. Implement the canonical knowledge graph
  (`platform.core.graph.Graph`) with sharded nodes/edges,
  content-addressed entity bodies, entity families from §16 and
  relation families from §16; implement the graph with a clear
  separation between ANN graph and knowledge graph.
  → `pi_platform/ports/runtime/graph.py` (new port),
  `pi_platform/core/runtime/graph.py` (new core re-export),
  `pi_platform/adapters/runtime/sharded_graph.py` (new default
  adapter; hash-prefix shards, 32 MiB per-file cap).
  Verification:
  - `python -m unittest tests.test_platform_phase3.GraphTests -v`
  - `python -m pi_platform.cli graph-rebuild` MUST exit zero.

### 3.7 — KnowledgeState and freshness tracking (task 67)

- [ ] 67. Implement knowledge provenance (`KnowledgeState`) and
  freshness tracking; record the staleness map on every reconcile.
  → `pi_platform/ports/runtime/provenance.py` (new port),
  `pi_platform/ports/runtime/freshness.py` (new port),
  `pi_platform/core/runtime/provenance.py` (new core re-export),
  `pi_platform/core/runtime/freshness.py` (new core re-export),
  `pi_platform/adapters/runtime/provenance_tracker.py` (new
  default adapter),
  `pi_platform/adapters/runtime/last_verified_freshness_tracker.py`
  (new default adapter).
  Verification:
  - `python -m unittest tests.test_platform_phase3.ProvenanceTests -v`
  - `python -m unittest tests.test_platform_phase3.FreshnessTests -v`

### 3.8 — GraphExpansion preview (Phase 4 preview port)

- [ ] 67b. Implement the Phase 4 preview
  `GraphExpansionPort` (seed set, hops, edge-type filter, budget)
  with a stub adapter that documents the contract.
  → `pi_platform/ports/runtime/graph_expansion.py` (new port),
  `pi_platform/adapters/runtime/bounded_graph_expansion.py`
  (new stub adapter).
  Verification:
  - `python -m unittest tests.test_platform_phase3.GraphExpansionTests -v`

### 3.9 — Spec scenarios for Phase 3 slice (tasks 68–69)

- [ ] 68. Add focused regression tests including a 50k-entity
  sharding test that asserts the documented shard counts and the
  32 MiB single-file cap.
  → covered by `tests/test_platform_phase3.GraphTests` and
  `tests/test_graph_50k.py` (new property-based test).
  Verification:
  - `python -m unittest tests.test_graph_50k -v`
  - the Phase 1 `tests/test_canonical_roundtrip.py` and the Phase
    2 `tests/test_platform_phase2.py` and
    `tests/test_content_address_cross_branch.py` MUST continue to
    pass byte-for-byte.

- [ ] 69. Update Wiki (new `modules/runtime-store`, `modules/graph`,
  `interfaces/sparse-index`, `interfaces/dense-index`), archive
  the Phase 3 change, update `openspec/CURRENT.md`.
  → `.ai/wiki/modules/runtime-store.md` (new),
  `.ai/wiki/modules/graph.md` (new),
  `.ai/wiki/interfaces/runtime-store.md` (new),
  `.ai/wiki/interfaces/sparse-index.md` (new),
  `.ai/wiki/interfaces/dense-index.md` (new),
  `.ai/wiki/interfaces/full-text-index.md` (new),
  `.ai/wiki/interfaces/graph-expansion.md` (new),
  `.ai/wiki/interfaces/provenance.md` (new),
  `.ai/wiki/interfaces/freshness.md` (new),
  `.ai/wiki/adr/0008-embedded-storage-selection.md` (new),
  `.ai/wiki/architecture/platform-overview.md` (Phase 3 module
  map), `.ai/wiki/glossary/platform.md` (Phase 3 vocabulary),
  `.ai/wiki/INDEX.md` (new entries), `openspec/CURRENT.md` (the
  nine Phase 3 capabilities added), archive
  `implement-phase-3-storage` under
  `archive/2026-10-04-implement-phase-3-storage/`, flip plan
  tasks 61–69 from `[ ]` to `[x]`.

Verification for the slice (tasks 68–69):

  - `python harness.py wiki-validate` MUST pass;
  - `python harness.py openspec-check` MUST pass;
  - `python harness.py check` MUST pass;
  - `openspec validate implement-phase-3-storage --type change
    --strict` MUST return `valid`.

## Out-of-scope tasks (this change)

The tasks below belong to later phases and are NOT executed by this
change. They are listed here only so the implementation work knows
where to draw the line.

- the embedding model and dense ANN integration — Phase 4 task 70
  (`EmbeddingModelPort`);
- the hybrid retrieval pipeline — Phase 4 task 71
  (`HybridRetrieval`);
- the multi-stage retrieval — Phase 4 task 72
  (`MultiStageRetrieval`);
- the graph-expansion production implementation — Phase 4 task 73
  (`GraphExpansion`; Phase 3 ships the port contract only);
- the reranker, metadata-driven filters, context assembler and
  retrieval benchmark — Phase 4 tasks 74–77;
- the query orchestrator, local LLM, task context and capability
  discovery — Phase 5 tasks 79–83;
- the MCP server exposing the runtime store — Phase 6 task 85;
- the control plane, security, distribution, A2A — Phase 7+ tasks
  86–123.

## Verification of this implementation change

- [ ] `python harness.py check` returns `Harness core checks:
  PASS`.
- [ ] `openspec validate implement-phase-3-storage --type change
  --strict` returns `valid`.
- [ ] `python harness.py wiki-validate` returns `{"ok": true,
  ...}`.
- [ ] `python3 scripts/artifact_manifest.py verify` returns
  `Artifact manifest: PASS`.
- [ ] `python -m pi_platform.cli license-gate` exits zero with
  no unapproved dependencies.
- [ ] `python -m unittest tests.test_platform_phase1
  tests.test_platform_phase2 tests.test_content_address_cross_branch
  tests.test_canonical_roundtrip tests.test_platform_phase3
  tests.test_graph_50k -v` exits zero.
- [ ] `python -m pi_platform.cli runtime-status` exits zero.
- [ ] `python -m pi_platform.cli graph-rebuild` exits zero.

## Implementation close-out

Once the verification gates pass, archive the change with
`openspec archive implement-phase-3-storage -y`. The archive step
promotes the nine Phase 3 spec deltas to
`openspec/specs/2026-10-04-*/`, updates `openspec/CURRENT.md`,
archives the `prepare-phase-3-storage` change as a side effect and
archives this implementation change. The plan change tasks 61–69
flip to `[x]`.