---
id: project.map
title: Project Map
kind: project
status: draft
summary: Repository navigation map for ProjectExpert: product sources, harness files, build/test entry points and important files.
sourceRefs: []
maintenance:
  mode: authored
---

# Project Map

## Main source areas

- Product source — **planned** under `platform/` (to be created by
  the future `implement-phase-1-foundation` change,
  hexagonal/ports-and-adapters + micro-kernel layout). See
  [`architecture/platform-overview`](../architecture/platform-overview.md)
  and the Phase 1 specs in
  [`plan-v0-8-platform-architecture`](../../../openspec/changes/plan-v0-8-platform-architecture/).
- [Harness scripts](../../../scripts/): environment bootstrap, client generation,
  skill routing, OpenSpec layout validation, session state.
- [Project-context MCP](../../../tools/mcp/project-context-mcp/): Wiki retrieval
  server and indexer (`kb_search`, `kb_get`, `kb_neighbors`, `code_symbol`,
  `spec_context`).
- [Harness skills](../../../.agents/skills/): directly discoverable core
  (`skill-router`, `session-checkpoint`, `project-safety`, `verification`,
  OpenSpec workflow skills) plus the on-demand catalog.
- [OpenSpec](../../../openspec/): production-SDD schema and templates,
  current specs, proposed changes. The
  [`plan-v0-8-platform-architecture`](../../../openspec/changes/plan-v0-8-platform-architecture/)
  change defines the v0.8 platform roadmap.
- [Architecture baseline](../../../project-intelligence-platform-architecture-v0.8.md):
  v0.8 platform architecture.
- [AI task handoffs](task-handoff.md): durable active-task context and
  empty-dialog resume lifecycle.

## Build and test entry points

- `python3 harness.py init` — initialize environment, Wiki index, skills and
  client configs.
- `python3 harness.py mcp-install` — install the project-local MCP
  environment.
- `python3 harness.py client-config` — regenerate client adapters after
  configuration changes.
- `python3 harness.py index` — rebuild the Wiki index after Markdown changes.
- `python3 harness.py check` — configuration, Wiki, OpenSpec structure, and
  regression tests; the operator pre-completion gate.
- `python3 scripts/session_state.py resume` — discover the current task and
  validate its working-set hashes.

## Important configuration

- [`.env.example`](../../../.env.example) documents supported local
  configuration; `.env` contains private machine settings.
- [`Makefile`](../../../Makefile) wraps the CLI and optional service commands.
- [`.harness/runtime.json`](../../../.harness/runtime.json) sets goal-loop
  budgets and routing profile limits.
- Canonical skills live under [`.agents/skills/`](../../../.agents/skills/).

## Generated/runtime directories

Generated local context/index data and session locks belong under
`tmp/local/` and must not become canonical knowledge. Durable operational
task state belongs under `.ai/state/`; it is separate from the project Wiki
and OpenSpec.