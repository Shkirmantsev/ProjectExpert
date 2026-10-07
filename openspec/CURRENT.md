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
| [MCP server](specs/2026-10-05-mcp-server/spec.md) |
| [Skill distribution plane](specs/2026-10-05-skill-distribution-plane/spec.md) |
| [Agent skill canonical](specs/2026-10-05-agent-skill-canonical/spec.md) |
| [Version compatibility handshake](specs/2026-10-05-version-compatibility-handshake/spec.md) |
| [Codex plugin package](specs/2026-10-05-codex-plugin-package/spec.md) |
| [Claude Code plugin package](specs/2026-10-05-claude-code-plugin-package/spec.md) |
| [OpenCode plugin package](specs/2026-10-05-opencode-plugin-package/spec.md) |
| [Generic agent bundle](specs/2026-10-05-generic-agent-bundle/spec.md) |
| [Agent adapter contract](specs/2026-10-05-agent-adapter-contract/spec.md) |
| [Plugin supply chain security](specs/2026-10-05-plugin-supply-chain-security/spec.md) |

These product capabilities define the foundation, ingestion,
storage, retrieval, orchestration and agent integration phases of
the v0.8 Project Intelligence Platform. Subsequent phases
(Control plane, Security, Distribution, A2A and quality gates)
will introduce additional accepted capabilities. Create new specs
through the OpenSpec workflow (`openspec/changes/<id>/` →
`openspec/specs/YYYY-MM-DD-domain-capability/`) and link them here
when adopted.

Maintain this inventory with every accepted addition, retirement or identity
migration. Dates record first acceptance, not the latest edit. Run
`python harness.py openspec-check` to verify its completeness and naming.