---
id: interfaces.mcp-tools
title: MCP server tool contracts
kind: interfaces
status: active
summary: Phase 6 §36 MCP server — 17 semantic tools + describe_capabilities; thin adapter over the Phase 4 / 5 ports; readiness-gated read tools and trust-boundary-gated write tools.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md#36
  - project-intelligence-platform-architecture-v0.8.md#47
  - pi_platform/mcp/server.py
  - openspec/specs/2026-10-05-mcp-server/spec.md
maintenance:
  mode: authored
related:
  - interfaces.skill-distribution
  - interfaces.version-compatibility
  - interfaces.agent-adapter-contract
  - interfaces.plugin-supply-chain
---

# MCP server tool contracts

The MCP server is a thin adapter over the Phase 4
retrieval ports and the Phase 5 orchestration ports. It
exposes the 17 §36 semantic tools plus the documented
extension tool `project.describe_capabilities`; no
additional tool is allowed to shadow a §36 name.

## Read-only tools

The read-only tools consult `KnowledgeReadinessPort` and
return `RuntimeNotReadyError` when the runtime project
knowledge is not in a consistent state.

| Tool | Purpose |
|---|---|
| `project.search` | Hybrid exact + dense search. |
| `project.retrieve_context` | Multi-stage retrieval + bounded assembly. |
| `project.get_entity` | Graph lookup; uses `ProvenancePort.evidence`, never invents records. |
| `project.get_component` | Same shape, by component URI. |
| `project.get_requirement` | Same shape, by `requirementId`. |
| `project.get_spec` | Same shape, by OpenSpec spec id. |
| `project.get_architecture` | Wiki architecture index. |
| `project.get_dependency` | Dependency record lookup. |
| `project.find_implementation` | Graph traversal requirement → component. |
| `project.trace_requirement` | End-to-end trace. |
| `project.find_references` | Inverse: code symbol → requirements. |
| `project.get_project_version` | Runtime `VersionIdentity`. |
| `project.get_conflicts` | Conflict map (per-entity evidence chains). |
| `project.get_stale_knowledge` | `staleness_map`. |
| `project.build_task_context` | Bounded task-context bundle. |

## Write / materialisation tools

Both tools require an `approval_id` issued by
`TrustedApprovalBoundary`. The boundary is HMAC-SHA-256
scoped to action, repository, change_ids and validity
window. The server fails closed when no operator key is
configured.

| Tool | Purpose |
|---|---|
| `project.materialize_knowledge` | Materialise durable changes. |
| `project.refresh_sources` | Trigger hydrate / reconcile cycle. |

## Extension tools

| Tool | Purpose |
|---|---|
| `project.describe_capabilities` | Returns `CapabilityDescriptor` (legacy + nine-dimension block). |

## Typed errors

- `RuntimeNotReadyError` — readiness gate failed.
- `ApprovalRejected` — typed reason from `TrustedApprovalBoundary`.
- `VersionIncompatibleError` — typed reason from the handshake.
- `FilteredEscalationNotSupportedError` — typed reason from the orchestrator.
- `UnknownToolError` — unrecognised tool name.

## Return shape

Every tool returns `{"ok": bool, ...}` so the caller can
branch on success without parsing prose.