# ProjectExpert

Portable Version-Aware Project Intelligence Platform.

## Development harness

This repository uses the [harness-layout](https://github.com/Shkirmantsev/harness-layout)
framework as its LLM-agent development harness. The harness provides:

- [`AGENTS.md`](AGENTS.md) and [`CLAUDE.md`](CLAUDE.md) — the always-loaded
  agent control plane.
- [`harness.py`](harness.py) / [`Makefile`](Makefile) — portable CLI
  (`init`, `check`, `test`, `clean`, ...).
- [`.env.example`](.env.example) / [`.harness/runtime.json`](.harness/runtime.json)
  — configuration and runtime policy.
- [`.agents/skills/`](.agents/skills/) — canonical shared skills (router,
  safety, checkpoint, verification, OpenSpec workflow, on-demand catalog).
- [`openspec/`](openspec/) — normative behavior specifications and change
  workflow.
- [`.ai/wiki/`](.ai/wiki/) — durable Markdown knowledge, retrieved through
  the `project-context` MCP server.
- [`.opencode/`](.opencode/), [`.claude/`](.claude/), [`.codex/`](.codex/) —
  client adapters and slash-commands.
- [`tools/mcp/project-context-mcp/`](tools/mcp/project-context-mcp/) — local
  MCP server (`kb_search`, `kb_get`, `kb_neighbors`, `code_symbol`,
  `spec_context`).
- [`docs/`](docs/) — navigation map, engineering conventions, security,
  troubleshooting.
- Optional: [`infra/`](infra/) (LiteLLM, SearXNG, Crawl4AI, Playwright),
  [`remote/hermes-worker-mcp/`](remote/hermes-worker-mcp/) (Claude Hermes
  sidecar), [`patches/`](patches/), [`templates/`](templates/).

See the [documentation map](docs/README.md) and the
[project structure](docs/PROJECT_STRUCTURE.md) for ownership and dependency
details. The Wiki is indexed at [`.ai/wiki/INDEX.md`](.ai/wiki/INDEX.md).

## Quick start

```bash
make init-mcp         # one-shot: .env, Wiki index, skills, MCP venv, client configs
make wiki-init        # validate existing Wiki and (re)build its disposable index
make check            # operator gate: config + Wiki + OpenSpec + tests + manifest
```

The portable `python` equivalents (`python harness.py <command>`) work on
Linux, macOS and Windows without GNU Make. See
[docs/HARNESS_COMMANDS.md](docs/HARNESS_COMMANDS.md) for the full setup and
manual MCP lifecycle (`run-mcp` / `stop-mcp` / `mcp-status` / `mcp-logs` /
`mcp-clean` / `mcp-stdio`).

## Architectural baseline

[`project-intelligence-platform-architecture-v0.8.md`](project-intelligence-platform-architecture-v0.8.md)
captures the v0.8 architecture baseline for the platform and is the starting
point for the [`architecture/system-overview`](.ai/wiki/architecture/system-overview.md),
[`project/project-map`](.ai/wiki/project/project-map.md), and
[`glossary/domain`](.ai/wiki/glossary/domain.md) Wiki pages.

## Where to find answers

| Question | File |
|---|---|
| How to use the harness | [docs/README.md](docs/README.md), [docs/QUICKSTART.md](docs/QUICKSTART.md), [docs/HARNESS_COMMANDS.md](docs/HARNESS_COMMANDS.md) |
| How to configure `.env` | [docs/CONFIGURATION.md](docs/CONFIGURATION.md) |
| What a skill does | [`.agents/skills/<name>/SKILL.md`](.agents/skills/) or [docs/SKILLS.md](docs/SKILLS.md) |
| How OpenSpec works | [openspec/README.md](openspec/README.md), [openspec/CURRENT.md](openspec/CURRENT.md) |
| Coding and commit conventions | [docs/conventions/README.md](docs/conventions/README.md) |
| Something broke | [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) |
| Security and secrets | [docs/SECURITY.md](docs/SECURITY.md) |
| Directory layout | [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) |
| OpenCode V1 vs V2 | [docs/OPENCODE_COMPATIBILITY.md](docs/OPENCODE_COMPATIBILITY.md) |