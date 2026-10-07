---
id: architecture.platform-overview
title: Platform Architecture Overview
kind: architecture
status: active
summary: High-level boundaries, runtime flows, control plane and data plane responsibilities of the v0.8 Project Intelligence Platform; describes the Phase 1–5 implementation and the boundary between this implementation project and the runtime data it operates on.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/plan-v0-8-platform-architecture/proposal.md
  - openspec/changes/plan-v0-8-platform-architecture/design.md
  - openspec/changes/archive/2026-10-04-implement-phase-1-foundation/design.md
  - pi_platform/core/canonical/value_types.py
  - pi_platform/core/sync/hydrate.py
  - pi_platform/core/licensing/policy.py
maintenance:
  mode: authored
---

# Platform Architecture Overview

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
is the agreed target. This page mirrors only the boundaries that
downstream agents must respect while the platform is implemented
phase by phase. Phase 1 ships the foundation documented in the
accepted specs
[`project-knowledge-repository-layout`](../../../openspec/specs/2026-10-04-project-knowledge-repository-layout/spec.md),
[`canonical-knowledge-schema`](../../../openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md),
[`git-version-aware-runtime`](../../../openspec/specs/2026-10-04-git-version-aware-runtime/spec.md),
[`bidirectional-canonical-runtime-sync`](../../../openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md) and
[`license-governance`](../../../openspec/specs/2026-10-04-license-governance/spec.md).

## What this repository is

This repository is the **implementation project** for the v0.8
Project Intelligence Platform. It contains:

- the platform source tree under `pi_platform/` (Python 3.11,
  hexagonal/ports-and-adapters + micro-kernel extension style);
- the container build files (`Containerfile`, `docker-compose.yml`,
  launcher scripts) and the OCI distribution artefacts;
- planned control-plane UI, plugin generation pipelines and canonical Agent
  Skill (future phases; scaffolding is not a released integration);
- the OpenSpec governance of the platform
  (`openspec/specs/` for accepted behaviour, `openspec/changes/`
  for proposed behaviour);
- the durable Wiki (`.ai/wiki/`) and ADRs that document the design
  and link back to OpenSpec specs and source code;
- the harness framework that automates the project's own
  development workflow.

The runtime data the platform operates on lives **outside this
repository**: the container image built from this repo binds to a
target project and reads/writes `project-knowledge/`,
`.project-intelligence-cache/` and `tmp/local/source/` in that target
project's tree. Runtime artefact generation (vector indexes,
embedding caches, model caches, runtime logs, capability state, ...)
lives inside the container's ephemeral storage and never goes inside
this implementation repo either.

## Architectural style

- **Hexagonal / Ports-and-Adapters core.** Business logic depends on
  ports; adapters implement ports for specific technologies.
- **Micro-kernel / Plugin extension surface.** Optional capabilities
  are registered through stable extension APIs and never coupled to
  the core domain.
- **Single modular deployable.** Default distribution is one
  container (or one container plus an optional UI/runtime sidecar).

The Phase 1 implementation is in Python 3.11 per
[`adr.platform-source-language`](../adr/0005-platform-source-language.md);
the core stays language-neutral at the boundary by declaring every
Phase 1 capability as a port in `pi_platform/ports/` and shipping
the default adapter in `pi_platform/adapters/`.

## Control plane and data plane

The platform separates:

- **Control plane** — UI/CLI/automation for configuration, policies,
  permissions, plugin/feature lifecycle, hooks, secret references,
  environment mappings, diagnostics, audit, health and administration.
- **Data plane** — ingestion, indexing, retrieval, graph operations,
  context assembly, MCP tool execution, A2A requests and runtime
  agent work.

The control plane configures and observes the data plane but does
not bypass the same authorization rules that apply to agents and
plugins. Both planes call into the same central Policy Engine for
authorization decisions. Phase 1 ships a Phase 1 policy stub
(`pi_platform.core.sync.policy_stub.PolicyDecisionStub`) that
returns `ALLOW` for `hydrate`/`reconcile` and `REQUIRE_APPROVAL`
for `materialise` by default.

## Module map (Phase 1 implemented)

The Phase 1 implementation lives under `pi_platform/`:

```text
pi_platform/
├── core/                  # domain logic, value types, ports
│   ├── canonical/         # value types, content addressing, manifest, OKF
│   ├── git/               # CLI adapter, version identity, working-tree overlay
│   ├── sync/              # hydrate / reconcile / materialise / WAL / lock
│   ├── licensing/         # policy / gate / inventory / SBOM emitter
│   ├── ingest/            # PipelineDriver, local source inbox scanner
│   └── runtime/           # runtime-store, graph, provenance, freshness re-exports
├── ports/                 # abstract port interfaces
│   ├── ingest/            # Phase 2 source / chunker / enricher / driver ports
│   └── runtime/           # Phase 3 store, indexes, graph, provenance, freshness ports
├── adapters/
│   ├── fs/                # local filesystem adapter
│   ├── git/               # git CLI adapter
│   ├── markdown/, html/, pdf/, openapi/  # shared Markdown / HTML adapters
│   ├── java/              # tree-sitter-java subprocess, java_structured_adapter, jar
│   ├── openspec/          # openspec-change-adapter
│   ├── ingest/            # default PipelineDriver, chunkers, enrichers
│   └── runtime/           # SqliteRuntimeStore, Bm25SparseIndex, FlatDenseIndex,
│                          # SqliteFtsFullTextIndex, LocalShardedGraph, etc.
├── runtime/               # content-addressed filesystem cache (Phase 1 shim over Phase 3)
└── cli/                   # `python -m pi_platform.cli` entry point
project-knowledge/         # canonical knowledge tree (target repo, Phase 1)
.project-intelligence-cache/  # runtime cache (target repo, gitignored)
distribution/             # generated artefacts (target repo, Phase 1)
├── licenses/              # dependency inventory, model licenses
├── skills/                # placeholder, Phase 6
├── codex/                 # placeholder, Phase 6
├── claude-code/           # placeholder, Phase 6
├── opencode/              # placeholder, Phase 6
├── generic-agent/         # placeholder, Phase 6
└── sbom/                  # SPDX SBOM, NOTICE
```

The CLI exposes `init-project`, `hydrate`, `materialise`,
`license-gate`, `okf-validate`, `version-identity`, `wal-recover`,
`ingest-sources`, `runtime-status`, `graph-rebuild` and `health`. The Phase 1 implementation targets the
`core-headless` docker-compose profile; later phases light up
`desktop-lite`, `desktop-local-ai`, `open-webui` and
`enterprise`.

The Python package name is `pi_platform` (not `platform`) because the
latter collides with the Python standard-library `platform` module.
The directory layout (`platform/` per §64) maps to the
`pi_platform/` Python module name; the container `Containerfile` and
the launcher scripts both import `pi_platform.cli` so there is no
runtime impact.

## Wiki and OpenSpec dual-track evolution

As the implementation progresses, both the Wiki and OpenSpec evolve
in parallel:

- the **Wiki** carries durable navigation pages (`architecture/`,
  `project/`, `modules/`, `interfaces/`, `adr/`, `glossary/`) that
  describe design, modules, distribution, ADRs and operational
  guidance. They do not duplicate OpenSpec normative text.
- **OpenSpec** carries the normative behavioural requirements
  (`openspec/specs/<dated-capability>/spec.md`) and the proposed
  changes (`openspec/changes/<id>/`). Implementation code MUST
  trace back to accepted specs.
- every implementation phase updates both the Wiki (new module /
  interface / ADR pages) and OpenSpec (new or modified capability
  specs).

## Source-of-truth hierarchy

The platform distinguishes between durable sources of truth:

1. `openspec/specs/` — agreed current behaviour (canonical);
2. source code and tests — implementation evidence;
3. `.ai/wiki/` — durable human-readable explanation of the project;
4. ADRs — accepted architectural decisions and rationale;
5. Git history — historical evidence;
6. external documentation — business, protocol, requirements evidence
   with explicit provenance.

Generated Wiki information MUST never silently override normative
specifications or verified source evidence.

## Phase 1 foundation capabilities (accepted)

The five Phase 1 capabilities are accepted in
`openspec/specs/2026-10-04-*`:

- [`project-knowledge-repository-layout`](../../../openspec/specs/2026-10-04-project-knowledge-repository-layout/spec.md)
  — canonical on-disk layout (`project-knowledge/`,
  `.project-intelligence-cache/`, `tmp/local/source/`,
  `distribution/`), `project-context.yaml` contract,
  `.gitignore` contract.
- [`canonical-knowledge-schema`](../../../openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md)
  — deterministic canonical serialization, SHA-256 content
  addressing, sharded canonical storage, manifest-driven
  hydration, chunk model and hierarchy, knowledge provenance
  state model, OKF v0.2 Wiki profile, isolated `OkfAdapter`,
  forward compatibility with future OKF revisions.
- [`git-version-aware-runtime`](../../../openspec/specs/2026-10-04-git-version-aware-runtime/spec.md)
  — runtime project version identity tuple, Git-state
  transitions, working-tree overlay, cross-branch content reuse,
  Git LFS strategy.
- [`bidirectional-canonical-runtime-sync`](../../../openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md)
  — hydrate, enrich, materialise, round-trip preservation,
  incremental branch-switch reconciliation, stale-knowledge
  detection.
- [`license-governance`](../../../openspec/specs/2026-10-04-license-governance/spec.md)
  — dependency inventory, SPDX tracking, allow/review/deny
  policy, model-license separate tracking, SBOM/NOTICE, CI gate,
  dynamic plugin/hook verification.

## Implementation phases (summary)

The full ordered task list is in
[`plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/plan-v0-8-platform-architecture/tasks.md).
Summary of phases:

| Phase | Name | Depends on | Status |
|---|---|---|---|
| 0 | Plan | — | complete |
| 1 | Foundation | Phase 0 | complete (this change) |
| 2 | Ingestion (parsers, content addressing) | Phase 1 | complete |
| 3 | Storage (runtime DB, sharded graph) | Phase 2 | complete |
| 4 | Retrieval (hybrid, multi-stage, reranking) | Phase 3 | complete |
| 5 | Orchestration (query, local LLM, task context) | Phase 4 | complete |
| 6 | Agent integration (MCP, skill, adapters) | Phase 5 | complete |
| 7 | Control plane (registry, hooks, capabilities, secrets) | Phase 6 | planned |
| 8 | Security (enterprise boundary) | Phase 7 | planned |
| 9 | Distribution (UI, container, OCI, one-click) | Phase 8 | planned |
| 10 | A2A and final quality gates | Phase 9 | planned |

## Evidence

- [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  — v0.8 baseline.
- [`openspec/changes/plan-v0-8-platform-architecture/proposal.md`](../../../openspec/changes/plan-v0-8-platform-architecture/proposal.md)
  — planning proposal.
- [`openspec/changes/plan-v0-8-platform-architecture/design.md`](../../../openspec/changes/plan-v0-8-platform-architecture/design.md)
  — planning technical design.
- [`openspec/changes/plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/plan-v0-8-platform-architecture/tasks.md)
  — ordered implementation tasks.
- [`openspec/changes/implement-phase-1-foundation/design.md`](../../../openspec/changes/archive/2026-10-04-implement-phase-1-foundation/design.md)
  — Phase 1 implementation design.
- [`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py)
  — Phase 1 regression suite.
- [`.ai/AGENTS.md`](../../../.ai/AGENTS.md) and
  [`AGENTS.md`](../../../AGENTS.md) — agent contracts.
- [`openspec/CURRENT.md`](../../../openspec/CURRENT.md) — accepted
  capabilities inventory.

## Phase 2 ingestion

The [ingestion module](../modules/ingest.md) implements PipelineDriver, source adapters,
structural chunking, layered enrichment, content-address reuse and inbox policies.
SourcePromotionPolicy distinguishes LOCAL_ONLY, REFERENCE and SNAPSHOT; parser
subprocesses and cache records carry explicit provenance. See the
[source interface](../interfaces/source-adapters.md), [chunker](../interfaces/chunker.md)
and [enrichment](../interfaces/enrichment.md) contracts. Persistent storage and retrieval
remain future phases.

## Phase 3 storage

The Phase 3 storage layer ships the runtime store, three indexes, the sharded
canonical knowledge graph, provenance / freshness and the
[Phase 3 `GraphExpansionPort` preview](../interfaces/graph-expansion.md) the
Phase 4 production adapter closes. The runtime store port lives under
[`pi_platform.ports.runtime`](../modules/runtime-store.md).

## Phase 4 retrieval

The Phase 4 retrieval layer composes the Phase 3 storage surface and the §25
embedding model into the §27 hybrid retrieval, the §29 multi-stage pipeline, the
§30 pluggable reranker, the §24 / §56 metadata filters, the §31 production graph
expansion, the §32 context assembler and the §49 evaluation fixture. The Phase 4
module map lives under
[`modules/retrieval`](../modules/retrieval.md); the embedding layer lives under
[`modules/embeddings`](../modules/embeddings.md); the context assembler lives
under [`modules/context-assembler`](../modules/context-assembler.md); the
hybrid retrieval and reranker port contracts live under
[`interfaces/hybrid-retrieval`](../interfaces/hybrid-retrieval.md) and
[`interfaces/reranker`](../interfaces/reranker.md) respectively.

The selection of the stdlib-only hashing embedding model as the default
multilingual fallback (with the opt-in multilingual sentence-transformer
adapter) is recorded in
[ADR 0009](../adr/0009-embedding-model-selection.md). The selection of RRF as
the default hybrid fusion strategy (with the linear weighted sum fallback) is
recorded in [ADR 0010](../adr/0010-hybrid-fusion-strategy.md). The Phase 3
[`graph-expansion`](../interfaces/graph-expansion.md) preview port is closed
by the [`pi_platform.adapters.runtime.graph_expansion`](../../../pi_platform/adapters/runtime/graph_expansion.py)
production adapter; the Phase 3 stub
[`BoundedGraphExpansion`](../../../pi_platform/adapters/runtime/bounded_graph_expansion.py)
remains in place so Phase 3 regression tests keep their binding.

## Phase 5 orchestration

The Phase 5 orchestration layer composes the Phase 4 retrieval surface and
the optional Phase 5 `LocalLLMPort` into the three-level
[`QueryOrchestrator`](../modules/orchestrator.md) (L0 direct retrieval,
L1 retrieval + small local LLM, L2 strong external agent), the bounded
[`TaskContextBuilder`](../modules/task-context.md) the L2 path emits,
the optional [`LocalLLM`](../modules/llm-port.md) stub that ships in the
default container, and the deterministic
[`CapabilityDiscovery`](../interfaces/capability-discovery.md) that
reports the §47 descriptor. The §33 retrieval-first escalation policy is
encoded in the orchestrator and asserted by the
`tests/test_orchestration_policy.py` regression test.

## Phase 6 agent integration

The Phase 6 agent integration layer ships:

- the [`McpServer`](../modules/mcp-server.md) (17 §36 tools +
  `describe_capabilities`) composing the Phase 4 retrieval ports
  and the Phase 5 orchestration ports;
- the [`SkillDistributionPlane`](../interfaces/skill-distribution.md)
  exposing the canonical Agent Skill under the documented URI
  namespace;
- the [`DefaultVersionCompatibilityPolicy`](../interfaces/version-compatibility.md)
  enforcing the §39 nine-dimension handshake with a typed
  `VersionIncompatibleError`;
- the [`PluginSupplyChainSecurityGate`](../interfaces/plugin-supply-chain.md)
  enforcing the §48 supply-chain controls; the verdict is
  recorded in every bundle's `PROVENANCE.json`;
- the [`TrustedApprovalBoundary`](../interfaces/trusted-approval-boundary.md)
  (HMAC-SHA-256) replacing the prior stub that accepted any
  non-empty token; both write tools fail closed until an
  operator key is configured;
- the [`KnowledgeReadinessPort`](../interfaces/runtime-readiness.md)
  gate that every MCP tool consults before serving evidence;
- four per-vendor
  [`plugin packagers`](../modules/plugin-packagers.md) (Codex /
  Claude Code / OpenCode / generic agent) driven by one
  `ReleaseInputSet` and coordinated by `DeterministicBuildRunner`;
- the canonical [`AgentIntegrationAdapter`](../interfaces/agent-adapter-contract.md)
  base exposing the documented eight operations and the typed
  error vocabulary;
- the [`AgentIntegration` core](../modules/agent-integration.md)
  carrying the version handshake, supply-chain gate, adapter
  base and trusted-approval boundary.

The §49 integration quality gate fixtures
(`tests/test_phase_6_quality_gates.py`) exercise the documented
representative agent scenarios against the deterministic Phase 6
surface. Live agent evals remain optional and are reported
separately. Three ADRs (`0011-agent-integration-packaging`,
`0012-version-compatibility-handshake`,
`0013-plugin-supply-chain-security`) record the Phase 6
decisions. The harness MCP server
(`tools/mcp/project-context-mcp/`) remains a separate deliverable.
