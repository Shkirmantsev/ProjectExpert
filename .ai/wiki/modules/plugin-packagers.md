---
id: modules.plugin-packagers
title: Phase 6 plugin packagers module
kind: modules
status: active
summary: Phase 6 §41-§45 per-vendor packagers + deterministic build runner; every bundle is generated from one release input set and shares the documented release identity.
sourceRefs:
  - pi_platform/adapters/agent_integration/packagers/codex.py
  - pi_platform/adapters/agent_integration/packagers/claude_code.py
  - pi_platform/adapters/agent_integration/packagers/opencode.py
  - pi_platform/adapters/agent_integration/packagers/generic_agent.py
  - pi_platform/adapters/agent_integration/packagers/runner.py
  - openspec/specs/2026-10-05-codex-plugin-package/spec.md
  - openspec/specs/2026-10-05-claude-code-plugin-package/spec.md
  - openspec/specs/2026-10-05-opencode-plugin-package/spec.md
  - openspec/specs/2026-10-05-generic-agent-bundle/spec.md
maintenance:
  mode: authored
related:
  - interfaces.plugin-distribution
  - interfaces.plugin-supply-chain
---

# Phase 6 plugin packagers module

The packagers under
`pi_platform/adapters/agent_integration/packagers/`
generate the four vendor bundles from one
`ReleaseInputSet`:

- `CodexPluginPackager` (§41) — Codex / ChatGPT
  plugin layout, with optional legacy
  `.codex-plugin/plugin.json` fallback.
- `ClaudeCodePluginPackager` (§42) — Claude Code
  plugin layout with the documented slug
  `project-intelligence`.
- `OpenCodePluginPackager` (§43) — npm-publishable
  or local-project-usable package with documented
  bootstrap fallback.
- `GenericAgentBundlePackager` (§44) — vendor-neutral
  bundle with stdio + HTTP MCP examples,
  `AGENTS.example.md`, `README.md`.

`DeterministicBuildRunner` (§45) coordinates the
four packagers and asserts the shared release
identity. The runner raises `DeterministicBuildError`
when any packager's supply-chain verdict fails, so
the build never emits a bundle with a hidden gap.

Every packager exposes a `bundle_inventory(bundle_root)`
helper that returns the full `{path: sha256}`
inventory of the output tree. The combined inventory
across vendors is the deterministic-build comparison
the §45 gate uses.