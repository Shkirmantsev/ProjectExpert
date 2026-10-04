---
name: hermes-delegation
description: Delegate bounded independent work to the native remote Hermes worker while preserving the client-specific transport split.
---
# Hermes delegation
- Hermes is an external leaf worker and owns its own agent loop, tools, skills, and native SSH project access.
- Claude Code delegates through the dedicated remote Hermes MCP sidecar; that sidecar is control-plane only and must not proxy project files.
- OpenCode delegates through project-local `hermes_*` custom tools which call the native Hermes `/v1/runs` API directly; do not route it through the Claude MCP sidecar, LiteLLM, or a model-backed `@generated-hermes` subagent.
- Codex has no Hermes transport in this phase.
- In OpenCode call `hermes_delegate` once with a complete bounded task. If it returns a still-running `run_id`, use `hermes_wait`/`hermes_status`/`hermes_result` instead of starting a duplicate run.
- The configured absolute project root is injected by the tool; the parent should provide expected outcome and verification criteria in the task.
- Ordinary source/docs/PDF/images/other repository files are handled by Hermes itself. Do not invent project bindings or pass transport secrets in prompts.
- Never ask Hermes to launch Claude Code, OpenCode, or Codex recursively.
