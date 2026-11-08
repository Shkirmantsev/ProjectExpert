# Proposal

## Why

ProjectExpert ships its Agent Skill over proprietary MCP resource URIs but does
not advertise or implement SEP-2640 discovery. A newly connected client cannot
find the bundled workflow using the Skills extension.

## Goal

Expose the shipped project-intelligence skill and supporting files using
io.modelcontextprotocol/skills, independently of target project initialization,
chat models, and index readiness.

## Affected capabilities

- 2026-10-07-skill-distribution-plane
- MCP discovery and bundled container resource delivery

## Compatibility / migration impact

Preserve initialize and all existing version-pinned resource URIs. Add standard
skill URIs and discovery; no runtime dependency or target project file copying.
Client-side activation remains subject to client support and user policy.

## Related knowledge

- .ai/wiki/interfaces/skill-distribution.md
- https://skills.extensions.modelcontextprotocol.io/specification/beta/skills
