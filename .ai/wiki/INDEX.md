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

- [Portable deployment architecture](architecture/portable-deployment.md)
- [ADR: Portable model runtimes and OCI kit](adr/0029-portable-model-runtime-and-oci-kit.md)
- [ADR: LLM Wiki as the curated knowledge layer](adr/0030-llm-wiki-as-curated-knowledge.md)
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
- [ADR: Phase 7 central policy engine](adr/0014-control-plane-policy-engine.md)
- [ADR: Phase 7 secret references and redaction](adr/0015-secret-references-and-redaction.md)
- [ADR: Phase 7 audit vs operational log separation](adr/0016-audit-vs-operational-log-separation.md)
- [Platform core modules](modules/platform-core.md)
- [Inference runtime module](modules/inference-runtime.md)
- [LLM Wiki module](modules/llm-wiki.md)
- [Phase 7 Feature / Plugin Registry module map](modules/registry.md)
- [Phase 7 Hook Runtime module map](modules/hooks.md)
- [Phase 7 Policy Engine module map](modules/policy-engine.md)
- [Phase 7 Secret Provider module map](modules/secret-provider.md)
- [Phase 7 Audit Log module map](modules/audit-log.md)
- [Phase 7 Feature Flags module map](modules/feature-flags.md)
- [Phase 7 UI Extension Registry module map](modules/ui-extensions.md)
- [Phase 8 Enterprise Security Boundary module map](modules/security.md)
- [Phase 8 Egress Decision interface](interfaces/egress.md)
- [ADR: Phase 8 Enterprise Security Boundary](adr/0017-phase-8-enterprise-security-boundary.md)
- [Capability vocabulary interface](interfaces/capabilities.md)
- [Control Registry interface](interfaces/control-registry.md)
- [Hook Runtime interface](interfaces/hook-runtime.md)
- [Policy Engine interface](interfaces/policy-engine.md)
- [Secret Provider interface](interfaces/secret-provider.md)
- [Audit Log interface](interfaces/audit-log.md)
- [Feature Flags interface](interfaces/feature-flags.md)
- [UI Extension interface](interfaces/ui-extension.md)
- [Canonical interface](interfaces/canonical.md)
- [Git interface](interfaces/git.md)
- [Sync interface](interfaces/sync.md)
- [One-command production UX](interfaces/one-command-ux.md) — v0.8 production
- [Licensing interface](interfaces/licensing.md)
- [Phase 6 MCP server module](modules/mcp-server.md)
- [Phase 6 agent-integration core module](modules/agent-integration.md)
- [Phase 6 plugin packagers module](modules/plugin-packagers.md)
- [MCP server tool contracts](interfaces/mcp-tools.md)
- [Skill distribution plane contract](interfaces/skill-distribution.md)
- [Plugin distribution profiles](interfaces/plugin-distribution.md)
- [Version compatibility handshake contract](interfaces/version-compatibility.md)
- [Agent integration adapter contract](interfaces/agent-adapter-contract.md)
- [Plugin supply-chain security gate](interfaces/plugin-supply-chain.md)
- [Trusted approval boundary contract](interfaces/trusted-approval-boundary.md)
- [Knowledge readiness gate contract](interfaces/runtime-readiness.md)
- [Domain glossary](glossary/domain.md)
- [Platform glossary](glossary/platform.md)
- [OpenSpec workflow](../../openspec/README.md) — current behavior and proposed changes.

## Phase 2 ingestion

- [Phase 2 ingestion](modules/ingest.md)
- [Source adapter interface](interfaces/source-adapters.md)
- [Chunker interface](interfaces/chunker.md)
- [Tokenizer port](interfaces/tokenizer.md) — v0.8 refinement
- [Retrieval text builder port](interfaces/retrieval-text-builder.md) — v0.8 refinement
- [Inference policy port](interfaces/inference-policy.md) — v0.8 refinement
- [Local contextualizer port](interfaces/local-contextualizer.md) — v0.8 refinement
- [Context enrichment interface](interfaces/enrichment.md)
- [Use an isolated tree-sitter Java parser](adr/0006-phase-2-parser-selection.md)
- [Default inbox sources to LOCAL_ONLY](adr/0007-phase-2-inbox-policy-default.md)
- [Rich document graph as additive submodel](adr/0024-rich-document-graph-as-additive-submodel.md) — v0.8 refinement
- [InferencePolicy separate from source policy](adr/0027-inference-policy-separate-from-source-policy.md) — v0.8 refinement
- [Rich document graph architecture](architecture/rich-document-graph.md) — v0.8 refinement
- [DocumentGraphStorePort interface](interfaces/document-graph-store.md) — v0.8 refinement
- [IngestionJobStorePort interface](interfaces/ingestion-job-store.md) — v0.8 refinement

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
- [SelectionPort contract](interfaces/selection.md) — v0.8 refinement
- [EmbeddingProfile contract](interfaces/embedding-profile.md) — v0.8 refinement
- [Real Docling PDF binding](modules/docling-binding.md) — v0.8 production
- [Production release gate](modules/release-gate.md) — v0.8 production
- [VectorRecordStorePort contract](interfaces/vector-record-store.md) — v0.8 refinement
- [Retrieval trace module](modules/retrieval-trace.md) — v0.8 refinement
- [Embedding model selection](adr/0009-embedding-model-selection.md)
- [Hybrid fusion strategy](adr/0010-hybrid-fusion-strategy.md)
- [Rerank direct before graph expansion](adr/0025-rerank-direct-before-graph-expansion.md) — v0.8 refinement
- [EmbeddingProfile identity and vector namespace](adr/0026-embedding-profile-identity-and-vector-namespace.md) — v0.8 refinement
- [USearch as configuration-driven ANN backend](adr/0028-usearch-as-default-ann-backend.md) — v0.8 refinement
- [Non-destructive candidate selection](architecture/retrieval-candidate-selection.md) — v0.8 refinement
- [EmbeddingProfile identity architecture](architecture/embedding-profile-identity.md) — v0.8 refinement
- [Host embedding accelerator module](modules/host-embedding-accelerator.md) — v0.8 refinement
- [Retrieval evaluation corpus and quality gates](project/retrieval-evaluation-corpus.md) — v0.8 refinement
- [Deployment execution profiles](project/deployment-profiles.md) — v0.8 refinement
- [v0.8 ingestion and retrieval refinement invariants](invariants/v0.8-ingestion-retrieval.md) — v0.8 refinement

## Phase 5 orchestration

- [Phase 5 query orchestrator module map](modules/orchestrator.md)
- [Phase 5 local LLM port module map](modules/llm-port.md)
- [Phase 5 task context builder module map](modules/task-context.md)
- [CapabilityDiscoveryPort interface](interfaces/capability-discovery.md)

## Phase 6 preparation (proposed)

- [Phase 6 readiness and outstanding gaps](project/phase-6-readiness.md)

## Phase 6 agent integration (accepted)

- [ADR: Phase 6 agent integration packaging](adr/0011-agent-integration-packaging.md)
- [ADR: Phase 6 version compatibility handshake](adr/0012-version-compatibility-handshake.md)
- [ADR: Phase 6 plugin supply-chain security](adr/0013-plugin-supply-chain-security.md)

## Phase 7 control plane (accepted)

- [Phase 7 control plane module map](modules/registry.md) and related
  Phase 7 module maps (`hooks`, `policy-engine`, `secret-provider`,
  `audit-log`, `feature-flags`, `ui-extensions`).
- Phase 7 ADRs: `0014-control-plane-policy-engine.md`,
  `0015-secret-references-and-redaction.md`,
  `0016-audit-vs-operational-log-separation.md`.

## Phase 8 enterprise security (accepted)

- [Phase 8 Enterprise Security Boundary module map](modules/security.md)
- [Phase 8 Egress Decision interface](interfaces/egress.md)
- [ADR: Phase 8 Enterprise Security Boundary](adr/0017-phase-8-enterprise-security-boundary.md)

## Phase 9 distribution (accepted)

- [Phase 9 UI module map](modules/ui.md)
- [Phase 9 UI REST interface contract](interfaces/rest-api.md)
- [Phase 9 distribution vendor inventory](project/distribution-vendors.md)
- [ADR: Phase 9 REST transport choice](adr/0018-rest-transport.md)
- [ADR: Phase 9 static frontend equivalence](adr/0019-static-frontend-equivalence.md)
- [ADR: Phase 9 Open WebUI shim](adr/0020-open-webui-shim.md)

## Phase 10 A2A and final quality gates (accepted)

- [Phase 10 A2A adapter module map](modules/a2a.md)
- [Phase 10 Eval core module map](modules/eval.md)
- [A2A interface contract](interfaces/a2a.md)
- [Reverse Delegation interface contract](interfaces/reverse-delegation.md)
- [v0.8 §68 invariants (52)](invariants/v0.8.md)
- [ADR: Phase 10 A2A adapter isolation](adr/0021-a2a-adapter-isolation.md)
- [ADR: Phase 10 reverse delegation is opt-in by default](adr/0022-reverse-delegation-default-off.md)
- [ADR: Phase 10 A2A transport is stdlib-only for v1.0](adr/0023-stdlib-only-a2a-transport.md)

## Knowledge areas

- `architecture/` — system boundaries, runtime flows, architecture views.
- `project/` — repository/module/tooling maps.
- `domain/` — business/domain knowledge.
- `modules/` — module/service/component descriptions.
- `interfaces/` — external/internal contracts and explanations.
- `adr/` — architecture decisions.
- `glossary/` — stable terminology.
- `invariants/` — architecture invariant map and probe catalogue.

## Machine entry points

When `project-context-mcp` is configured:

- `kb_search` — compact navigation cards.
- `kb_get` — selected Markdown sections/documents.
- `kb_neighbors` — explicit Wiki relationships.
- `code_symbol` — deterministic source symbol search.
- `spec_context` — OpenSpec current/change context.
- `kb_validate` / `kb_refresh` — consistency and local index refresh.