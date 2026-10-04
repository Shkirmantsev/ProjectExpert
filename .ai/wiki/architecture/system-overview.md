---
id: architecture.system-overview
title: System Overview
kind: architecture
status: draft
summary: High-level boundaries, actors and principal runtime responsibilities of ProjectExpert.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
maintenance:
  mode: authored
---

# System Overview

ProjectExpert is a portable version-aware project intelligence platform. The
authoritative v0.8 architecture baseline lives in
[`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
at the repository root; this page mirrors only the boundaries that downstream
agents must respect.

## Purpose

Provide a portable, version-aware intelligence layer over a software project
so that operators and agents can retrieve current behavior, history and
project metadata without rebuilding the system for each tool.

## Boundaries

- The product source tree is **planned** under
  `platform/` (to be created by the future
  `implement-phase-1-foundation` change) and other top-level paths
  per the Phase 1 spec [`project-knowledge-repository-layout`](../../../openspec/changes/plan-v0-8-platform-architecture/specs/project-knowledge-repository-layout/spec.md).
  No product source exists yet.
- `openspec/specs/` records agreed behavior; `openspec/changes/` records
  proposed behavior until adopted or archived. The
  [`plan-v0-8-platform-architecture`](../../../openspec/changes/plan-v0-8-platform-architecture/)
  change is the planning artifact for the entire v0.8 architecture.
- `.ai/wiki/` explains the implementation and links to specs, ADRs and source.
  See [`architecture/platform-overview`](platform-overview.md) for the
  planned platform module map.
- The development harness (see `AGENTS.md`) is an upstream tool; its own
  accepted capabilities are listed in [openspec/CURRENT.md](../../../openspec/CURRENT.md).
- Optional integrations (LiteLLM, Hermes, SearXNG, Crawl4AI, Playwright) are
  opt-in via `.env`; the platform is correct without them.

## Principal components

- **Product code** — planned under a hexagonal/ports-and-adapters +
  micro-kernel layout. See
  [`architecture/platform-overview`](platform-overview.md) and the
  Phase 1 specs introduced by
  [`plan-v0-8-platform-architecture`](../../../openspec/changes/plan-v0-8-platform-architecture/).
- **Harness framework** — `harness.py`, `Makefile`, `scripts/`, `.agents/skills/`,
  `openspec/`, `.ai/`, `tools/mcp/project-context-mcp/`, `.opencode/`,
  `.claude/`, `.codex/`.
- **Documentation** — `docs/`, `README.md`, `project-intelligence-platform-architecture-v0.8.md`,
  [`openspec/changes/plan-v0-8-platform-architecture/`](../../../openspec/changes/plan-v0-8-platform-architecture/).

## Phase 1 foundation capabilities

The following capabilities are introduced as planning deltas here and
become accepted specifications once this change is adopted:

- `2026-10-04-project-knowledge-repository-layout`
- `2026-10-04-canonical-knowledge-schema`
- `2026-10-04-git-version-aware-runtime`
- `2026-10-04-bidirectional-canonical-runtime-sync`
- `2026-10-04-license-governance`

## Runtime flows

Document after the first end-to-end flow is implemented; cite the entry
points and the boundary contracts from the v0.8 architecture document
and from [`architecture/platform-overview`](platform-overview.md).

## Evidence

- [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
- [`openspec/changes/plan-v0-8-platform-architecture/proposal.md`](../../../openspec/changes/plan-v0-8-platform-architecture/proposal.md)
- [`openspec/changes/plan-v0-8-platform-architecture/design.md`](../../../openspec/changes/plan-v0-8-platform-architecture/design.md)
- [`openspec/changes/plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/plan-v0-8-platform-architecture/tasks.md)
- [`AGENTS.md`](../../../AGENTS.md)
- [`openspec/CURRENT.md`](../../../openspec/CURRENT.md)