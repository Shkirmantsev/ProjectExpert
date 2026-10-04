---
id: wiki.index
title: Project Knowledge Index
kind: index
status: active
summary: Navigation entry point for durable project knowledge.
---

# Project Knowledge Index

Do not bulk-read this Wiki. Search first and retrieve only relevant documents/sections.

## Start here

- [Documentation map](../../docs/README.md)
- [Structure and ownership](../../docs/PROJECT_STRUCTURE.md)
- [Engineering conventions](../../docs/conventions/README.md)

- [System overview](architecture/system-overview.md)
- [Platform architecture overview (planned)](architecture/platform-overview.md)
- [Architecture baseline v0.8](../../project-intelligence-platform-architecture-v0.8.md)
- [Project map](project/project-map.md)
- [Implementation roadmap (v0.8)](project/implementation-roadmap.md)
- [Harness framework adoption](project/harness-framework-adoption.md)
- [Harness command lifecycle](project/harness-command-lifecycle.md)
- [AI task handoff lifecycle](project/task-handoff.md)
- [ADR: Separate harness core and integration skill ownership](adr/0001-separate-core-and-integration-skill-ownership.md)
- [ADR: Canonical vs runtime knowledge](adr/0002-canonical-runtime-separation.md)
- [ADR: License governance default](adr/0003-license-governance-default.md)
- [ADR: Ports-and-adapters extension style](adr/0004-ports-and-adapters-extension-style.md)
- [Domain glossary](glossary/domain.md)
- [Platform glossary](glossary/platform.md)
- [OpenSpec workflow](../../openspec/README.md) — current behavior and proposed changes.

## Knowledge areas

- `architecture/` — system boundaries, runtime flows, architecture views.
- `project/` — repository/module/tooling maps.
- `domain/` — business/domain knowledge.
- `modules/` — module/service/component descriptions.
- `interfaces/` — external/internal contracts and explanations.
- `adr/` — architecture decisions.
- `glossary/` — stable terminology.

## Machine entry points

When `project-context-mcp` is configured:

- `kb_search` — compact navigation cards.
- `kb_get` — selected Markdown sections/documents.
- `kb_neighbors` — explicit Wiki relationships.
- `code_symbol` — deterministic source symbol search.
- `spec_context` — OpenSpec current/change context.
- `kb_validate` / `kb_refresh` — consistency and local index refresh.