---
name: delegation
description: Delegate bounded independent work with a self-contained task envelope and client-appropriate transport. Use when parallelism, isolated context, or a fresh review materially helps; do not delegate tightly coupled work or trivial one-step tasks.
---

# Delegation

Delegate outcomes, not vague activity. The parent remains responsible for scope, integration, and final verification.

## Decide first

Delegate only when the subtask is independently useful, has no unresolved dependency on another active task, and can be checked on its own. Keep tightly coupled reasoning in one context. Do not delegate merely to avoid reading the relevant files.

## Task envelope

Provide each worker only what it needs:

- concrete objective and why it matters;
- exact project boundary and relevant files or symbols;
- known evidence, constraints, and non-goals;
- allowed side effects and forbidden actions;
- observable acceptance and smallest useful verification;
- expected return: findings, changed files, commands/results, uncertainty, and blockers.

Never put secrets, `.env` contents, credentials, or private transport details in a task. A child receives no broader authority than its parent.

## Client routing

- Claude Code may use its native subagents for local work. Use the dedicated Hermes MCP sidecar only for an explicitly suitable remote Hermes task; the sidecar stays control-plane-only.
- OpenCode may use native local agents. For remote Hermes, call `hermes_delegate` once, then continue that run with `hermes_wait`, `hermes_status`, or `hermes_result`; a wait timeout never justifies a duplicate run.
- Codex may use its native collaboration/subagent capability when available. Codex has no remote Hermes transport in this project phase.
- If the active client has no suitable delegation mechanism, perform the task locally rather than inventing a transport.

Never launch Claude Code, OpenCode, or Codex recursively from Hermes. Preserve the existing project access boundary.

## Coordination

Run independent read-only investigations in parallel when this lowers latency. Avoid parallel writers to overlapping files. Review every returned result against current repository state, resolve conflicts, and run project-level verification after integration.

For Hermes-specific constraints, also read `hermes-delegation`.

Adapted from the Hermes Agent delegation guide and this repository's established transport split.
