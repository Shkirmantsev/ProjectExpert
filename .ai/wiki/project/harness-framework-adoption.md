---
id: project.harness-framework-adoption
title: Harness Framework Adoption
kind: project
status: active
summary: Records that this project uses the upstream harness-layout framework as its development harness, without importing its history.
sourceRefs:
  - AGENTS.md
  - README.md
maintenance:
  mode: authored
---

# Harness Framework Adoption

This project adopts the upstream
[harness-layout](https://github.com/Shkirmantsev/harness-layout) framework as
its LLM-agent development harness. The framework provides:

- `AGENTS.md` and `CLAUDE.md` — the always-loaded agent control plane.
- `harness.py` / `Makefile` — portable CLI (`init`, `check`, `test`, ...).
- `.env.example` and `.harness/runtime.json` — configuration and runtime
  policy.
- `.agents/skills/` — canonical shared skills (router, safety, checkpoint,
  verification, OpenSpec workflow, on-demand catalog).
- `openspec/` — normative behavior specifications and the change workflow.
- `.ai/wiki/` — durable Markdown knowledge, retrieved through the
  `project-context` MCP server.
- `tools/mcp/project-context-mcp/` — local MCP server for retrieval and
  indexing.
- `.opencode/`, `.claude/`, `.codex/` — client adapters.
- `docs/` — navigation map, engineering conventions, security,
  troubleshooting.

## Scope of import

- **Adopted**: framework files (control plane, CLI, scripts, skills,
  OpenSpec schema and templates, MCP server, client adapters, docs).
- **Local OpenCode integration**: the V1 routing scaffold adds an inheriting
  MiniMax M3 orchestrator, three OpenRouter workers, `/route`, and the
  `jev_decide` custom tool. Its V1 settings are merged into the root config;
  stale V2 nested config/plugin files are backed up outside `.opencode`.
  See [OpenCode compatibility](../../../docs/OPENCODE_COMPATIBILITY.md#projectexpert-v1-routing-scaffold)
  for setup and the config-regeneration limitation.
- **Adopted as reference**: harness-specific OpenSpec accepted specs under
  [`openspec/specs/`](../../../openspec/specs/) document the framework
  contract; they are not ProjectExpert product specs. See
  [`openspec/CURRENT.md`](../../../openspec/CURRENT.md).
- **Not imported**: the source repository's git history, session handoffs,
  archived changes, harness-specific reports (`HERMES_REVIEW.md`,
  `QA_REPORT.md`, `MIGRATION_FROM_BRIDGE.md`), harness-internal changes
  (`openspec/changes/java-maven-jar-skill-adoption/`,
  `openspec/changes/production-readiness-remediation/`), the harness's own
  evals, third-party skill licenses and unrelated documentation.

## Project product capabilities

ProjectExpert's own product capabilities are not yet adopted. Create new
specs through the OpenSpec workflow (`openspec/changes/<id>/` →
`openspec/specs/YYYY-MM-DD-domain-capability/`) and link them in
`openspec/CURRENT.md`.
