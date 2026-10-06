# Context impact — implement-phase-6-agent-integration

The Wiki, ADR and `openspec/CURRENT.md` updates are
documented in
[`openspec/changes/prepare-phase-6-agent-integration/context-impact.md`](../../prepare-phase-6-agent-integration/context-impact.md).
This file is the implementation-side reference.

The implementation change creates the documented Wiki nodes
under `.ai/wiki/interfaces/`, `.ai/wiki/modules/` and
`.ai/wiki/adr/`, updates the platform glossary, the
project map, the implementation roadmap and the
`openspec/CURRENT.md` to add the ten Phase 6
capabilities. The pre-existing harness-side MCP server
at `tools/mcp/project-context-mcp/` is NOT modified by
this change; the two MCP servers are separate
deliverables owned by different scopes.

## Related knowledge

- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §5, §17, §33, §36, §37, §38, §39, §40, §41, §42,
  §43, §44, §45, §46, §47, §48, §49.