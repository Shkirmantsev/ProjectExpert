---
id: architecture.platform-overview
title: Platform Architecture Overview
kind: architecture
status: draft
summary: High-level boundaries, runtime flows, control plane and data plane responsibilities of the planned v0.8 Project Intelligence Platform; also describes the boundary between this implementation project and the runtime data it operates on.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/proposal.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md
maintenance:
  mode: authored
---

# Platform Architecture Overview

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
is the agreed target. This page mirrors only the boundaries that
downstream agents must respect while the platform is implemented
phase by phase per the
[`plan-v0-8-platform-architecture`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/)
OpenSpec change.

## What this repository is

This repository is the **implementation project** for the v0.8
Project Intelligence Platform. It contains:

- the platform source tree under `platform/`;
- the container build files (`Containerfile`, `docker-compose.yml`,
  launcher scripts) and the OCI distribution artefacts;
- the default control-plane UI assets, the plugin generation
  pipelines and the canonical Agent Skill;
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
authorization decisions.

## Module map

The product source tree is **planned** for the implementation
phases defined in
[`plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md):

```text
platform/
├── core/                # domain entities, value types, policies
├── ports/               # port interfaces (no implementation)
├── adapters/            # adapter implementations
├── runtime/             # runtime working knowledge cache
├── control/             # control-plane scaffolding
├── data/                # data-plane scaffolding
├── ingest/              # ingestion adapters (Phase 2)
├── retrieval/           # retrieval engine (Phase 4)
├── embeddings/          # embedding model port (Phase 4)
├── context/             # context assembler (Phase 4)
├── orchestrator/        # query orchestrator (Phase 5)
├── llm/                 # local LLM port (Phase 5)
├── task/                # task context builder (Phase 5)
├── mcp/                 # MCP server (Phase 6)
├── security/            # enterprise boundary (Phase 8)
├── ui/                  # REST API for UI (Phase 9)
└── a2a/                 # A2A adapter (Phase 10)
project-knowledge/       # canonical knowledge tree (Phase 1)
.project-intelligence-cache/  # runtime cache, gitignored (Phase 1)
distribution/
├── licenses/            # dependency inventory, SBOM, NOTICE (Phase 1)
├── skills/              # canonical Agent Skill (Phase 6)
├── codex/               # Codex/ChatGPT plugin bundle (Phase 6)
├── claude-code/         # Claude Code plugin bundle (Phase 6)
├── opencode/            # OpenCode plugin package (Phase 6)
├── generic-agent/       # generic agent bundle (Phase 6)
└── sbom/                # generated SBOM artefacts (Phase 1)
```

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

## Phase 1 foundation capabilities

The following capabilities are PROPOSED in the current OpenSpec
change; they become accepted upon archive and land in
`openspec/specs/2026-10-04-*/`. They are the contracts that every
later phase builds on:

- `2026-10-04-project-knowledge-repository-layout` — canonical
  on-disk layout (`project-knowledge/`, `.project-intelligence-cache/`,
  `tmp/local/source/`, `distribution/`), `project-context.yaml`
  contract, `.gitignore` contract.
- `2026-10-04-canonical-knowledge-schema` — deterministic canonical
  serialization, SHA-256 content addressing, sharded canonical
  storage, manifest-driven hydration, chunk model and hierarchy,
  knowledge provenance state model, OKF v0.2 Wiki profile, isolated
  `OkfAdapter`, forward compatibility with future OKF revisions.
- `2026-10-04-git-version-aware-runtime` — runtime project version
  identity tuple, Git-state transitions, working-tree overlay,
  cross-branch content reuse, Git LFS strategy.
- `2026-10-04-bidirectional-canonical-runtime-sync` — hydrate,
  enrich, materialise, round-trip preservation, incremental
  branch-switch reconciliation, stale-knowledge detection.
- `2026-10-04-license-governance` — dependency inventory, SPDX
  tracking, allow/review/deny policy, model-license separate
  tracking, SBOM/NOTICE, CI gate, dynamic plugin/hook verification.

## Implementation phases (summary)

The full ordered task list is in
[`tasks.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md).
Summary of phases:

| Phase | Name | Depends on |
|---|---|---|
| 0 | Plan (this change) | — |
| 1 | Foundation | Phase 0 (this change archived) |
| 2 | Ingestion (parsers, content addressing) | Phase 1 |
| 3 | Storage (runtime DB, sharded graph) | Phase 2 |
| 4 | Retrieval (hybrid, multi-stage, reranking) | Phase 3 |
| 5 | Orchestration (query, local LLM, task context) | Phase 4 |
| 6 | Agent integration (MCP, skill, adapters) | Phase 5 |
| 7 | Control plane (registry, hooks, capabilities, secrets) | Phase 6 |
| 8 | Security (enterprise boundary) | Phase 7 |
| 9 | Distribution (UI, container, OCI, one-click) | Phase 8 |
| 10 | A2A and final quality gates | Phase 9 |

## Evidence

- [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  — v0.8 baseline.
- [`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/proposal.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/proposal.md)
  — proposal.
- [`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md)
  — technical design.
- [`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md)
  — ordered implementation tasks.
- [`.ai/AGENTS.md`](../../../.ai/AGENTS.md) and
  [`AGENTS.md`](../../../AGENTS.md) — agent contracts.
- [`openspec/CURRENT.md`](../../../openspec/CURRENT.md) — accepted
  capabilities inventory.