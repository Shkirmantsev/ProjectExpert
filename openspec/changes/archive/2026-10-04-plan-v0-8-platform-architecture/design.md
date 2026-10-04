# Design — plan-v0-8-platform-architecture

## Current state

The repository currently contains:

- the development harness framework (`harness.py`, `Makefile`,
  `scripts/`, `.agents/skills/`, `openspec/`, `.ai/`, `tools/mcp/`,
  `.opencode/`, `.claude/`, `.codex/`);
- the v0.8 architecture baseline document at the repository root
  (`project-intelligence-platform-architecture-v0.8.md`);
- accepted harness capabilities (`openspec/specs/2026-09-07-*`,
  `openspec/specs/2026-10-03-*`, `openspec/specs/2026-10-04-*`);
- existing durable Wiki nodes (`architecture/system-overview`,
  `project/project-map`, `project/harness-framework-adoption`,
  `project/harness-command-lifecycle`, `project/task-handoff`,
  `glossary/domain`, `adr/0001-separate-core-and-integration-skill-
  ownership`).

The repository does not yet contain any product code, any product
specs, any product ADRs, any product Wiki, any runtime container,
any MCP server, any retrieval engine, any control plane, any plugin
registry, any agent integration package, or any distribution
artifact.

The architecture document is the only source of product intent.

## Proposed design

This design covers two scopes:

1. the overall platform architecture (target end-state), used to
   align subsequent OpenSpec changes with the same vocabulary,
   module boundaries and dependency rules;
2. the Phase 1 foundation implementation that the first code-
   producing OpenSpec change will execute against, derived from the
   five Phase 1 specs introduced by this change.

The design is described as module boundaries, runtime flows, data
contracts, technology choices and rules rather than as finished code.

### Architectural style

The platform adopts the architectural style mandated by §59:

- **Hexagonal / Ports-and-Adapters core.** Business logic depends on
  ports; adapters implement ports for specific technologies (a
  vector-store adapter, a graph-store adapter, an embedding-model
  adapter, an MCP transport adapter, a Web framework adapter).
- **Micro-kernel / Plugin extension surface.** Optional capabilities
  are registered through stable extension APIs
  (`Plugin`, `FeatureProvider`, `HookProvider`, `SourceProvider`,
  `SecretProvider`, `PolicyProvider`, `AgentAdapter`, `UiExtension`,
  `ObservabilityProvider`, `Exporter`) and never coupled to the core
  domain.
- **Single modular deployable.** The default deployable is one
  process. The default distribution is one container (or one
  container plus an optional UI/runtime sidecar).

Vendor-specific configuration is excluded from the domain core. The
core remains agent-neutral, model-neutral, storage-neutral at the
architectural level, and UI-neutral.

### Control plane and data plane

The platform separates:

- **Control plane** — UI/CLI/automation for configuration, policies,
  permissions, plugin/feature lifecycle, hooks, secret references,
  environment mappings, diagnostics, audit, health and administration.
- **Data plane** — ingestion, indexing, retrieval, graph operations,
  context assembly, MCP tool execution, A2A requests and runtime
  agent work.

The control plane configures and observes the data plane but must
not bypass the same authorization rules that apply to agents and
plugins. Both planes call into the same central Policy Engine for
authorization decisions.

### Modules and packages

The Phase 1 foundation defines the following top-level product
modules. The path layout mirrors §64.

```text
platform/
├── core/                  # domain entities, value types, policies
│   ├── canonical/         # canonical-knowledge-schema
│   ├── git/               # git-version-aware-runtime
│   ├── sync/              # bidirectional-canonical-runtime-sync
│   └── licensing/         # license-governance
├── ports/                 # port interfaces (no implementation)
├── adapters/              # adapter implementations
│   ├── git/               # libgit2 / git CLI adapter
│   ├── fs/                # filesystem adapter for canonical tree
│   └── packaging/         # JSON / YAML / SHA-256 adapters
├── runtime/               # in-process runtime working knowledge cache
├── control/               # control-plane scaffolding (later phase)
├── data/                  # data-plane scaffolding (later phase)
└── schemas/               # generated schema artifacts
project-knowledge/         # canonical knowledge tree (see spec)
.project-intelligence-cache/  # runtime cache (see spec)
distribution/
└── licenses/              # generated dependency inventory and SBOM
```

### Phase 1 foundation design

The Phase 1 specs (this change) introduce the following contracts
that the first code-producing change must implement. The design
below describes the intended technical approach for that change; it
is not implemented here.

#### Module: `platform/core/canonical`

Implements the `canonical-knowledge-schema` spec. Responsibilities:

- define value types for `Source`, `Document`, `Section`, `Chunk`,
  `ContextualChunk`, `Entity`, `Relation`, `Evidence`,
  `KnowledgeState`, `ProjectVersion`, `Shard`, `Manifest`,
  `RuntimeChange`, `TaskContext`;
- provide deterministic JSON/YAML serializers (sorted, normalised
  line endings, trailing newline);
- provide a SHA-256 content-addressing utility used by both the
  canonical layer and the runtime cache;
- implement the `OkfAdapter` interface and a v0.2 profile that
  declares the `okf_version` frontmatter key and the `pi_` extension
  prefix;
- implement an OKF conformance validator used as a pre-commit
  validation step;
- provide a manifest writer/reader per knowledge family
  (graph, sources, chunks, objects).

The module exposes ports for storage adapters rather than reading
the filesystem directly. The first implementation uses a filesystem
adapter and a content-addressed object store backed by the
canonical `objects/` tree.

#### Module: `platform/core/git`

Implements the `git-version-aware-runtime` spec. Responsibilities:

- resolve HEAD, branch, tag, worktree and working-tree fingerprint
  via the Git adapter;
- compute the structured project version identity tuple;
- detect Git-state transitions and emit reconcile events;
- integrate with the Git LFS pointer mechanism for binary source
  artifacts;
- reuse content-hash derived cache entries across branches.

The Git adapter interface lives in `platform/adapters/git/` and
defaults to a CLI-based Git adapter that uses the system `git`
binary. The adapter has a documented minimal Git version contract
(≥ the version available in the project's base container image).

#### Module: `platform/core/sync`

Implements the `bidirectional-canonical-runtime-sync` spec.
Responsibilities in Phase 1:

- drive the hydrate / reconcile / materialise lifecycle over the
  canonical layer only; the runtime store, the graph index, the
  sparse index, the dense index and the embedding cache are added
  in Phases 3-4, so Phase 1 hydrate operates on manifests and
  normalised shard bodies, then leaves the runtime cache cold for
  the later phases;
- expose `RestoreRuntime(projectVersion)` that loads manifests,
  restores the Phase 1 runtime cache, and applies the working-tree
  overlay;
- expose `MaterialiseDurableChanges()` that normalises, serialises,
  re-shards, updates manifests, regenerates affected Wiki concept
  Markdown, validates provenance and license policy, and emits a
  Git diff for operator approval;
- expose a `ReconcileBranchSwitch()` that performs incremental
  reconciliation rather than full rebuild;
- detect and surface stale durable knowledge via the runtime store
  and, when Phase 6 ships it, via the MCP `project.get_conflicts`
  tool.

The approval gate is delegated to a Phase 1 stub `PolicyDecisionPort`
that returns `ALLOW / DENY / REQUIRE_APPROVAL`; the full central
Policy Engine arrives in Phase 7 (task 98). The sync module does not
own approval policy.

#### Module: `platform/core/licensing`

Implements the `license-governance` spec. Responsibilities:

- maintain the SPDX-aware dependency inventory;
- implement the policy evaluator
  (`allow` ∪ `review` with explicit acceptance token) and produce
  build-blocking decisions;
- separately track model licenses (`distribution/licenses/model-
  licenses.json`) and bundled library licenses
  (`distribution/licenses/dependency-inventory.json`);
- emit SBOM and NOTICE artefacts at the documented paths;
- expose a port for license-checking plugins, hooks, UI extensions
  and agent adapters before activation.

### Data ownership and flow

#### Canonical layer (durable)

Owned by `platform/core/canonical`. The canonical layer is the
source of truth; only the materialise operation may write into it
and only after operator approval.

#### Runtime cache (transient)

Owned by `platform/runtime/`. Lives under
`.project-intelligence-cache/` per `project-knowledge-repository-
layout` spec. Cache entries are content-addressed by SHA-256; an
entry's key is the SHA-256 of the canonical input it derives from.
The runtime store never grows into the canonical tree.

#### Working-tree overlay (transient)

Owned by `platform/core/git` and `platform/core/sync`. The overlay
is computed from the Git status of the target project; it is applied
to the effective runtime context but is never written to the
canonical tree automatically.

#### Configuration scopes

Per §59 the configuration is split into:

- Git-versioned project configuration (`project-knowledge/project-
  context.yaml`, `platform/policies/*.yaml`, `platform/hooks/*.
  yaml`, `platform/plugins/*.yaml`);
- local machine configuration (`.project-intelligence-cache/
  machine.json` inside the runtime cache, plus
  `~/.config/project-intelligence/` per-user; documents local
  ports, model cache paths, Docker/Podman choice, local UI
  preferences). The product MUST NOT own, edit, or import
  harness-owned `.harness/runtime.json`; the product tree and the
  harness tree are independent.
- secret configuration (resolved through `SecretProvider` ports);
- runtime / session configuration (active overlays, active agent
  session).

### Concurrency and consistency

- Hydrate and materialise are serialised per target project. The
  platform MUST refuse concurrent hydrate or materialise calls for
  the same project and return a clear error.
- Incremental reconcile after a branch switch is allowed to run in
  parallel with read-only retrieval operations; the runtime store
  presents a consistent snapshot to retrieval through a version
  stamp.
- The runtime working knowledge store uses a write-ahead log so an
  interrupted materialise does not corrupt the canonical tree; the
  store is rolled back to the last approved materialisation on
  startup if no in-progress materialisation is found.
- Locking uses a per-project advisory file lock
  (`tmp/local/project-locks/<project-id>.lock`) that is
  **behaviour-compatible** with `scripts/file_lock.py` shipped by
  the harness. The product does NOT import the harness script;
  it implements its own lock with the same advisory semantics so
  both can coexist if a target developer chooses to enable both.

### Failure modes and recovery

- Interrupting a hydrate: the runtime store remains in the previous
  consistent state; the next startup resumes hydrate from the last
  committed manifest state.
- Interrupting a materialise: the canonical tree remains untouched;
  the runtime store records the in-progress change so the operator
  can retry or discard.
- Git LFS unavailability: sources behind LFS pointers are recorded
  by OID but not embedded; retrieval reports `unknown` provenance
  for the affected facts.

### Interfaces introduced in Phase 1 (placeholder names; final names
during implementation)

```text
platform.core.canonical.ChunkPort
platform.core.canonical.EntityPort
platform.core.canonical.RelationPort
platform.core.canonical.ManifestPort
platform.core.canonical.OkfAdapter
platform.core.canonical.OkfValidator

platform.core.git.GitPort
platform.core.git.VersionIdentityPort
platform.core.git.WorkingTreeOverlayPort

platform.core.sync.HydratePort
platform.core.sync.ReconcilePort
platform.core.sync.MaterialisePort

platform.core.licensing.LicensePolicy
platform.core.licensing.LicenseGate
platform.core.licensing.DependencyInventoryPort
```

### Cross-cutting decisions

- Every product module MUST expose ports; adapters live in
  `platform/adapters/` and never in `platform/core/`.
- The control plane and data plane will be split in later phases
  per §59; Phase 1 introduces only the boundaries and the ports.
- All configuration that is durable knowledge lives under
  `project-knowledge/`; that canonical tree is Git-versioned
  (invariant #1, §7.1). The runtime cache under
  `.project-intelligence-cache/` and the dynamic inbox under
  `tmp/local/source/` are excluded from the Git tree by default
  per `project-knowledge-repository-layout` spec.

## Errata against the v0.8 architecture baseline

While reading the baseline end-to-end, two internal contradictions
were found. Per the project contract (`.ai/AGENTS.md`: "When these
disagree, report the mismatch explicitly. Never silently rewrite one
source to hide disagreement."), both are recorded here so the
implementation work and the future baseline revision can resolve
them deliberately rather than implicitly.

1. **`project-context.yaml` location** — §64 (Suggested Repository
   Layout, lines 3310-3354) shows `project-context.yaml` at the
   project root; §7.1 (lines 286-298) shows `project-context.yaml`
   inside `project-knowledge/`. The Phase 1 spec and this design
   follow §7.1 because canonical knowledge is git-versioned
   (`project-knowledge/`) and `project-context.yaml` is canonical
   configuration. The future baseline revision SHOULD consolidate
   on the §7.1 location.
2. **`platform/` subpackage mix** — §64 lists
   `platform/{plugins,hooks,policies,schemas}` as the repository-
   level extension surface; §59 lists the runtime extension API
   types (`Plugin`, `FeatureProvider`, etc.) but does not pin
   their filesystem path. This design uses §64's
   `platform/{plugins,hooks,policies,schemas}` for the
   repository-level layout and §59's API types for the runtime
   surface. The future baseline revision SHOULD explicitly cross-
   reference both.

## Affected modules / interfaces

| Module / path | Affect |
|---|---|
| `openspec/changes/plan-v0-8-platform-architecture/` | new (this change) |
| `openspec/specs/2026-10-04-*` (five new capabilities) | new (after adoption) |
| `openspec/CURRENT.md` | updated to list the five new accepted capabilities |
| `.ai/wiki/architecture/system-overview.md` | updated to reference the five new capabilities |
| `.ai/wiki/project/project-map.md` | updated to add the product module map |
| `.ai/wiki/glossary/domain.md` | updated with platform vocabulary |
| `.ai/wiki/adr/0002-...md` | new ADR for the canonical/runtime separation |
| `project-knowledge/`, `.project-intelligence-cache/` | directories introduced in the first code-producing change |
| `distribution/licenses/` | produced by the first code-producing change |

## Data / persistence / concurrency impact

- Canonical knowledge lives in `project-knowledge/` in sharded
  JSON/YAML/Markdown files; large files are split, never committed
  monolithically.
- Runtime cache lives in `.project-intelligence-cache/` (gitignored)
  using an embedded relational+vector+graph engine chosen in Phase 4.
- Concurrency is serialised per project via `file_lock.py`-style
  advisory locks.
- No database migration is required for this change because no
  runtime data exists yet.

## Compatibility and migration

This change introduces only new files. No existing source, schema,
API, or contract is modified.

- No public harness contract changes.
- No OpenSpec schema change (the production-sdd schema is reused).
- No CLI command changes (the first code-producing change will add
  new commands; this change does not).
- No backward-compatibility flag needed because no consumer exists
  yet.

## Risks and rollback

Risks:

- choosing the wrong Phase 1 module boundaries could lock in
  awkward seams later; mitigated by keeping the Phase 1 surface
  small (canonical model + git/sync + licensing) and by exposing
  ports, not concrete classes, so that any seam can be moved with
  adapter-only churn.
- underestimating the size of the deterministic serialization
  work; mitigated by isolating it in `platform/core/canonical` and
  adding a property-based round-trip test.

Rollback:

- this change reverts cleanly by deleting
  `openspec/changes/plan-v0-8-platform-architecture/` and reverting
  the Wiki edits (the Wiki edits are additive; reverting them
  restores the previous state).
- before the first code-producing change is adopted, there is no
runtime artifact to roll back.