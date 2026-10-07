---
id: project.map
title: Project Map
kind: project
status: active
summary: Repository navigation map for ProjectExpert: product sources, harness files, build/test entry points and important files.
sourceRefs:
  - pi_platform/
  - tests/test_platform_phase1.py
  - Containerfile
  - docker-compose.yml
  - scripts/project-intelligence.sh
  - scripts/Start-ProjectIntelligence.ps1
  - openspec/changes/archive/2026-10-04-implement-phase-1-foundation/design.md
maintenance:
  mode: authored
---

# Project Map

## Main source areas

- Product source — **implemented** under `pi_platform/` (Python
  3.11, hexagonal/ports-and-adapters + micro-kernel layout). See
  [`architecture/platform-overview`](../architecture/platform-overview.md),
  [`modules/platform-core`](../modules/platform-core.md) and the
  Phase 1 specs in `openspec/specs/2026-10-04-*`. The Python
  package name is `pi_platform` (the directory name `platform/`
  would collide with the Python standard library `platform`
  module); both `Containerfile` and the launcher scripts import
  `pi_platform.cli`.
- `project-knowledge/`, `.project-intelligence-cache/`,
  `distribution/` — populated in the **target repository** by
  `python -m pi_platform.cli init-project`. These directories are
  owned by the target, not by this implementation repo.
- `Containerfile`, `docker-compose.yml` — single-container default
  plus the documented compose profiles (`core-headless`,
  `desktop-lite`, `desktop-local-ai`, `open-webui`, `enterprise`).
- `scripts/project-intelligence.sh` and
  `scripts/Start-ProjectIntelligence.ps1` — Phase 1 launcher
  skeletons; full one-click behaviour ships in Phase 9.
- [Harness scripts](../../../scripts/): environment bootstrap,
  client generation, skill routing, OpenSpec layout validation,
  session state.
- [Project-context MCP](../../../tools/mcp/project-context-mcp/):
  Wiki retrieval server and indexer (`kb_search`, `kb_get`,
  `kb_neighbors`, `code_symbol`, `spec_context`).
- [Harness skills](../../../.agents/skills/): directly discoverable
  core (`skill-router`, `session-checkpoint`, `project-safety`,
  `verification`, OpenSpec workflow skills) plus the on-demand
  catalog.
- [OpenSpec](../../../openspec/): production-SDD schema and
  templates, current specs, proposed changes. The
  [`plan-v0-8-platform-architecture`](../../../openspec/changes/plan-v0-8-platform-architecture/)
  change defines the v0.8 platform roadmap and the archived
  [`implement-phase-1-foundation`](../../../openspec/changes/archive/2026-10-04-implement-phase-1-foundation/)
  change delivers the Phase 1 implementation.
- [Architecture baseline](../../../project-intelligence-platform-architecture-v0.8.md):
  v0.8 platform architecture.
- [AI task handoffs](task-handoff.md): durable active-task context
  and empty-dialog resume lifecycle.

## Build and test entry points

- [CodeQL workflow](../../../.github/workflows/codeql.yml) — Python code
  scanning for pull requests to and pushes on `main` and `dev`, with SARIF
  results uploaded to GitHub. This does not supply a human PR approval.
  [GitHub setup guide](../../../GITHUB_REVIEW_SETUP.md) covers
  initial target-branch scanning and repository review settings. Remote
  execution must be verified in GitHub Actions after publishing the workflow.
- `python3 harness.py init` — initialize environment, Wiki index,
  skills and client configs.
- `python3 harness.py mcp-install` — install the project-local MCP
  environment.
- `python3 harness.py client-config` — regenerate client adapters
  after configuration changes.
- `python3 harness.py index` — rebuild the Wiki index after
  Markdown changes.
- `python3 harness.py check` — configuration, Wiki, OpenSpec
  structure, and regression tests; the operator pre-completion
  gate. Phase 1 also runs `tests/test_platform_phase1.py`.
- `python3 scripts/session_state.py resume` — discover the
  current task and validate its working-set hashes.
- `make platform-init` / `make platform-hydrate` /
  `make platform-materialise` / `make license-gate` /
  `make okf-validate` / `make version-identity` /
  `make wal-recover` — Phase 1 platform CLI shortcuts.
- `python3 -m pi_platform.cli ...` — direct entry point for
  the documented subcommands (`init-project`, `hydrate`,
  `materialise`, `license-gate`, `okf-validate`,
  `version-identity`, `wal-recover`, `ingest-sources`,
  `runtime-status`, `graph-rebuild`, `health`).

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


## Phase 2 ingestion

The [ingestion module](../modules/ingest.md) implements PipelineDriver, source adapters,
structural chunking, layered enrichment, content-address reuse and inbox policies.
SourcePromotionPolicy distinguishes LOCAL_ONLY, REFERENCE and SNAPSHOT; parser
subprocesses and cache records carry explicit provenance. See the
[source interface](../interfaces/source-adapters.md), [chunker](../interfaces/chunker.md)
and [enrichment](../interfaces/enrichment.md) contracts. Persistent storage and retrieval
remain future phases.

## Phase 3 storage

The [runtime store module](../modules/runtime-store.md) and the [graph module](../modules/graph.md)
implement the Phase 3 storage surface — the embedded runtime store, three indexes
(BM25-sparse, ANN-dense, FTS5-secondary), the canonical sharded knowledge graph, the
`GraphExpansion` preview port, the `KnowledgeState` lifecycle and the
`FreshnessTracker` snapshot. The default backend uses Python stdlib `sqlite3`; the
PostgreSQL backend is opt-in for the enterprise-scale profile.
