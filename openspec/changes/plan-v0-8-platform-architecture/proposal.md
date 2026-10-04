# Proposal — Plan the v0.8 Project Intelligence Platform

## Why

This repository is the **implementation project** for the v0.8 Project
Intelligence Platform: the product source tree, container build, OCI
distribution, default configuration, sample plugin generation, default
launchers, control-plane UI assets, license policy, OpenSpec
governance and the durable Wiki for the platform are all authored
here. The container image(s) built from this repo are the runtime
product; they bind to an external target project and operate on that
project's dedicated data.

Today the repo contains only the harness scaffolding
(`harness.py`, `openspec/`, `.agents/`, `.ai/`, scripts, tooling). The
product described in
`project-intelligence-platform-architecture-v0.8.md` does not yet
exist as code in `platform/`, no container image is built, no OCI
artefacts are produced, and no `distribution/` plugin bundles exist.
The v0.8 architecture document is the agreed architectural baseline,
but no agreed behavioural specs, technical design, ordered
implementation tasks, or context-impact analysis exist for it.

Consequences of that gap:
- product capabilities cannot be designed coherently, so neither the
  Wiki nor OpenSpec can trace implementation back to normative
  contracts;
- ordering of work is undefined, so contributors and AI agents cannot
  reason about which subsystem to build first or which OCI artefact
  to publish next;
- the Wiki can only mirror the architecture document; the Wiki has
  no product modules, ADRs, interfaces or distribution artefacts to
  reference;
- OpenSpec has no product behavioural specs to validate against
  `harness.py openspec-check`;
- the container build pipeline, the OCI distribution tags, the
  default control-plane UI assets and the plugin generation
  pipelines cannot be planned.

This change resolves the gap by producing the OpenSpec change
artifacts (proposal, specs, design, context-impact, tasks) that
decompose the v0.8 architecture into a coherent, verifiable,
prioritized work plan. After this change is archived the repo has a
single, reviewable, machine-checkable entry point to implement the
platform phase by phase, with the Wiki and OpenSpec evolving
together as the implementation and OCI distribution proceeds.

## Goal

Adopt OpenSpec change artifacts for the v0.8 architecture that:

- split the 72 architecture sections into **ten bounded implementation
  phases** with clear ordering and dependencies;
- define the **Phase 1 foundation capabilities** as accepted
  behavioural specs so downstream changes can build on stable
  contracts;
- describe the **technical design** for the platform core, control
  plane, data plane, container build, OCI distribution, and Wiki
  evolution, following the architecture's
  hexagonal/ports-and-adapters + micro-kernel style;
- identify **Wiki/ADR/context-impact** work needed alongside
  implementation so the Wiki and OpenSpec evolve together as the
  product is built and shipped;
- enumerate a **fine-grained, dependency-ordered task list** that an
  agent or developer can execute top-to-bottom to implement the
  entire v0.8 architecture, build the container image(s), publish
  the OCI artefacts, and generate the plugin bundles.

Out of scope for this change:
- writing any platform source code, container build file, OCI
  artefact, plugin bundle, or any other runtime artefact;
- operating the platform against a target project (that is a
  runtime concern of the container bound to a target repo, not a
  concern of this implementation repo).

What this change does:
- proposes the five Phase 1 foundation capability specs that every
  later phase builds on;
- describes the overall architectural design and the Phase 1
  technical design;
- updates the durable Wiki so it becomes the central navigation for
  the implementation project as it grows;
- enumerates an ordered, dependency-respecting task list across all
  ten implementation phases so a contributor or AI agent can orient.

Adoption model (resolves F15):
- **this change IS archivable now** because all its acceptance
  criteria are planning artifacts (proposal, five specs, design,
  context-impact, tasks, Wiki/ADR updates) and those artifacts have
  been authored, validated by `openspec validate --changes` and are
  internally consistent;
- when this change is archived (via the standard OpenSpec archive
  workflow), the five Phase 1 spec deltas are promoted to accepted
  specs under `openspec/specs/2026-10-04-<capability>/`;
- the ordered task list is the implementation roadmap. **Tasks 1-12
  complete this change.** **Tasks 13-44** are the Phase 1
  implementation tasks assigned to the future
  `implement-phase-1-foundation` change. **Tasks 45-123** are the
  Phase 2-10 roadmap for the subsequent phase changes. None of
  tasks 13-123 are executed by this change;
- the future `implement-phase-1-foundation` change depends on the
  five accepted Phase 1 specs being present in `openspec/specs/`
  and implements exactly the Phase 1 tasks (13-44).

## Affected capabilities

### What changes

This change introduces the following additive product capability specs.
No existing capability (harness or product) is modified or retired by
this change.

- `openspec/changes/plan-v0-8-platform-architecture/specs/project-knowledge-repository-layout/spec.md`
  — additive; new capability; lands in
  `openspec/specs/2026-10-04-project-knowledge-repository-layout/` upon
  archive.
- `openspec/changes/plan-v0-8-platform-architecture/specs/canonical-knowledge-schema/spec.md`
  — additive; new capability; lands in
  `openspec/specs/2026-10-04-canonical-knowledge-schema/` upon archive.
- `openspec/changes/plan-v0-8-platform-architecture/specs/git-version-aware-runtime/spec.md`
  — additive; new capability; lands in
  `openspec/specs/2026-10-04-git-version-aware-runtime/` upon archive.
- `openspec/changes/plan-v0-8-platform-architecture/specs/bidirectional-canonical-runtime-sync/spec.md`
  — additive; new capability; lands in
  `openspec/specs/2026-10-04-bidirectional-canonical-runtime-sync/`
  upon archive.
- `openspec/changes/plan-v0-8-platform-architecture/specs/license-governance/spec.md`
  — additive; new capability; lands in
  `openspec/specs/2026-10-04-license-governance/` upon archive.

The five Phase 1 specs are PROPOSED while this change is in
`openspec/changes/`. They are NOT yet authoritative. They become
authoritative when this change is archived and OpenSpec promotes them into
`openspec/specs/2026-10-04-*/`.

The capability table below lists every Phase 2-10 capability that later
OpenSpec changes will introduce after the Phase 1 foundation is
adopted; they are listed for end-to-end review of the v0.8 architecture
but produce no spec files in this change.

This change proposes the **creation** of the following product capability
specs (proposed while this change is in `openspec/changes/`; first
acceptance date 2026-10-04 upon archive). Phase numbering matches
[`tasks.md`](../../changes/plan-v0-8-platform-architecture/tasks.md):

| New capability | Architecture sections | Phase |
|---|---|---|
| `project-knowledge-repository-layout` | §64, §6, §9 | 1 — Foundation |
| `canonical-knowledge-schema` | §7.1, §10, §21, §54, §10/OKF, §23 (metadata) | 1 — Foundation |
| `git-version-aware-runtime` | §5, §11, §12, §13 | 1 — Foundation |
| `bidirectional-canonical-runtime-sync` | §7.2, §8, §62, §63 | 1 — Foundation |
| `license-governance` | §4 | 1 — Foundation |
| `ingestion-pipeline-driver` | §18 | 2 — Ingestion |
| `structured-code-intelligence` | §14 | 2 — Ingestion |
| `jar-dependency-intelligence` | §15 | 2 — Ingestion |
| `document-source-adapters` | §3, §8.2 | 2 — Ingestion |
| `openspec-change-adapter` | §53 | 2 — Ingestion |
| `local-source-inbox` | §9 | 2 — Ingestion |
| `content-addressed-processing` | §13 | 2 — Ingestion |
| `semantic-structural-chunking` | §19, §20, §21 | 2 — Ingestion |
| `context-enrichment` | §22 | 2 — Ingestion |
| `runtime-storage-strategy` | §61 | 3 — Storage |
| `canonical-knowledge-graph` | §16, §17 | 3 — Storage |
| `knowledge-provenance-and-freshness` | §54, §55 | 3 — Storage |
| `hybrid-retrieval-engine` | §26, §27, §28 | 4 — Retrieval |
| `temporal-version-retrieval` | §24 | 4 — Retrieval |
| `multi-stage-retrieval` | §29, §30, §31 | 4 — Retrieval |
| `context-assembler` | §32 | 4 — Retrieval |
| `embedding-model-port` | §25 | 4 — Retrieval |
| `retrieval-first-policy` | §33 | 5 — Orchestration |
| `query-orchestrator` | §34 | 5 — Orchestration |
| `small-local-llm-port` | §35 | 5 — Orchestration |
| `task-context-bundles` | §52 | 5 — Orchestration |
| `capability-discovery` | §47 | 5 — Orchestration |
| `mcp-server-and-tools` | §36 | 6 — Agent integration |
| `versioned-agent-skill` | §37 | 6 — Agent integration |
| `skill-distribution-plane` | §38 | 6 — Agent integration |
| `protocol-version-compatibility` | §39 | 6 — Agent integration |
| `agent-integration-adapters` | §40–§44, §46 | 6 — Agent integration |
| `plugin-generation-pipeline` | §45 | 6 — Agent integration |
| `plugin-supply-chain-security` | §48 | 6 — Agent integration |
| `feature-plugin-registry` | §59 (registry) | 7 — Control plane |
| `hook-system` | §59 (hooks) | 7 — Control plane |
| `capability-based-permissions` | §59 (capabilities) | 7 — Control plane |
| `secret-provider` | §59 (secrets) | 7 — Control plane |
| `central-policy-engine` | §59 (policy) | 7 — Control plane |
| `audit-and-operational-logs` | §59 (audit) | 7 — Control plane |
| `feature-flags` | §59 (feature flags) | 7 — Control plane |
| `ui-plugin-extension` | §59 (UI extensions) | 7 — Control plane |
| `enterprise-security-boundary` | §56 | 8 — Security |
| `human-interface-web-ui` | §57 | 9 — Distribution |
| `one-click-distribution` | §58 | 9 — Distribution |
| `deployment-containerization` | §60 | 9 — Distribution |
| `okf-wiki-profile` | §10 (OKF, compat) | 9 — Distribution |
| `a2a-adapter` | §50 | 10 — A2A |
| `external-coding-agent-integration` | §51 | 10 — A2A |
| `integration-quality-gates` | §49 | 10 — Quality |

This change ships the **Phase 1 foundation capability specs only**
(those five rows with Phase 1 — Foundation). All other rows are listed in
the proposal so the implementation order is reviewable end-to-end; their
spec deltas will be authored by later OpenSpec changes that depend on the
foundation specs adopted here.

Two capabilities were renamed from earlier drafts for clarity:

- `knowledge-provenance-and-freshness` was previously listed under
  Phase 6 (Orchestration) but its implementation belongs to Phase 3
  (Storage) per `tasks.md` task 67. The implementation site (the
  runtime store and graph) is the canonical owner.
- `context-assembler` was previously listed under Phase 5
  (Orchestration) but its implementation belongs to Phase 4
  (Retrieval) per `tasks.md` task 76. It depends on the retrieval
  candidate set, so it ships with the retrieval engine.

`openspec/specs/` currently contains only the harness-framework accepted
capabilities (`2026-09-07-*`, `2026-10-03-*`, `2026-10-04-*`). This
change introduces the first product capabilities under the dated
folder convention.

No existing capability is **modified** or **retired** by this change.
No accepted harness capability is affected.

## Compatibility / migration impact

This change is a pure planning artifact: no source files, no runtime
configuration, no dependencies, no public contracts, and no API versions
are changed. The only filesystem impact is the creation of new files
under `openspec/changes/plan-v0-8-platform-architecture/` and a small set
of Wiki/ADR nodes under `.ai/wiki/`.

Compatibility constraints this plan respects:

- the `production-sdd` OpenSpec schema selected in `openspec/config.yaml`;
  this plan uses the same artifact sequence (`proposal → specs → design →
  context-impact → tasks`);
- lowercase kebab-case change ID without date prefix
  (`plan-v0-8-platform-architecture`);
- archive folder convention `archive/YYYY-MM-DD-original-change-name/`
  is preserved for the future archive step;
- the harness agent contract (`AGENTS.md`, `.ai/AGENTS.md`) is followed:
  Markdown is canonical, secrets stay out of the Wiki, generated indexes
  live under `tmp/local/`;
- the existing project Wiki structure (`.ai/wiki/architecture/`,
  `.ai/wiki/project/`, `.ai/wiki/glossary/`, `.ai/wiki/adr/`) is extended
  with new durable knowledge nodes rather than rewritten;
- the existing harness commands, skill routing, and OpenSpec layout
  validation scripts are untouched.

No migration steps are required for downstream consumers because no public
contract changes in this change.

## Related knowledge

- `kb://architecture.system-overview` — high-level boundaries; mirrors
  the v0.8 architecture; to be updated by this change.
- `kb://project.map` — repository navigation; to be updated by this
  change to reference the new capability set and the change artifact.
- `kb://project.task-handoff` — durable task-state lifecycle; informs
  the implementation order recorded in `tasks.md`.
- `kb://adr.skill-ownership-boundary` — boundary between harness core
  skills and integration-owned top-level skills; respected by the
  Phase 7 agent integration plan (skill packaging strategy).
- `kb://glossary.domain` — domain terminology; to be extended with the
  new platform vocabulary introduced by the v0.8 architecture.
- `kb://project.harness-framework-adoption` — adopted framework files;
  informs what stays harness-owned versus what becomes product code.
- `kb://project.harness-command-lifecycle` — `harness.py` command
  lifecycle; the platform product code must coexist with and may
  register additional subcommands under the same lifecycle.
- external: `project-intelligence-platform-architecture-v0.8.md` (the
  v0.8 baseline; this change cites every architectural section it
  introduces a capability for).