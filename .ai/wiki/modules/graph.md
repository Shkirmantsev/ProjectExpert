---
id: modules.graph
title: Phase 3 sharded graph module map
kind: modules
status: active
summary: Canonical knowledge graph with hash-prefix shards and 32 MiB per-file cap.
sourceRefs:
  - pi_platform/ports/runtime/graph.py
  - pi_platform/core/runtime/graph.py
  - pi_platform/adapters/runtime/sharded_graph.py
  - tests/test_graph_50k.py
maintenance:
  mode: authored
---

# Phase 3 sharded graph

The canonical knowledge graph is the durable representation of every
entity and relation the platform derives. Phase 3 implements it as
a hash-prefix sharded directory layout (§10.1, §16, §17) with a
single JSONL body file per prefix directory (so the per-prefix shard
count is bounded by the number of hash prefixes — 256 by default).

## Module map

- `pi_platform/ports/runtime/graph.py` — `GraphPort`,
  `GraphManifest`, `Shard`, `GraphPortError`.
- `pi_platform/core/runtime/graph.py` — re-export the `GraphPort`
  symbols.
- `pi_platform/adapters/runtime/sharded_graph.py` —
  `LocalShardedGraph` (default `GraphPort` impl).

## Layout

```text
project-knowledge/graph/
├── nodes/<prefix>/shard.jsonl     # entity bodies by hash prefix
├── edges/<prefix>/shard.jsonl     # relation bodies by hash prefix
├── objects/<prefix>/<hash>.json   # content-addressed entity bodies
├── node-index.jsonl               # entity id → shard path index
├── edge-index.jsonl               # source id → shard path index
└── graph-manifest.json            # §10.3 manifest
```

The `<prefix>` directories use the first two characters of the
SHA-256 hash of the entity id (`nodes/<prefix>/`) and the first two
characters of the SHA-256 hash of the source id (`edges/<prefix>/`).
The total per-prefix shard count is bounded by the number of hash
prefixes (256 by default).

## Per-file cap

Every shard JSONL file is held under the §66 documented 32 MiB
uncompressed budget. The `tests/test_graph_50k.py` property test
asserts both the shard count distribution and the 32 MiB cap with a
50 000-entity fixture.

## Content-addressed entity bodies

Every entity body is stored by its SHA-256 content address under
`objects/<prefix>/<hash>.json` so identical entity bodies across
Git branches share one canonical artefact.

## ANN graph vs. knowledge graph

The `GraphPort` only operates on the canonical knowledge graph
(§17 invariant). The `DenseIndexPort` operates on the ANN graph.
The two graphs MUST NOT be confused.

## Verification

- `python -m unittest tests.test_platform_phase3.GraphTests -v`
- `python -m unittest tests.test_graph_50k -v`
- `python -m pi_platform.cli graph-rebuild`
- `python harness.py check`
- `openspec validate --all --strict`