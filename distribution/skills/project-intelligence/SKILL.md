---
name: project-intelligence
description: Use the Project Intelligence MCP server to retrieve version-correct project context, trace requirements, inspect architecture and dependencies, build bounded task context, and refresh or materialize approved project knowledge. Use before scanning the repository directly when project context is needed.
license: Apache-2.0
compatibility: Requires access to a compatible Project Intelligence MCP server. Designed for Agent-Skills-compatible coding agents; vendor adapters may add installation metadata.
metadata:
  author: "project-intelligence"
  version: "1.4.0"
  mcp-api: ">=1.3.0 <2.0.0"
  knowledge-schema: ">=0.7.0 <1.0.0"
  okf-profile: "0.2"
  distribution-schema: "1"
---

# Project Intelligence Agent Skill

Use the Project Intelligence MCP server (`project.*` tools) to
retrieve project knowledge, trace requirements, inspect
architecture and dependencies, build bounded task context, and
refresh or materialize approved project knowledge.

Prefer MCP retrieval over broad repository scanning whenever the
question can be expressed against the canonical knowledge model.
The MCP server is the canonical retrieval surface; the
repository is the secondary surface.

## Behaviour contract (10 steps)

1. Inspect project / version capabilities with
   `project.describe_capabilities` and `project.get_project_version`.
2. Prefer `project.search`, `project.retrieve_context`,
   `project.find_implementation`, `project.trace_requirement`,
   `project.find_references` and `project.get_*` over broad
   `Read` / `Glob` / `Grep` scans against the repository.
3. Use exact / symbol search when the identifier is known
   (`project.search` with the identifier; or `project.get_entity`
   for graph lookups).
4. Use hybrid `project.retrieve_context` for semantic questions;
   do NOT fall back to direct file scans until retrieval evidence
   is exhausted.
5. Follow requirement / spec / graph links rather than opening
   unrelated files; links are the canonical traversal order.
6. Request bounded `project.build_task_context` for
   implementation work so the implementation runs against a
   token-bounded bundle, not a full source dump.
7. Open raw source only for selected evidence or when retrieval
   has explicitly returned insufficient coverage; never as the
   first action.
8. Preserve version / security / project filters end-to-end; do
   not relax `validFrom`/`validTo` or `securityClassifications`.
9. Cite provenance returned by the server (`contentHash`,
   `sourceRepository`, `evidenceHash`); do not invent
   requirements, references or commit ids.
10. Materialise durable knowledge only through the explicit
    approved workflow (`project.materialize_knowledge`,
    `project.refresh_sources`) — never silently.

## When NOT to use a tool

- Do not call `project.materialize_knowledge` /
  `project.refresh_sources` without an `approval_id` issued by a
  trusted operator boundary; the server rejects unauthorized
  calls.
- Do not bypass the project readiness gate; the server refuses
  to serve when hydrate / reconcile is inconsistent.
- Do not invoke `project.search` / `project.retrieve_context`
  with no filters when a project version is known; pass the
  typed `ProjectVersion` so version-mismatched evidence is
  rejected.
- Do not escalate filtered L1 / L2 queries through the
  orchestrator; filtered L1 / L2 is rejected explicitly until a
  separately specified extension preserves the filters through
  escalation.

## Stale / conflicting knowledge

When the server reports `stale_fact_ids`, treat those facts as
informational only and prefer the freshest available
`current_state` from `project.get_entity` /
`project.find_implementation`. When the server reports
`conflicts`, surface the conflict to the operator; do not pick
silently.

## Incompatible server / skill versions

When `project.describe_capabilities` reports an unavailable
dimension (e.g. `a2aAdapterVersion`, `agentAdapterVersion`),
omit that capability entirely. When the MCP API version is
outside the `mcp-api` range declared in this skill's
`metadata`, upgrade the skill before continuing.

## Security policy

The server enforces the §48 supply-chain security gate: pinned
version, content hash, MCP API range, license allow-list, source
provenance, declared permissions and network requirements, and
the absence of hidden auto-install directives. Bypassing these
controls is forbidden.

## Read-only retrieval vs write / materialization

Tools prefixed `project.get_*`, `project.search`,
`project.retrieve_context`, `project.find_implementation`,
`project.trace_requirement`, `project.find_references`,
`project.get_conflicts`, `project.get_stale_knowledge`,
`project.get_project_version`, and `project.describe_capabilities`
are read-only and do not require approval.

`project.materialize_knowledge` and `project.refresh_sources`
are write / materialization actions and require an `approval_id`
issued by the trusted operator boundary.

## Reference material

For tool inventory, retrieval policy, version compatibility,
OKF profile, and security gate details, read the references
in `references/` in this order:

- `MCP-TOOLS.md` — every `project.*` tool, argument shape and
  return shape.
- `RETRIEVAL-POLICY.md` — the §33 retrieval-first agent access
  strategy and the L0 / L1 / L2 escalation rules.
- `VERSIONING.md` — the §39 nine-dimension compatibility
  handshake, identifier sets and the
  `VersionIncompatibleError` payload.
- `OKF-PROFILE.md` — the OKF v0.2 profile this platform targets
  and the `pi_` extension namespace.
- `SECURITY.md` — the §48 supply-chain security gate, the
  trusted approval boundary and the shared release identity.