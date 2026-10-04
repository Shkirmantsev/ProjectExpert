---
id: architecture.system-overview
title: System Overview
kind: architecture
status: active
summary: High-level boundaries, actors and principal runtime responsibilities of ProjectExpert.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - pi_platform/
  - tests/test_platform_phase1.py
  - openspec/specs/2026-10-04-*
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

- The product source tree is **implemented** under
  `pi_platform/` (Python 3.11; hexagonal/ports-and-adapters + micro-
  kernel layout). The Phase 1 foundation lives in
  `pi_platform/core/{canonical,git,sync,licensing}/`,
  `adapters/{fs,git}/`, `runtime/`, `cli/`. The Python package name
  is `pi_platform` (not `platform`) to avoid a name collision with
  the Python standard library; the directory layout matches §64.
- `openspec/specs/` records agreed behavior; `openspec/changes/`
  records proposed behavior until adopted or archived. The five
  Phase 1 foundation capabilities are accepted under
  `openspec/specs/2026-10-04-*` and the implementation change is
  archived under
  [`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`](../../../openspec/changes/archive/2026-10-04-implement-phase-1-foundation/).
- `.ai/wiki/` explains the implementation and links to specs,
  ADRs and source. See [`architecture/platform-overview`](platform-overview.md)
  for the implemented module map and the planned extension
  points for Phases 2-10.
- `.ai/wiki/` explains the implementation and links to specs,
  ADRs and source. See [`architecture/platform-overview`](platform-overview.md)
  for the implemented module map and the planned extension
  points for Phases 2-10.
- The development harness (see `AGENTS.md`) is an upstream tool;
  its own accepted capabilities are listed in
  [`openspec/CURRENT.md`](../../../openspec/CURRENT.md).
- Optional integrations (LiteLLM, Hermes, SearXNG, Crawl4AI,
  Playwright) are opt-in via `.env`; the platform is correct
  without them.

## Principal components

- **Product code** — implemented under a hexagonal/ports-and-
  adapters + micro-kernel layout. See
  [`architecture/platform-overview`](platform-overview.md),
  [`modules/platform-core`](../modules/platform-core.md),
  [`interfaces/canonical`](../interfaces/canonical.md),
  [`interfaces/git`](../interfaces/git.md),
  [`interfaces/sync`](../interfaces/sync.md) and
  [`interfaces/licensing`](../interfaces/licensing.md).
- **Container, compose and launchers** — `Containerfile`,
  `docker-compose.yml` (with documented profiles),
  `scripts/project-intelligence.sh` (Linux) and
  `scripts/Start-ProjectIntelligence.ps1` (Windows).
- **Harness framework** — `harness.py`, `Makefile`, `scripts/`,
  `.agents/skills/`, `openspec/`, `.ai/`,
  `tools/mcp/project-context-mcp/`, `.opencode/`, `.claude/`,
  `.codex/`.
- **Documentation** — `docs/`, `README.md`,
  `project-intelligence-platform-architecture-v0.8.md`,
  [`openspec/changes/plan-v0-8-platform-architecture/`](../../../openspec/changes/plan-v0-8-platform-architecture/),
  [`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/`](../../../openspec/changes/archive/2026-10-04-implement-phase-1-foundation/).

## Phase 1 foundation capabilities (accepted)

The following five capabilities are accepted and have working
implementations under `pi_platform/`:

- `2026-10-04-project-knowledge-repository-layout`
- `2026-10-04-canonical-knowledge-schema`
- `2026-10-04-git-version-aware-runtime`
- `2026-10-04-bidirectional-canonical-runtime-sync`
- `2026-10-04-license-governance`

The Phase 1 regression suite is in
[`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py).

## Runtime flows

Document after the first end-to-end flow is implemented; cite the entry
points and the boundary contracts from the v0.8 architecture document
and from [`architecture/platform-overview`](platform-overview.md).

## Evidence

- [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
- [`openspec/changes/plan-v0-8-platform-architecture/proposal.md`](../../../openspec/changes/plan-v0-8-platform-architecture/proposal.md)
- [`openspec/changes/plan-v0-8-platform-architecture/design.md`](../../../openspec/changes/plan-v0-8-platform-architecture/design.md)
- [`openspec/changes/plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/plan-v0-8-platform-architecture/tasks.md)
- [`openspec/changes/archive/2026-10-04-implement-phase-1-foundation/design.md`](../../../openspec/changes/archive/2026-10-04-implement-phase-1-foundation/design.md)
- [`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py)
- [`AGENTS.md`](../../../AGENTS.md)
- [`openspec/CURRENT.md`](../../../openspec/CURRENT.md)