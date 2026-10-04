---
id: project.implementation-roadmap
title: v0.8 Platform Implementation Roadmap
kind: project
status: draft
summary: Ordered phase summary for implementing the v0.8 Project Intelligence Platform.
sourceRefs:
  - openspec/changes/plan-v0-8-platform-architecture/proposal.md
  - openspec/changes/plan-v0-8-platform-architecture/tasks.md
maintenance:
  mode: authored
---

# v0.8 Platform Implementation Roadmap

The full ordered task list is in
[`tasks.md`](../../../openspec/changes/plan-v0-8-platform-architecture/tasks.md).
This page summarises the phases and their dependencies so a new
contributor or AI agent can orient quickly.

## Phases

| # | Phase | Depends on | OpenSpec change |
|---|---|---|---|
| 0 | Plan | — | `plan-v0-8-platform-architecture` (this change) |
| 1 | Foundation | Phase 0 | next code-producing change |
| 2 | Ingestion (parsers, content addressing) | Phase 1 | depends on foundation specs |
| 3 | Storage (runtime DB, sharded graph) | Phase 2 | depends on Phase 2 specs |
| 4 | Retrieval (hybrid, multi-stage, reranking) | Phase 3 | depends on Phase 3 specs |
| 5 | Orchestration (query, local LLM, task context) | Phase 4 | depends on Phase 4 specs |
| 6 | Agent integration (MCP, skill, adapters) | Phase 5 | depends on Phase 5 specs |
| 7 | Control plane (registry, hooks, capabilities, secrets) | Phase 6 | depends on Phase 6 specs |
| 8 | Security (enterprise boundary) | Phase 7 | depends on Phase 7 specs |
| 9 | Distribution (UI, container, one-click) | Phase 8 | depends on Phase 8 specs |
| 10 | A2A and final quality gates | Phase 9 | depends on Phase 9 specs |

## Phase 1 deliverables

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

## Out-of-scope for Phase 1

Anything listed under Phases 2–10 is explicitly out of scope for the
first code-producing change. Adding out-of-scope work to Phase 1
violates the principle of the smallest coherent vertical change.