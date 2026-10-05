---
id: modules.runtime-store
title: Phase 3 runtime store module map
kind: modules
status: active
summary: Runtime store, three indexes, sharded graph, provenance and freshness layers.
sourceRefs:
  - pi_platform/ports/runtime/
  - pi_platform/core/runtime/
  - pi_platform/adapters/runtime/
  - pi_platform/runtime/cache.py
maintenance:
  mode: authored
---

# Phase 3 runtime-store modules

The Phase 3 storage layer hosts the canonical chunks and entity /
relation records that the Phase 2 ingestion subsystem produces. The
storage surface ships as a port-and-adapter pair: ports under
`pi_platform/ports/runtime/`, core re-exports under
`pi_platform/core/runtime/`, default adapters under
`pi_platform/adapters/runtime/`.

## Port modules (`pi_platform/ports/runtime/`)

- `runtime_store.py` — `RuntimeStorePort`, `RuntimeStoreError`,
  `RuntimeEntry`, `RuntimeStatusReport`,
  `KnowledgeStatePolicy` (`DURABLE` / `ALL` / `STALE`).
- `sparse_index.py` — `SparseIndexPort`, `SparseHit`.
- `dense_index.py` — `DenseIndexPort`, `DenseHit`.
- `full_text_index.py` — `FullTextIndexPort`, `FullTextHit`.
- `graph.py` — `GraphPort`, `GraphManifest`, `Shard`,
  `GraphPortError`.
- `graph_expansion.py` — `GraphExpansionPort`,
  `GraphExpansion` (Phase 4 preview).
- `provenance.py` — `ProvenancePort`, `ProvenanceEvent`.
- `freshness.py` — `FreshnessTrackerPort`, `FreshnessSnapshot`,
  `FreshnessFact`.

## Core modules (`pi_platform/core/runtime/`)

- `runtime_store.py` — re-export the `RuntimeStorePort` symbols.
- `graph.py` — re-export the `GraphPort` symbols.
- `provenance.py` — re-export the `ProvenancePort` symbols.
- `freshness.py` — re-export the `FreshnessTrackerPort` symbols.

## Adapter modules (`pi_platform/adapters/runtime/`)

- `sqlite_runtime_store.py` — `SqliteRuntimeStore` (default
  `RuntimeStorePort` impl; stdlib `sqlite3`; SHA-256 content
  addressing; per-shard cache; WAL; advisory file lock).
- `bm25_sparse_index.py` — `Bm25SparseIndex` (default
  `SparseIndexPort` impl; in-process BM25; no extra dependency).
- `flat_dense_index.py` — `FlatDenseIndex` (default
  `DenseIndexPort` impl; in-process cosine similarity; no extra
  dependency).
- `sqlite_fts_full_text_index.py` — `SqliteFtsFullTextIndex`
  (default `FullTextIndexPort` impl; SQLite FTS5; reuses the SQLite
  backend).
- `sharded_graph.py` — `LocalShardedGraph` (default `GraphPort`
  impl; hash-prefix shards; one JSONL body file per prefix dir;
  32 MiB per-file cap).
- `bounded_graph_expansion.py` — `BoundedGraphExpansion` (Phase 4
  preview stub).
- `provenance_tracker.py` — `LocalProvenanceTracker` (default
  `ProvenancePort` impl; SQLite-backed state machine).
- `last_verified_freshness_tracker.py` —
  `LastVerifiedFreshnessTracker` (default `FreshnessTrackerPort`
  impl; SQLite-backed).

## Backward compatibility shim

`pi_platform/runtime/cache.py` is the Phase 1 placeholder runtime
cache. Phase 3 rewrites it as a thin shim that delegates to the
default `SqliteRuntimeStore` adapter. The public `put` / `get` /
`has` / `evict` / `stats` surface stays unchanged so existing Phase
1 callers (`init-project`, `hydrate`, `materialise`,
`ingest-sources`) continue to work without modification.

## CLI subcommands

- `python -m pi_platform.cli runtime-status` — prints the
  `RuntimeStatusReport` from the default `RuntimeStorePort`
  adapter.
- `python -m pi_platform.cli graph-rebuild` — calls
  `GraphPort.rebuild_manifest()` and prints the regenerated
  `GraphManifest`.

## Verification

- `python -m unittest tests.test_platform_phase3 -v`
- `python -m unittest tests.test_graph_50k -v`
- `python harness.py check`
- `openspec validate --all --strict`