---
id: architecture.platform-overview
title: Platform Architecture Overview
kind: architecture
status: active
summary: High-level boundaries, runtime flows, control plane and data plane responsibilities of the v0.8 Project Intelligence Platform; describes the Phase 1 implementation and the boundary between this implementation project and the runtime data it operates on.
sourceRefs:
  - project-intelligence-platform-architecture-v0.8.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/proposal.md
  - openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md
  - openspec/changes/implement-phase-1-foundation/design.md
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
│   └── licensing/         # policy / gate / inventory / SBOM emitter
├── ports/                 # abstract port interfaces
├── adapters/
│   ├── fs/                # local filesystem adapter
│   └── git/               # git CLI adapter
├── runtime/               # content-addressed filesystem cache
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
`license-gate`, `okf-validate`, `version-identity`, `wal-recover`
and `health`. The Phase 1 implementation targets the
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
[`plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md).
Summary of phases:

| Phase | Name | Depends on | Status |
|---|---|---|---|
| 0 | Plan | — | complete |
| 1 | Foundation | Phase 0 | complete (this change) |
| 2 | Ingestion (parsers, content addressing) | Phase 1 | planned |
| 3 | Storage (runtime DB, sharded graph) | Phase 2 | planned |
| 4 | Retrieval (hybrid, multi-stage, reranking) | Phase 3 | planned |
| 5 | Orchestration (query, local LLM, task context) | Phase 4 | planned |
| 6 | Agent integration (MCP, skill, adapters) | Phase 5 | planned |
| 7 | Control plane (registry, hooks, capabilities, secrets) | Phase 6 | planned |
| 8 | Security (enterprise boundary) | Phase 7 | planned |
| 9 | Distribution (UI, container, OCI, one-click) | Phase 8 | planned |
| 10 | A2A and final quality gates | Phase 9 | planned |

## Evidence

- [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  — v0.8 baseline.
- [`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/proposal.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/proposal.md)
  — planning proposal.
- [`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md)
  — planning technical design.
- [`openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md`](../../../openspec/changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md)
  — ordered implementation tasks.
- [`openspec/changes/implement-phase-1-foundation/design.md`](../../../openspec/changes/archive/2026-10-04-implement-phase-1-foundation/design.md)
  — Phase 1 implementation design.
- [`tests/test_platform_phase1.py`](../../../tests/test_platform_phase1.py)
  — Phase 1 regression suite.
- [`.ai/AGENTS.md`](../../../.ai/AGENTS.md) and
  [`AGENTS.md`](../../../AGENTS.md) — agent contracts.
- [`openspec/CURRENT.md`](../../../openspec/CURRENT.md) — accepted
  capabilities inventory.