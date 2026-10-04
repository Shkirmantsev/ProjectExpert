@AGENTS.md

# Claude Code adapter

Use the portable project contract from `AGENTS.md`.

- Prefer the `project-context` MCP server for Wiki/context discovery when configured.
- Do not preload the Wiki tree. Search first, retrieve second.
- Task-specific procedures belong in skills, not in this always-loaded file.
- Preserve the active OpenSpec change ID, current task state, verification state, and unresolved findings when compacting context.
- Hermes, local-model workers, and web/browser MCPs are optional and are generated only when enabled in `.env`.
