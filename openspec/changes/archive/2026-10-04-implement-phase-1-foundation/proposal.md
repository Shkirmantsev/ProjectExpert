# Proposal — Implement Phase 1 Foundation of the v0.8 Project Intelligence Platform

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
is now an agreed architectural contract, and the planning change
[`plan-v0-8-platform-architecture`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/)
has been archived, promoting the five Phase 1 foundation specs into
`openspec/specs/2026-10-04-*`:

- [`project-knowledge-repository-layout`](../../specs/2026-10-04-project-knowledge-repository-layout/spec.md)
- [`canonical-knowledge-schema`](../../specs/2026-10-04-canonical-knowledge-schema/spec.md)
- [`git-version-aware-runtime`](../../specs/2026-10-04-git-version-aware-runtime/spec.md)
- [`bidirectional-canonical-runtime-sync`](../../specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md)
- [`license-governance`](../../specs/2026-10-04-license-governance/spec.md)

No product code, no container image, no distribution artifact and no
`platform/` source tree exist yet. The repository contains only the
harness scaffolding, the Wiki planning nodes, and the OpenSpec
artifacts. Without product code there is nothing for agents to query,
no hydration contract for the runtime store, no materialisation gate,
no license gate and no deterministic canonical serialization to back
the durability invariant. The Wiki explains what will be built but
not what is built.

This change resolves that gap by **implementing exactly the Phase 1
foundation tasks (13-44)** recorded in the
[`plan-v0-8-platform-architecture/tasks.md`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md)
file. After this change is archived, the repository will:

- expose a runnable `platform/` Python package implementing the five
  Phase 1 capability contracts;
- ship the documented directory layout (`project-knowledge/`,
  `.project-intelligence-cache/`, `distribution/`,
  `distribution/licenses/`, `distribution/sbom/`, `distribution/skills/`,
  `distribution/codex/`, `distribution/claude-code/`,
  `distribution/opencode/`, `distribution/generic-agent/`);
- provide a `Containerfile` skeleton and `docker-compose.yml` with
  the documented profiles;
- provide launcher skeletons for Linux and Windows;
- update the durable Wiki to reflect the implemented foundation.

No graph index, sparse/dense vector index, embedding model, MCP
server, A2A adapter or control plane ships in this change — those
land in Phases 3-10 per the
[`plan-v0-8-platform-architecture/tasks.md`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md)
roadmap.

## Goal

Implement the Phase 1 foundation per the five accepted specs, per
`plan-v0-8-platform-architecture/tasks.md` tasks 13-44, so the
repository has:

- a runnable `platform/` package with deterministic canonical
  serialization, SHA-256 content addressing, manifest-driven
  hydration, Git CLI adapter, version-identity tuple, working-tree
  overlay, hydrate/reconcile/materialise ports, approval-gated
  materialisation, per-project advisory file lock, write-ahead log
  for crash-safe materialisation, license policy/gate/inventory,
  model-license separate tracker and CI license gate stub;
- regression tests covering every Phase 1 scenario that does not
  require Phase 2+ machinery, plus a property-based canonical
  round-trip test and an end-to-end sync round-trip test;
- Wiki updates reflecting the implemented foundation;
- a passing `python harness.py check` and
  `openspec validate implement-phase-1-foundation --type change`.

## Affected capabilities

This change **modifies** the five accepted Phase 1 specs through
additive delta files that capture the concrete platform value types,
ports and adapters introduced by this change:

| Existing capability | Delta folder |
|---|---|
| `2026-10-04-project-knowledge-repository-layout` | [`specs/2026-10-04-project-knowledge-repository-layout/spec.md`](specs/2026-10-04-project-knowledge-repository-layout/spec.md) |
| `2026-10-04-canonical-knowledge-schema` | [`specs/2026-10-04-canonical-knowledge-schema/spec.md`](specs/2026-10-04-canonical-knowledge-schema/spec.md) |
| `2026-10-04-git-version-aware-runtime` | [`specs/2026-10-04-git-version-aware-runtime/spec.md`](specs/2026-10-04-git-version-aware-runtime/spec.md) |
| `2026-10-04-bidirectional-canonical-runtime-sync` | [`specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md`](specs/2026-10-04-bidirectional-canonical-runtime-sync/spec.md) |
| `2026-10-04-license-governance` | [`specs/2026-10-04-license-governance/spec.md`](specs/2026-10-04-license-governance/spec.md) |

All five deltas are **ADDED Requirements** modules that:

- pin concrete observable behaviour for the implemented value types,
  ports and adapters (e.g. `Source`, `Document`, `Section`, `Chunk`,
  `ContextualChunk`, `Entity`, `Relation`, `Evidence`,
  `KnowledgeState`, `ProjectVersion`, `Shard`, `Manifest`,
  `RuntimeChange`, `TaskContext`, `Metadata` in
  `canonical-knowledge-schema`);
- bind concrete module paths (`pi_platform.core.canonical.*`,
  `pi_platform.core.git.*`, `pi_platform.core.sync.*`,
  `pi_platform.core.licensing.*`) to the spec scenarios;
- document the implementation evidence (test classes, regression
  coverage) that the change verifies.

No existing capability is **retired**. No harness capability
(`2026-09-07-*`, `2026-10-03-*`) is modified. No Phase 2-10 capability
(ingestion, storage, retrieval, orchestration, MCP, control plane,
security, distribution, A2A) is affected; those capabilities are added
by their own later OpenSpec changes per the
[`plan-v0-8-platform-architecture/proposal.md`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/proposal.md).

## Compatibility / migration impact

- This change does **not** alter any existing harness or product
  contract. No CLI command, no JSON Schema, no OpenSpec schema, no
  agent skill and no existing Python module changes behaviour.
- It does **add** a new CLI harness target,
  `python -m pi_platform.cli <subcommand>`, that exposes the Phase 1
  foundation capabilities (`hydrate`, `materialise`, `license-gate`,
  `okf-validate`, `version-identity`, `init-project`). The new
  target is additive; existing harness commands continue to work.
- The platform's directory contract is **additive**: new directories
  (`platform/`, `project-knowledge/`, `.project-intelligence-cache/`,
  `distribution/`) are scaffolded by this change; no existing file
  is moved or rewritten.
- The platform CLI is implemented in Python (chosen by
  [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)).
  The licence policy in [`license-governance`](../../specs/2026-10-04-license-governance/spec.md)
  is honoured by selecting a permissive Apache-2.0/MIT-friendly
  Python 3.11 baseline and by stubbing the CI license gate so a
  future Phase 2 dependency cannot enter the dependency stack
  without a known SPDX identifier.
- The Phase 1 implementation deliberately defers the embedded
  runtime store, the graph index, the sparse index, the dense index,
  the embedding cache and the MCP server to Phases 3-5/6. The
  hydrate port operates over the canonical layer only; the
  `hydrateReport` accurately reports which families have not yet
  shipped rather than silently leaving them absent.

## Related knowledge

- `kb://architecture.platform-overview` — phase-1-aware mirror of
  the platform boundaries; updated to reflect the implemented
  foundation.
- `kb://project.project-map` — repository navigation; updated to
  list the new `platform/`, `project-knowledge/`,
  `.project-intelligence-cache/`, `distribution/` directories.
- `kb://project.implementation-roadmap` — ordered phase roadmap;
  Phase 1 tasks are now resolved by this change.
- `kb://glossary.platform` — platform glossary; aligned with the
  implemented Phase 1 vocabulary.
- `kb://adr.canonical-runtime-separation` — accepted by this
  change (was proposed by the archived planning change).
- `kb://adr.license-governance-default` — accepted by this change.
- `kb://adr.ports-and-adapters-extension-style` — accepted by this
  change.
- `kb://adr.platform-source-language` — new ADR created by this
  change documenting the choice of Python 3.11 as the platform
  source language.
- external:
  [`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md)
  (v0.8 baseline).