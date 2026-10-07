---
id: interfaces.plugin-distribution
title: Plugin distribution profiles
kind: interfaces
status: active
summary: Phase 6 §41-§44 Codex / Claude Code / OpenCode / generic-agent bundle layouts; every vendor package is generated from one release input set and shares the documented release identity.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#41
  - project-intelligence-platform-architecture-v0.8.md#42
  - project-intelligence-platform-architecture-v0.8.md#43
  - project-intelligence-platform-architecture-v0.8.md#44
  - pi_platform/adapters/agent_integration/packagers/codex.py
  - pi_platform/adapters/agent_integration/packagers/claude_code.py
  - pi_platform/adapters/agent_integration/packagers/opencode.py
  - pi_platform/adapters/agent_integration/packagers/generic_agent.py
maintenance:
  mode: authored
related:
  - interfaces.plugin-supply-chain
  - interfaces.agent-adapter-contract
---

# Plugin distribution profiles

The four per-vendor bundles follow the documented
layouts. Each bundle is generated from one
`ReleaseInputSet` and shares the documented release
identity (skill content hash, version, MCP API range,
license, server identity).

## Codex / ChatGPT plugin

- `plugin.json`, `mcp.json`, `skills/project-intelligence/SKILL.md`,
  `assets/`.
- legacy `.codex-plugin/plugin.json` only when the
  configured legacy client profile requires it.

## Claude Code plugin

- `.claude-plugin/plugin.json`, `.mcp.json`,
  `skills/project-intelligence/SKILL.md`, `README.md`,
  empty `commands/` and `agents/`.
- the documented plugin slug is `project-intelligence`.

## OpenCode plugin package

- `package.json`, `plugin/project-intelligence.ts`,
  `skill/project-intelligence/SKILL.md`,
  `config/opencode.example.jsonc`, `README.md`.
- publishable as a versioned npm package or usable as a
  local project plugin; the
  `bootstrap_fallback` flag replaces the embedded skill
  with minimal instructions when the active OpenCode
  version does not support Agent Skills loading.

## Generic agent bundle

- `skills/project-intelligence/SKILL.md`,
  `mcp/stdio-example.json`,
  `mcp/http-example.json`,
  `AGENTS.example.md`, `README.md`.
- vendor-neutral; maximises compatibility through
  standard MCP, Agent Skills, optional A2A and plain
  Markdown instructions.

## Determinism

Every packager exposes a `bundle_inventory(bundle_root)`
helper that returns the full `{path: sha256}` inventory
of the output tree. The `DeterministicBuildRunner`
combines the four vendors and asserts that two
isolated runs at different absolute paths produce the
same inventory, byte-for-byte.