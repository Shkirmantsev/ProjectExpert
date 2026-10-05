---
id: project.implementation-roadmap
title: v0.8 Platform Implementation Roadmap
kind: project
status: active
summary: Ordered phase summary for implementing the v0.8 Project Intelligence Platform.
sourceRefs:
  - openspec/changes/plan-v0-8-platform-architecture/proposal.md
  - openspec/changes/plan-v0-8-platform-architecture/tasks.md
  - openspec/changes/archive/2026-10-04-implement-phase-1-foundation/design.md
maintenance:
  mode: authored
---

# v0.8 Platform Implementation Roadmap

The full ordered task list is in
[`tasks.md`](../../../openspec/changes/plan-v0-8-platform-architecture/tasks.md).
This page summarises the phases and their dependencies so a new
contributor or AI agent can orient quickly.

## Phases

| # | Phase | Depends on | Status |
|---|---|---|---|
| 0 | Plan | — | complete (archived) |
| 1 | Foundation | Phase 0 | complete (archived) |
| 2 | Ingestion (parsers, content addressing) | Phase 1 | complete |
| 3 | Storage (runtime DB, sharded graph) | Phase 2 | complete |
| 4 | Retrieval (hybrid, multi-stage, reranking) | Phase 3 | planned |
| 5 | Orchestration (query, local LLM, task context) | Phase 4 | planned |
| 6 | Agent integration (MCP, skill, adapters) | Phase 5 | planned |
| 7 | Control plane (registry, hooks, capabilities, secrets) | Phase 6 | planned |
| 8 | Security (enterprise boundary) | Phase 7 | planned |
| 9 | Distribution (UI, container, one-click) | Phase 8 | planned |
| 10 | A2A and final quality gates | Phase 9 | planned |

## Phase 1 deliverables (complete)

The Phase 1 foundation change ships the smallest coherent vertical
slice that lets later phases build on stable contracts:

- `project-knowledge-repository-layout` — directory tree and
  configuration contract.
- `canonical-knowledge-schema` — value types, deterministic
  serialization, content addressing, sharded storage, manifests,
  OKF v0.2 adapter and validator.
- `git-version-aware-runtime` — Git adapter, version identity,
  working-tree overlay, cross-branch reuse, Git LFS.
- `bidirectional-canonical-runtime-sync` — hydrate / reconcile /
  materialise lifecycle with round-trip preservation and
  approval-gated materialise.
- `license-governance` — SPDX dependency inventory, allow/review/
  deny policy, model-license separate tracking, SBOM, CI gate,
  dynamic plugin/hook verification.

Phase 1 also produces:

- the `pi_platform/` Python package with the canonical, git,
  sync and licensing modules;
- `Containerfile`, `docker-compose.yml` skeletons and Linux /
  Windows launcher scripts;
- the `distribution/{licenses,skills,codex,claude-code,opencode,
  generic-agent,sbom}/` scaffolding;
- the `tests/test_platform_phase1.py` regression suite and the
  Phase 1 ADRs (`0002-canonical-runtime-separation`,
  `0003-license-governance-default`,
  `0004-ports-and-adapters-extension-style`,
  `0005-platform-source-language`).

## Out-of-scope for Phase 1

Anything listed under Phases 2–10 is explicitly out of scope for the
first code-producing change. Adding out-of-scope work to Phase 1
violates the principle of the smallest coherent vertical change.

## Phase 2 ingestion

The [ingestion module](../modules/ingest.md) implements PipelineDriver, source adapters,
structural chunking, layered enrichment, content-address reuse and inbox policies.
SourcePromotionPolicy distinguishes LOCAL_ONLY, REFERENCE and SNAPSHOT; parser
subprocesses and cache records carry explicit provenance. See the
[source interface](../interfaces/source-adapters.md), [chunker](../interfaces/chunker.md)
and [enrichment](../interfaces/enrichment.md) contracts. Persistent storage and retrieval
remain future phases.

## Phase 3 storage (complete)

The [runtime store module](../modules/runtime-store.md) and the [graph module](../modules/graph.md)
implement the Phase 3 storage surface — the embedded runtime store, three indexes
(BM25-sparse, ANN-dense, FTS5-secondary), the canonical sharded knowledge graph, the
`GraphExpansion` preview port, the `KnowledgeState` lifecycle and the
`FreshnessTracker` snapshot. The default backend uses Python stdlib `sqlite3`; the
PostgreSQL backend is opt-in for the enterprise-scale profile. The 50 000-entity
property test (`tests/test_graph_50k.py`) asserts both the shard count distribution and
the 32 MiB per-file cap. The Phase 3 ADR
`0008-embedded-storage-selection` documents the dual-backend choice and the rejected
alternatives (DuckDB MIT, RocksDB Apache-2.0, sled MPL-2.0, LevelDB BSD-3-Clause,
Badger Apache-2.0).
