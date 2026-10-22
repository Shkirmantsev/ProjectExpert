# Accepted project state ("actual is")

This is the central entry point for this repository's agreed current requirements.
The linked specs are canonical; this inventory does not duplicate their content.
The Wiki explains observed implementation. Report any discrepancy between specs
and implementation explicitly. Proposed changes are excluded from this view.

## Framework-provided capabilities

The development harness (see `AGENTS.md` and `docs/README.md`) ships with the
following accepted capabilities. They document the harness contract, not the
project product.

| Accepted capability | Canonical requirements |
|---|---|
| Project initialization | [Spec](specs/2026-09-07-project-initialization/spec.md) |
| Session handoff | [Spec](specs/2026-09-07-session-handoff/spec.md) |
| Skill integration | [Spec](specs/2026-09-07-skill-integration/spec.md) |
| Portable harness tooling | [Spec](specs/2026-10-03-portable-harness-tooling/spec.md) |
| Harness command lifecycle | [Spec](specs/2026-10-04-harness-command-lifecycle/spec.md) |
| OpenSpec governance | [Spec](specs/2026-10-03-openspec-governance/spec.md) |

## Project product capabilities

| Accepted capability | Canonical requirements |
| --- | --- |
| [Project knowledge repository layout](specs/2026-10-04-project-knowledge-repository-layout/spec.md) |
| [Canonical knowledge schema](specs/2026-10-04-canonical-knowledge-schema/spec.md) |
| [Git version aware runtime](specs/2026-10-04-git-version-aware-runtime/spec.md) |
| [Bidirectional canonical runtime sync](specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md) |
| [License governance](specs/2026-10-04-license-governance/spec.md) |
| [Content addressed processing](specs/2026-10-04-content-addressed-processing/spec.md) |
| [Context enrichment](specs/2026-10-04-context-enrichment/spec.md) |
| [Document source adapters](specs/2026-10-04-document-source-adapters/spec.md) |
| [Ingestion pipeline driver](specs/2026-10-04-ingestion-pipeline-driver/spec.md) |
| [Jar dependency intelligence](specs/2026-10-04-jar-dependency-intelligence/spec.md) |
| [Local source inbox](specs/2026-10-04-local-source-inbox/spec.md) |
| [Openspec change adapter](specs/2026-10-04-openspec-change-adapter/spec.md) |
| [Semantic structural chunking](specs/2026-10-04-semantic-structural-chunking/spec.md) |
| [Structured code intelligence](specs/2026-10-04-structured-code-intelligence/spec.md) |
| [Embedded storage selection](specs/2026-10-04-embedded-storage-selection/spec.md) |
| [Runtime store](specs/2026-10-04-runtime-store/spec.md) |
| [Sparse index](specs/2026-10-04-sparse-index/spec.md) |
| [Dense index](specs/2026-10-04-dense-index/spec.md) |
| [Full text index](specs/2026-10-04-full-text-index/spec.md) |
| [Sharded graph](specs/2026-10-04-sharded-graph/spec.md) |
| [Graph expansion](specs/2026-10-04-graph-expansion/spec.md) |
| [Provenance state model](specs/2026-10-04-provenance-state-model/spec.md) |
| [Freshness tracking](specs/2026-10-04-freshness-tracking/spec.md) |
| [Embedding model](specs/2026-10-04-embedding-model/spec.md) |
| [Hybrid retrieval](specs/2026-10-04-hybrid-retrieval/spec.md) |
| [Multi stage retrieval](specs/2026-10-04-multi-stage-retrieval/spec.md) |
| [Graph expansion production](specs/2026-10-04-graph-expansion-production/spec.md) |
| [Reranker port](specs/2026-10-04-reranker-port/spec.md) |
| [Metadata filters](specs/2026-10-04-metadata-filters/spec.md) |
| [Context assembler](specs/2026-10-04-context-assembler/spec.md) |
| [Retrieval benchmark](specs/2026-10-04-retrieval-benchmark/spec.md) |
| [Query orchestrator](specs/2026-10-05-query-orchestrator/spec.md) |
| [Local LLM port](specs/2026-10-05-local-llm-port/spec.md) |
| [Task context builder](specs/2026-10-05-task-context-builder/spec.md) |
| [Capability discovery](specs/2026-10-05-capability-discovery/spec.md) |
| [Retrieval first policy](specs/2026-10-05-retrieval-first-policy/spec.md) |
| [MCP server](specs/2026-10-07-mcp-server/spec.md) |
| [Skill distribution plane](specs/2026-10-07-skill-distribution-plane/spec.md) |
| [Agent skill canonical](specs/2026-10-07-agent-skill-canonical/spec.md) |
| [Version compatibility handshake](specs/2026-10-07-version-compatibility-handshake/spec.md) |
| [Codex plugin package](specs/2026-10-07-codex-plugin-package/spec.md) |
| [Claude Code plugin package](specs/2026-10-07-claude-code-plugin-package/spec.md) |
| [OpenCode plugin package](specs/2026-10-07-opencode-plugin-package/spec.md) |
| [Generic agent bundle](specs/2026-10-07-generic-agent-bundle/spec.md) |
| [Agent adapter contract](specs/2026-10-07-agent-adapter-contract/spec.md) |
| [Plugin supply chain security](specs/2026-10-07-plugin-supply-chain-security/spec.md) |
| [Control Registry](specs/2026-10-08-control-registry/spec.md) |
| [Hook Runtime](specs/2026-10-08-hook-runtime/spec.md) |
| [Policy Engine](specs/2026-10-08-policy-engine/spec.md) |
| [Secret Provider](specs/2026-10-08-secret-provider/spec.md) |
| [Audit Log](specs/2026-10-08-audit-log/spec.md) |
| [Feature Flags](specs/2026-10-08-feature-flags/spec.md) |
| [UI Extension Registry](specs/2026-10-08-ui-extension/spec.md) |
| [Capabilities](specs/2026-10-08-capabilities/spec.md) |
| [Enterprise Security Boundary](specs/2026-10-11-enterprise-security-boundary/spec.md) |
| [Human interface web UI](specs/2026-10-11-human-interface-web-ui/spec.md) |
| [OKF wiki profile distribution](specs/2026-10-11-okf-wiki-profile-distribution/spec.md) |
| [One-click distribution](specs/2026-10-11-one-click-distribution/spec.md) |
| [A2A adapter](specs/2026-10-12-a2a-adapter/spec.md) |
| [External coding agent integration](specs/2026-10-12-external-coding-agent-integration/spec.md) |
| [Integration quality gates](specs/2026-10-12-integration-quality-gates/spec.md) |
| [Retrieval candidate selection](specs/2026-10-16-retrieval-candidate-selection/spec.md) |
| [Retrieval trace](specs/2026-10-16-retrieval-trace/spec.md) |
| [Embedding execution profile](specs/2026-10-16-embedding-execution-profile/spec.md) |
| [Rich document graph](specs/2026-10-16-rich-document-graph/spec.md) |
| [Resumable document ingestion](specs/2026-10-16-resumable-document-ingestion/spec.md) |
| [Production runtime configuration resolver](specs/2026-10-18-production-runtime-configuration-resolver/spec.md) |
| [Embedding port query/document roles](specs/2026-10-18-embedding-port-query-document-roles/spec.md) |
| [Real EmbeddingGemma 2 binding](specs/2026-10-18-real-embeddinggemma2-binding/spec.md) |
| [Real Qwen3 embedding binding](specs/2026-10-18-real-qwen3-embedding-binding/spec.md) |
| [Semantic index service](specs/2026-10-18-semantic-index-service/spec.md) |
| [Real USearch dense backend](specs/2026-10-18-real-usearch-dense-backend/spec.md) |
| [Unified production retrieval composition](specs/2026-10-18-unified-production-retrieval-composition/spec.md) |
| [Persisted runtime snapshot reconciliation](specs/2026-10-18-persisted-runtime-snapshot-reconciliation/spec.md) |
| [Repository source discovery incremental](specs/2026-10-18-repository-source-discovery-incremental/spec.md) |
| [Real Docling PDF adapter and hybrid chunker](specs/2026-10-18-real-docling-pdf-adapter-and-hybrid-chunker/spec.md) |
| [One-command production UX](specs/2026-10-18-one-command-production-ux/spec.md) |
| [Production capability and release gates](specs/2026-10-18-production-capability-and-release-gates/spec.md) |

These product capabilities define the foundation, ingestion,
storage, retrieval, orchestration, agent integration,
control plane, security, distribution, A2A and quality-gate
phases of the v0.8 Project Intelligence Platform. The Phase 10
capabilities close the v0.8 roadmap and ship the v1.0 release
evidence (container image tag, OCI artefact, distribution
bundles). The 2026-10-16 capabilities are the v0.8 refinement
adopted from the `improve-ingestion-retrieval-local-models`
change (Change Packages A–J + H). Create new specs through the
OpenSpec workflow (`openspec/changes/<id>/` →
`openspec/specs/YYYY-MM-DD-domain-capability/`) and link them
here when adopted.

Maintain this inventory with every accepted addition, retirement or identity
migration. Dates record first acceptance, not the latest edit. Run
`python harness.py openspec-check` to verify its completeness and naming.
## Production reconciliation adoption — 2026-10-22

Existing capability identities retain their original dates. The current Gemma
binding now requires image-aware loading, one-command startup records effective
model settings before snapshot identity, CPU distribution provisions model/OCR
assets automatically, and license governance accepts only the exact approved
closure. These contracts have local implementation evidence. The broader
`ship-portable-oci-deployment` change remains active: physical GPU/Windows
acceptance and remote GHCR publication are not completed or certified here.
