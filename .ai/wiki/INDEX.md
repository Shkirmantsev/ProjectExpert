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
- [Platform architecture overview](architecture/platform-overview.md)
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
- [ADR: Platform source language](adr/0005-platform-source-language.md)
- [Platform core modules](modules/platform-core.md)
- [Canonical interface](interfaces/canonical.md)
- [Git interface](interfaces/git.md)
- [Sync interface](interfaces/sync.md)
- [Licensing interface](interfaces/licensing.md)
- [Domain glossary](glossary/domain.md)
- [Platform glossary](glossary/platform.md)
- [OpenSpec workflow](../../openspec/README.md) — current behavior and proposed changes.

## Phase 2 ingestion

- [Phase 2 ingestion](modules/ingest.md)
- [Source adapter interface](interfaces/source-adapters.md)
- [Chunker interface](interfaces/chunker.md)
- [Context enrichment interface](interfaces/enrichment.md)
- [Use an isolated tree-sitter Java parser](adr/0006-phase-2-parser-selection.md)
- [Default inbox sources to LOCAL_ONLY](adr/0007-phase-2-inbox-policy-default.md)

## Phase 3 storage

- [Phase 3 runtime store module map](modules/runtime-store.md)
- [Phase 3 sharded graph module map](modules/graph.md)
- [RuntimeStorePort interface](interfaces/runtime-store.md)
- [SparseIndexPort interface](interfaces/sparse-index.md)
- [DenseIndexPort interface](interfaces/dense-index.md)
- [FullTextIndexPort interface](interfaces/full-text-index.md)
- [GraphExpansionPort interface (Phase 4 preview)](interfaces/graph-expansion.md)
- [ProvenancePort interface](interfaces/provenance.md)
- [FreshnessTrackerPort interface](interfaces/freshness.md)
- [Embedded storage engine selection](adr/0008-embedded-storage-selection.md)

## Phase 4 retrieval

- [Phase 4 retrieval module map](modules/retrieval.md)
- [Phase 4 embedding-model module map](modules/embeddings.md)
- [Phase 4 context-assembler module map](modules/context-assembler.md)
- [HybridRetrievalPort interface](interfaces/hybrid-retrieval.md)
- [RerankerPort interface](interfaces/reranker.md)
- [Embedding model selection](adr/0009-embedding-model-selection.md)
- [Hybrid fusion strategy](adr/0010-hybrid-fusion-strategy.md)

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