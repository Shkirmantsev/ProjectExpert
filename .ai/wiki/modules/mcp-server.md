---
id: modules.mcp-server
title: Phase 6 MCP server module
kind: modules
status: active
summary: Phase 6 §36 MCP server — thin adapter over Phase 4 / 5 ports; 17 §36 tools + describe_capabilities; readiness-gated read tools and trust-boundary-gated write tools.
sourceRefs:
  - pi_platform/mcp/server.py
  - pi_platform/mcp/skill_plane.py
  - openspec/specs/2026-10-05-mcp-server/spec.md
  - openspec/specs/2026-10-05-skill-distribution-plane/spec.md
maintenance:
  mode: authored
related:
  - interfaces.mcp-tools
  - interfaces.skill-distribution
  - modules.orchestrator
---

# Phase 6 MCP server module

`pi_platform/mcp/server.py` and
`pi_platform/mcp/skill_plane.py` together form the
Phase 6 MCP server module. The server is a thin
adapter: it composes the Phase 4
`MultiStageRetrievalPort`, `HybridRetrievalPort`,
`ContextAssemblerPort` and the Phase 5
`QueryOrchestratorPort`, `LocalLLMPort`,
`TaskContextBuilderPort`, `CapabilityDiscoveryPort`.
It does not introduce a new runtime store.

## Entry points

- `McpServer.call_tool(name, arguments)` — deterministic
  dispatch; every handler enforces readiness first.
- `McpServer.list_tools()` — returns the union of the
  17 §36 tools and the documented extension
  `project.describe_capabilities`.
- `McpServer.serve(transport)` — boots the official MCP
  Python SDK over `stdio` (default) or Streamable HTTP.

## Skill distribution plane

`SkillDistributionPlane` exposes the canonical Agent
Skill under the documented URI namespace. Every
resource is content-addressed; two consecutive reads
return byte-identical bytes.

## Typed errors

The server wraps every tool handler and returns
`{"ok": false, "error": {"type": …}}` for any typed
failure, so callers branch without parsing prose.

## Tests

- `tests/test_mcp_server.py` — dispatch table and
  typed-error surface.
- `tests/test_skill_plane.py` — distribution plane
  manifest, byte-stability, escape and symlink
  rejection.
- `tests/test_phase_6_quality_gates.py` — §49
  integration fixtures against the server.