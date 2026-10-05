# Proposal — Prepare the v0.8 Phase 3 Storage Capability Specs

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the storage layer as the third implementation phase: nine
behavioural capabilities (`runtime-store`, `sparse-index`,
`dense-index`, `full-text-index`, `sharded-graph`, `graph-expansion`,
`provenance-state-model`, `freshness-tracking`,
`embedded-storage-selection`) that turn the Phase 2 chunks and
entities/relations into a durable runtime store, three complementary
indexes (BM25-sparse, ANN-dense, full-text), the canonical sharded
knowledge graph, and the provenance / freshness tracking layer that
the later phases (Retrieval, Orchestration, MCP) consume.

The Phase 1 foundation
(`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`)
and the Phase 2 ingestion subsystem
(`openspec/changes/archive/2026-10-04-implement-phase-2-ingestion/`)
are prerequisites. Phase 1 supplies the canonical value-type catalogue,
the SHA-256 content address, the Git-version-aware runtime and the
license gate; Phase 2 supplies the `PipelineDriver`, the
`SourceAdapter` family, the `Chunker`, the `ContextEnricher`, the
`LocalSourceInboxScanner` and the nine Phase 2 capability specs that
emit the canonical chunks and entity/relation records the Phase 3
runtime store is expected to host. The current Phase 1 runtime cache
(`pi_platform/runtime/cache.py`) is documented as a Phase 1 stub that
Phase 3 replaces with the real embedded runtime store (relational +
vector + graph). Without Phase 3 specs there is no authoritative
behavioural contract for the storage subsystem, the later phases
cannot reuse the sharded graph or the BM25 / HNSW indexes, and the
regression suite cannot express Phase 3 scenarios such as the
50 000-entity sharding test that task 68 mandates.

This change resolves the gap by authoring the nine Phase 3 capability
specs, the supporting design, context-impact and tasks, while shipping
zero production code. The implementation work ships under a future
`implement-phase-3-storage` change that depends on the nine Phase 3
specs being accepted into `openspec/specs/`.

## Goal

Author the Phase 3 capability specs and change artifacts so that a
later `implement-phase-3-storage` change can:

- fill in the Phase 1 placeholder `RuntimeStorePort` with a real
  embedded runtime store (per-shard content-addressed cache, version
  stamp, write-ahead log, per-project advisory file lock) per the
  runtime DB engine selection ADR (§61) — the design candidate is a
  PostgreSQL + SQLite dual-backend with Apache-2.0 / BSD licenses
  (DuckDB, RocksDB and `sled` are explicitly rejected for the reasons
  recorded in the `embedded-storage-selection` ADR);
- implement the three documented indexes behind their respective
  ports: `SparseIndexPort` (BM25 over chunks and entities), the
  secondary `FullTextIndexPort` and the `DenseIndexPort` (HNSW or
  flat ANN over chunk embeddings), each per the §63-§65 contract;
- implement the canonical sharded knowledge graph (`GraphPort`,
  `Shard.contentHash` primary key, §10.1 / §16 / §66) with a clear
  separation between ANN graph and knowledge graph (§17);
- expose the optional Phase 4 `GraphExpansionPort` preview
  (seed set + hops + edge-type filter) so the Phase 4 retrieval
  change does not have to invent the surface area in isolation;
- implement the `KnowledgeState` lifecycle transitions
  (`verified` → `inferred` → `stale` → `unknown` plus `conflicting`)
  and the freshness-tracking rules that drive the staleness map on
  every reconcile (§54, §55, §67);
- record the embedded-storage-engine selection in
  `embedded-storage-selection` ADR with the documented rationale
  and the rejected alternatives.

What this change does:

- proposes the nine Phase 3 capability specs under
  `openspec/changes/prepare-phase-3-storage/specs/`;
- documents the technical design covering the `RuntimeStore`
  coordinator (per-shard cache, version stamp, WAL, file lock), the
  `SparseIndex`, `FullTextIndex` and `DenseIndex` ports with their
  default adapters, the `Graph` sharding strategy, the `KnowledgeState`
  lifecycle and freshness rules, the graph-expansion preview port and
  the runtime-DB engine selection rationale;
- lists the Wiki, ADR and context-impact nodes the future
  `implement-phase-3-storage` change will need to create or update;
- enumerates Phase 3 tasks 61–69 (mirroring
  [`plan-v0-8-platform-architecture/tasks.md`](../../changes/plan-v0-8-platform-architecture/tasks.md))
  with concrete verification commands so a contributor or AI agent can
  execute them deterministically.

Out of scope for this change:

- any production code under `pi_platform/ports/runtime/`,
  `pi_platform/core/runtime/`, `pi_platform/adapters/runtime/`
  or any other Phase 3 module;
- any addition to the runtime dependency inventory (no PostgreSQL
  Python driver, no HNSW library, no BM25 library, no full-text
  search library — those land in the future
  `implement-phase-3-storage` change after each SPDX-tracked license
  inventory entry passes `LicenseGate`);
- the dense ANN, hybrid retrieval, multi-stage retrieval and reranker
  (Phase 4 tasks 70–75);
- the query orchestrator, local LLM, task context and capability
  discovery (Phase 5 tasks 79–83);
- the MCP server exposing the runtime store (Phase 6 task 85);
- the Wiki materialisation, control plane, security, distribution,
  A2A (Phase 7+ tasks 86–123);
- archiving this change. The change stays active (proposal-only)
  until the future `implement-phase-3-storage` change uses it as
  prerequisite. The `plan-v0-8-platform-architecture` change remains
  the authoritative source for Phase 3–10 task ordering; tasks 61–69
  stay `[ ]`.

## Affected capabilities

This change introduces the following additive capability specs. None
of the five accepted Phase 1 specs (`project-knowledge-repository-layout`,
`canonical-knowledge-schema`, `git-version-aware-runtime`,
`bidirectional-canonical-runtime-sync`, `license-governance`) and none
of the nine accepted Phase 2 specs (`ingestion-pipeline-driver`,
`structured-code-intelligence`, `jar-dependency-intelligence`,
`document-source-adapters`, `openspec-change-adapter`,
`local-source-inbox`, `content-addressed-processing`,
`semantic-structural-chunking`, `context-enrichment`) is modified or
retired. Phase 3 specs depend on the Phase 1 specs (canonical schema,
Git-version-aware runtime, bidirectional sync, repository layout,
license governance) and the Phase 2 specs (content-addressed
processing, semantic-structural chunking, context enrichment) but do
not alter their normative content.

| New capability | Architecture sections | Phase 3 task(s) | Spec delta path |
|---|---|---|---|
| `embedded-storage-selection` | §61 | 61 | [`specs/2026-10-04-embedded-storage-selection/spec.md`](specs/2026-10-04-embedded-storage-selection/spec.md) |
| `runtime-store` | §62, §10.2, §64 | 62, 69 | [`specs/2026-10-04-runtime-store/spec.md`](specs/2026-10-04-runtime-store/spec.md) |
| `sparse-index` | §63, §26 | 63, 69 | [`specs/2026-10-04-sparse-index/spec.md`](specs/2026-10-04-sparse-index/spec.md) |
| `dense-index` | §64, §28 | 64, 69 | [`specs/2026-10-04-dense-index/spec.md`](specs/2026-10-04-dense-index/spec.md) |
| `full-text-index` | §65, §26 | 65, 69 | [`specs/2026-10-04-full-text-index/spec.md`](specs/2026-10-04-full-text-index/spec.md) |
| `sharded-graph` | §66, §10.1, §16, §17 | 66, 68, 69 | [`specs/2026-10-04-sharded-graph/spec.md`](specs/2026-10-04-sharded-graph/spec.md) |
| `graph-expansion` | §73, §31 | (Phase 4 preview) | [`specs/2026-10-04-graph-expansion/spec.md`](specs/2026-10-04-graph-expansion/spec.md) |
| `provenance-state-model` | §67, §54 | 67, 69 | [`specs/2026-10-04-provenance-state-model/spec.md`](specs/2026-10-04-provenance-state-model/spec.md) |
| `freshness-tracking` | §55, §67 | 67, 69 | [`specs/2026-10-04-freshness-tracking/spec.md`](specs/2026-10-04-freshness-tracking/spec.md) |

The nine specs cover Phase 3 tasks 61–69 from
[`plan-v0-8-platform-architecture/tasks.md`](../../changes/plan-v0-8-platform-architecture/tasks.md).
Tasks 61–69 remain `[ ]` in the plan change after this change is
archived; they will be flipped to `[x]` by the future
`implement-phase-3-storage` change when it lands. The
`graph-expansion` capability is a Phase 4 preview — Phase 3 ships the
port contract and a stub adapter so Phase 4 does not have to invent
the surface area, but Phase 4 owns the production implementation and
the §31 / §73 scenarios.

Cross-phase task responsibility:

- the embedded-storage-engine selection (task 61) is owned by Phase 3
  but the chosen engine remains replaceable through the
  `RuntimeStorePort` so the enterprise-scale profile can substitute a
  different backend without changing the public contract;
- the `SparseIndex` / `DenseIndex` / `FullTextIndex` (tasks 63-65)
  expose ports that Phase 4 composes into the
  `HybridRetrieval` pipeline (Phase 4 task 71);
- the `GraphExpansion` capability (Phase 4 task 73) is previewed as a
  Phase 3 port contract only; Phase 4 ships the implementation;
- the `RuntimeStore` (task 62), `Graph` (task 66), `KnowledgeState`
  (task 67) and freshness tracking (task 67) own the Phase 3
  storage surface; the MCP server exposing the runtime store
  (Phase 6 task 85) and the OKF Wiki materialisation of the
  storage entities (Phase 9 task 112) belong to later phases.

Naming and adoption conventions (per
[`openspec/config.yaml`](../../config.yaml) and
[`openspec/README.md`](../../README.md)):

- active change IDs are undated semantic kebab-case
  (`prepare-phase-3-storage`);
- delta folders under `specs/` use the future first-acceptance date
  (`2026-10-04-<capability>`);
- `openspec/CURRENT.md` is updated by the future
  `implement-phase-3-storage` change when the nine Phase 3 specs are
  adopted, not by this change.

## Compatibility / migration impact

This change is a pure planning artifact. It adds:

- one new active change directory at
  `openspec/changes/prepare-phase-3-storage/`;
- nine new spec deltas under
  `openspec/changes/prepare-phase-3-storage/specs/2026-10-04-*/`.

It does not:

- modify any accepted Phase 1 capability spec under
  `openspec/specs/2026-10-04-*/`;
- modify any accepted Phase 2 capability spec under
  `openspec/specs/2026-10-04-*/`;
- modify `openspec/CURRENT.md`, the harness, the license inventory or
  the regression suite;
- introduce any source code, dependency or runtime configuration;
- rename any existing capability, port or adapter;
- alter the `plan-v0-8-platform-architecture` change
  (`tasks.md` still lists tasks 61–69 as `[ ]`).

Language and dependency decisions:

- the Python 3.11 platform source language decision recorded in
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  still holds. No new language dependency is being introduced by this
  change. The future `implement-phase-3-storage` change MAY add one
  PostgreSQL Python driver (e.g. `psycopg` Apache-2.0), one embedded
  SQLite Python wrapper (e.g. `sqlite3` stdlib, no extra dependency),
  one HNSW library (e.g. `hnswlib` MIT) and one BM25 / full-text
  library (e.g. `rank-bm25` MIT) — but only after each SPDX-tracked
  license inventory entry passes `LicenseGate`. The Python-only default
  ports in `pi_platform/ports/runtime/` stay language-neutral; the
  storage engines are supplied as adapters under
  `pi_platform/adapters/runtime/` so no port acquires a
  database-runtime dependency;
- no change to the licence-governance defaults. Any new dependency
  must be SPDX-tracked and pass `LicenseGate` before it lands in
  `distribution/licenses/dependency-inventory.json`. The candidate
  storage libraries are documented as review-required paths in the
  `design.md` so the future
  `embedded-storage-selection` ADR carries the documented rationale
  (PostgreSQL + SQLite dual-backend, Apache-2.0 / BSD, rejected
  alternatives: DuckDB MIT, RocksDB Apache-2.0, `sled` MPL-2.0).

OpenSpec CLI conventions:

- the change folder uses lowercase kebab-case without a date prefix
  (`prepare-phase-3-storage`) per
  [`openspec/config.yaml`](../../config.yaml);
- the nine spec deltas are dated with the future acceptance date
  `2026-10-04` matching the Phase 1 and Phase 2 archive conventions;
  the archive step for the future `implement-phase-3-storage` change
  will produce `archive/2026-10-04-implement-phase-3-storage/` and
  rename the delta folders to drop the date prefix in the change-root
  view;
- no production code, license inventory entry or harness command is
  touched.

## Related knowledge

- `kb://architecture.platform-overview` — Phase 1 Wiki node; will be
  updated by the future `implement-phase-3-storage` change to add the
  Phase 3 module map (`runtime/`, `ports/runtime/`,
  `adapters/runtime/`).
- `kb://architecture.system-overview` — cross-cutting view; will gain
  a Phase 3 module map row.
- `kb://glossary.platform` — Phase 1 / Phase 2 platform vocabulary; the
  future change adds `RuntimeStore`, `SparseIndex`, `DenseIndex`,
  `FullTextIndex`, `Graph`, `KnowledgeState`, `FreshnessTracker`,
  `GraphExpansion`.
- `kb://glossary.domain` — cross-links to the platform vocabulary.
- `kb://project.implementation-roadmap` — links to Phase 3 entry.
- `kb://project.project-map` — Phase 3 module map placeholder.
- `kb://adr.platform-source-language` — Python 3.11 holds; the
  storage engines stay under `pi_platform/adapters/runtime/`.
- `kb://adr.canonical-runtime-separation` — Phase 3 specs respect
  invariants #1–#4 and the canonical / runtime boundary.
- `kb://adr.license-governance-default` — every Phase 3 dependency
  requires an SPDX-tracked inventory entry.
- future `kb://adr.embedded-storage-selection` — runtime DB engine
  selection (the design candidate is PostgreSQL + SQLite dual-backend
  with Apache-2.0 / BSD; rejected alternatives include DuckDB MIT,
  RocksDB Apache-2.0, `sled` MPL-2.0).
- future `kb://modules.runtime-store`, `kb://modules.graph` —
  Wiki module maps for the Phase 3 surface.
- future `kb://interfaces.runtime-store`,
  `kb://interfaces.sparse-index`, `kb://interfaces.dense-index`,
  `kb://interfaces.full-text-index`,
  `kb://interfaces.graph-expansion` — Wiki interface nodes.
- external: `project-intelligence-platform-architecture-v0.8.md`
  §10.1-§10.4, §16, §17, §26, §28, §31, §54, §55, §61-§67, §73 —
  every cited section is authoritative for the Phase 3 capability
  contracts.