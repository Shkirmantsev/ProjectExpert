# Context impact

## Knowledge to create

- none

## Knowledge to update

- .ai/wiki/interfaces/skill-distribution.md
- distribution/deployment/README.md

## Knowledge to review for staleness

- .ai/wiki/modules/mcp-server.md

## Affected implementation

- pi_platform/mcp/skill_plane.py: complete immutable manifests and aliases
- pi_platform/mcp/server.py: discovery and resource dispatch
- pi_platform/cli/main.py: use installed bundle for arbitrary target projects
- scripts/smoke_production_container.py: packaged endpoint integrity checks

## ADR impact

None: preserves the existing resources-based distribution architecture.

## Acceptance criteria

- [x] Wiki reflects verified behavior and explains client activation limits.
- [x] Focused protocol, HTTP, stdio and packaged-container checks pass.
- [x] Current specs adopt verified behavior without presenting proposals as current.
- [x] Full harness and artifact manifest pass.
