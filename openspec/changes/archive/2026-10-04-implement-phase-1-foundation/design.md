# Design — implement-phase-1-foundation

## Current state

The repository contains:

- the harness framework (`harness.py`, `scripts/`, `openspec/`,
  `.agents/`, `.ai/`, `tools/mcp/`);
- the v0.8 architecture baseline document at the repository root
  ([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md));
- accepted harness capabilities (`openspec/specs/2026-09-07-*`,
  `2026-10-03-*`, `2026-10-04-harness-command-lifecycle`);
- five accepted Phase 1 product capabilities (`2026-10-04-*`).
- the durable Wiki nodes produced by the planning change
  (`architecture/system-overview`, `architecture/platform-overview`,
  `glossary/domain`, `glossary/platform`, `project/project-map`,
  `project/implementation-roadmap`, `adr/0001-...`,
  `adr/0002-...`, `adr/0003-...`, `adr/0004-...`).

The repository does **not** contain any platform Python package, any
container image, any launcher script or any
`distribution/licenses/` artifact.

## Proposed design

The design of this change is governed by the archived
[`plan-v0-8-platform-architecture/design.md`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md).
The additions in this change are concrete implementation choices
that did not need to be made at planning time.

### Language and runtime

The platform is implemented in **Python 3.11** as the platform source
language. Rationale is recorded in
[`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md).
Python is selected over Java for Phase 1 because:

- the v0.8 architecture does not require Java-specific runtime
  semantics for the foundation modules (canonical serialization,
  Git CLI, content addressing, license gating);
- the harness framework and the existing tests are already Python;
- the same Python code can drive the JSON/YAML canonical files,
  the `git` CLI adapter, the licensing gate and the eventual
  ingestion / retrieval adapters without crossing language
  boundaries;
- the Open Knowledge Format, deterministic serialization and
  SHA-256 addressing are language-agnostic and trivial in Python;
- Apache-2.0/MIT Python tooling is widely available, fully
  commercially usable and runs on CPU;
- a Java back-end can be introduced later as an adapter behind a
  stable port if a workload (e.g. Java source intelligence, JAR
  intelligence) requires it; Phase 1 stays language-neutral.

### Module layout

The Phase 1 module layout mirrors
[`plan-v0-8-platform-architecture/design.md`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/design.md).
Python subpackages created by this change:

```text
platform/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── canonical/        # canonical-knowledge-schema
│   │   ├── __init__.py
│   │   ├── value_types.py
│   │   ├── content_address.py
│   │   ├── serializer.py
│   │   ├── manifest.py
│   │   ├── okf.py
│   │   └── validator.py
│   ├── git/              # git-version-aware-runtime
│   │   ├── __init__.py
│   │   ├── git_port.py
│   │   ├── version_identity.py
│   │   └── working_tree_overlay.py
│   ├── sync/             # bidirectional-canonical-runtime-sync
│   │   ├── __init__.py
│   │   ├── hydrate.py
│   │   ├── reconcile.py
│   │   ├── materialise.py
│   │   ├── policy_stub.py
│   │   ├── project_lock.py
│   │   └── wal.py
│   └── licensing/        # license-governance
│       ├── __init__.py
│       ├── policy.py
│       ├── gate.py
│       ├── inventory.py
│       └── sbom.py
├── ports/                # port interfaces only, no implementation
│   ├── __init__.py
│   ├── canonical.py
│   ├── git.py
│   ├── sync.py
│   └── licensing.py
├── adapters/
│   ├── __init__.py
│   ├── fs/               # filesystem adapter for canonical tree
│   │   ├── __init__.py
│   │   └── fs_adapter.py
│   └── git/              # CLI git adapter
│       ├── __init__.py
│       └── cli_adapter.py
├── runtime/              # phase-1 stub; phase-3 adds the real store
│   ├── __init__.py
│   └── cache.py
└── cli/                  # command-line entry point
    ├── __init__.py
    └── main.py
```

Subpackages planned for later phases (`ingest/`, `retrieval/`,
`embeddings/`, `context/`, `orchestrator/`, `llm/`, `task/`,
`mcp/`, `security/`, `ui/`, `a2a/`) are **not** created in Phase 1;
creating empty subpackages would violate the project convention
([`docs/conventions/implementation.md`](../../../docs/conventions/implementation.md)
"avoid introducing infrastructure or abstractions without a concrete
problem they solve").

### Concrete value-type and port inventory

The Phase 1 implementation ships the following concrete types,
matching the spec sections:

- `pi_platform.core.canonical.value_types.Source`
- `pi_platform.core.canonical.value_types.Document`
- `pi_platform.core.canonical.value_types.Section`
- `pi_platform.core.canonical.value_types.Chunk`
- `pi_platform.core.canonical.value_types.ContextualChunk`
- `pi_platform.core.canonical.value_types.Entity`
- `pi_platform.core.canonical.value_types.Relation`
- `pi_platform.core.canonical.value_types.Evidence`
- `pi_platform.core.canonical.value_types.KnowledgeState`
- `pi_platform.core.canonical.value_types.ProjectVersion`
- `pi_platform.core.canonical.value_types.Shard`
- `pi_platform.core.canonical.value_types.Manifest`
- `pi_platform.core.canonical.value_types.RuntimeChange`
- `pi_platform.core.canonical.value_types.TaskContext`
- `pi_platform.core.canonical.value_types.Metadata`
- `pi_platform.core.canonical.content_address.content_address` and
  `content_address_for_canonical` helpers
- `pi_platform.core.canonical.serializer.canonical_dump_json`,
  `canonical_dump_yaml`, `canonical_load_json`,
  `canonical_load_yaml`
- `pi_platform.core.canonical.manifest.{load,save}_{source,graph,object,chunk}_manifest`
- `pi_platform.core.canonical.okf.OkfAdapter`, `OkfV02Profile`,
  `OkfValidationError`, `validate_wiki_bundle`
- `pi_platform.core.git.git_port.GitCliAdapter` (the default adapter)
- `pi_platform.core.git.version_identity.compute_version_identity`
- `pi_platform.core.git.working_tree_overlay.compute_working_tree_overlay`
- `pi_platform.core.sync.hydrate.HydrateService`
- `pi_platform.core.sync.reconcile.ReconcileService`
- `pi_platform.core.sync.materialise.MaterialiseService`
- `pi_platform.core.sync.policy_stub.PolicyDecisionStub`
- `pi_platform.core.sync.project_lock.ProjectLock`
- `pi_platform.core.sync.wal.WriteAheadLog`
- `pi_platform.core.licensing.policy.LicensePolicy`
- `pi_platform.core.licensing.gate.LicenseGate`
- `pi_platform.core.licensing.inventory.DependencyInventory`,
  `ModelLicenseInventory`
- `pi_platform.core.licensing.sbom.emit_spdx_sbom`,
  `emit_notice_file`
- `pi_platform.adapters.fs.fs_adapter.LocalFilesystemAdapter`
- `pi_platform.adapters.git.cli_adapter.GitCliAdapter`

All ports are declared in `platform/ports/` and consumed by the core
module. Adapters live in `platform/adapters/`. Per the ports-and-
adapters ADR ([`adr.ports-and-adapters-extension-style`](../../../.ai/wiki/adr/0004-ports-and-adapters-extension-style.md)),
no adapter is imported from inside `platform/core/`.

### Deterministic serialization

The serializer uses `json.dumps(..., sort_keys=True,
ensure_ascii=False, separators=(",", ":"))` plus a trailing
`\n`. Sorted array ordering is applied to all identifier arrays
(`entityIds`, `childIds`, `parentId`-derived lists, `relations`
arrays, `evidence` arrays). The serializer does not embed volatile
metadata; volatile metadata lives in the manifest envelope.

### OKF v0.2 profile

The OKF v0.2 profile is a thin Python implementation that:

- parses YAML frontmatter from a Markdown string;
- validates the root `index.md` for `okf_version: "0.2"` and
  `type: "WikiIndex"`;
- validates that every non-reserved concept Markdown file under
  `project-knowledge/wiki/` has YAML frontmatter and a non-empty
  `type` field;
- recognises `pi_`-prefixed fields as platform extensions and does
  not reject them;
- emits a deterministic Markdown serialization of the same concept
  with sorted extension fields and stable link ordering;
- validates reserved filenames (`index.md`, `log.md`).

The internal Knowledge Model is intentionally decoupled from the
profile implementation; only `OkfAdapter` knows the OKF v0.2 wire
shape.

### Hydrate / reconcile / materialise

Phase 1 implements the contract but not the full storage. The
runtime store is a content-addressed cache under
`.project-intelligence-cache/` that records per-shard canonical
serializations keyed by their SHA-256. The hydrate service:

1. reads every manifest under `project-knowledge/manifests/`;
2. for each shard declared by the manifest, checks whether the
   content hash is present in the runtime cache; if not, the
   canonical file is read and registered;
3. computes a per-family cache hit rate in the `hydrateReport`;
4. applies the working-tree overlay;
5. marks stale canonical shards (those that no longer appear in the
   manifest) as `stale` in the runtime cache.

The reconcile service performs incremental reconciliation on branch
switch by comparing the previous HEAD manifest's content hashes with
the new HEAD manifest's hashes; only changed shards are re-ingested.

The materialise service:

1. selects pending runtime changes (those marked
   `KnowledgeState.verified` and not from `LOCAL_ONLY` sources);
2. normalises each selected change to its canonical form;
3. writes the change to its canonical family shard;
4. updates the family manifest;
5. regenerates affected Wiki Markdown via the OKF adapter;
6. runs the OKF conformance validator and the license gate;
7. returns a Git diff summary; no commit is performed unless the
   approval token is provided and the `PolicyDecisionStub` returns
   `ALLOW`. By default the stub returns `REQUIRE_APPROVAL` so any
   automated invocation is non-destructive.

### Write-ahead log

The write-ahead log records `(materialise_id, op_id, payload)` JSON
lines to `.project-intelligence-cache/wal.log` before each
materialise step. On startup, if a `materialise_in_progress`
marker is present and the WAL contains uncommitted entries, the WAL
is rolled back to the last committed entry. If no marker is
present, the WAL is truncated. This guarantees crash-safe recovery
per the design's failure-mode contract.

### Project lock

`pi_platform.core.sync.project_lock.ProjectLock` uses the same
advisory file-lock semantics as `scripts/file_lock.py`
(`fcntl.flock` on POSIX, `msvcrt.locking` on Windows). It is
implemented independently; the product does not import the harness
script. Per the design, the lock files live at
`tmp/local/project-locks/<project-id>.lock` so the harness lock
files at `tmp/local/session-locks/` and the product lock files do
not collide.

### Licensing

The `LicensePolicy` evaluator reads the documented allow/review/deny
lists from `project-knowledge/project-context.yaml` and evaluates a
list of `Dependency` records against the policy. The `LicenseGate`
returns one of `PASS`, `FAIL`, `REVIEW` per dependency and rolls them
up into a build-blocking decision.

The `DependencyInventory` is constructed from
`distribution/licenses/dependency-inventory.json` (generated by the
stub CI license gate). The `ModelLicenseInventory` is read from
`distribution/licenses/model-licenses.json` when present.

The CI license gate is wired as a `make license-gate` target that
invokes `python -m pi_platform.cli license-gate`. The gate fails the
build when a dependency lacks an SPDX identifier or matches a deny
pattern. Phase 1 ships the gate logic and a stub inventory so the
gate can be exercised; Phase 2 wires the inventory generator into
the package install pipeline.

### Sandbox and testing

All Phase 1 tests use `tempfile.TemporaryDirectory` for the target
project root and avoid any global state. Tests do not depend on the
network. Tests use `unittest` to match the existing harness test
conventions.

Tests added in Phase 1:

- `tests.test_canonical_value_types.ValueTypeTests` — every value
  type round-trips through the canonical serializer.
- `tests.test_canonical_roundtrip.RoundtripTests` — property-based
  test asserting byte-identical serialization for equivalent
  in-memory states; covers chunk, entity, relation, manifest and
  metadata.
- `tests.test_canonical_content_address.ContentAddressTests` —
  SHA-256 addressing tests; verifies that identical bodies share a
  cache key and that a modification changes the address.
- `tests.test_canonical_manifest.ManifestTests` — manifest write,
  read and content-hash stability.
- `tests.test_canonical_okf.OkfTests` — OKF v0.2 frontmatter parse,
  root-index validation, reserved-filename validation, link
  stability, no-binary check.
- `tests.test_project_knowledge_layout.LayoutTests` —
  `project-knowledge/` directory creation, gitignore update, custom
  cache root, `project-context.yaml` defaults and policy override.
- `tests.test_git_port.GitPortTests` — HEAD, branch, status, log,
  LFS pointer detection. Skipped when `git` is not installed.
- `tests.test_version_identity.VersionIdentityTests` — version
  identity tuple format, embedding-model-version default,
  working-tree fingerprint stability, branch-name independence.
- `tests.test_working_tree_overlay.WorkingTreeOverlayTests` —
  overlay captures uncommitted changes, is deterministic, does not
  cause canonical file modification.
- `tests.test_sync_hydrate.HydrateTests` — cold-start and warm-start
  hydrate, per-family cache hit rate, branch-switch incremental
  reconciliation, stale-knowledge detection.
- `tests.test_sync_materialise.MaterialiseTests` — materialise
  produces a Git diff, excludes LOCAL_ONLY sources, is approval-
  gated.
- `tests.test_sync_roundtrip.RoundtripTests` — end-to-end hydrate
  → edit → materialise → no-diff round trip.
- `tests.test_project_lock.ProjectLockTests` — concurrent
  acquisition serialised; cross-platform semantics match
  `scripts/file_lock.py`.
- `tests.test_write_ahead_log.WalTests` — WAL recovery semantics;
  rollback on startup.
- `tests.test_license_policy.LicensePolicyTests` — allow/review/
  deny evaluation; review acceptance; model-license tracking;
  SBOM emission.
- `tests.test_license_gate.LicenseGateTests` — gate fails build on
  missing SPDX identifier or matching deny pattern; passes on
  allow-listed license.
- `tests.test_cli_entrypoint.CliEntrypointTests` — `python -m
  pi_platform.cli` subcommands smoke tests.

### Container, compose and launchers

`Containerfile` is a single-stage `python:3.11-slim`-based image
that installs the platform package, copies `distribution/licenses/`
artifacts and exposes the documented control-plane port (default
`8765`). `docker-compose.yml` documents the profiles
(`core-headless`, `desktop-lite`, `desktop-local-ai`, `open-webui`,
`enterprise`) per
[`plan-v0-8-platform-architecture/tasks.md`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md)
task 19. The launchers are skeletons in Phase 1 — they verify
Docker/Podman availability and start the default profile, but full
one-click behaviour ships in Phase 9.

### Distribution scaffolding

Phase 1 scaffolds the empty directory tree under `distribution/`
required by the
[`project-knowledge-repository-layout`](../../specs/2026-10-04-project-knowledge-repository-layout/spec.md)
spec. Only `distribution/licenses/` is populated with a stub
inventory so the license gate has evidence to read.

## Affected modules / interfaces

| Module / path | Affect |
|---|---|
| `platform/` | new (this change) |
| `platform/core/canonical/`, `platform/core/git/`, `platform/core/sync/`, `platform/core/licensing/` | new |
| `platform/ports/`, `platform/adapters/`, `platform/runtime/`, `platform/cli/` | new |
| `project-knowledge/` | new (scaffolded by `init-project`) |
| `.project-intelligence-cache/` | new (scaffolded by `init-project`; gitignored) |
| `distribution/{licenses,skills,codex,claude-code,opencode,generic-agent,sbom}/` | new |
| `Containerfile`, `docker-compose.yml` | new |
| `scripts/project-intelligence.sh`, `scripts/Start-ProjectIntelligence.ps1` | new |
| `.ai/wiki/adr/0005-platform-source-language.md` | new |
| `.ai/wiki/adr/0002-canonical-runtime-separation.md`, `0003-license-governance-default.md`, `0004-ports-and-adapters-extension-style.md` | status: proposed → accepted |
| `.ai/wiki/architecture/platform-overview.md`, `architecture/system-overview.md`, `glossary/platform.md`, `modules/platform-core.md`, `interfaces/canonical.md`, `interfaces/git.md`, `interfaces/sync.md`, `interfaces/licensing.md` | updated |
| `.ai/wiki/INDEX.md` | updated |
| `openspec/CURRENT.md` | unchanged (Phase 1 capabilities already listed) |
| `openspec/specs/2026-10-04-*` | additive deltas via this change's spec folders |

## Data / persistence / concurrency impact

- Canonical knowledge lives under `project-knowledge/` in
  sharded JSON/YAML/Markdown files (small, deterministic, Git-
  friendly). Large files are split, never committed monolithically.
- Runtime cache lives under `.project-intelligence-cache/`
  (gitignored) using a filesystem content-hash directory.
- Concurrency is serialised per target project via the
  `ProjectLock` advisory file lock at
  `tmp/local/project-locks/<project-id>.lock`.
- The write-ahead log lives at
  `.project-intelligence-cache/wal.log`; it is recovered on
  startup.
- No database migration is required for this change because no
  runtime database exists yet; that arrives in Phase 3.

## Compatibility and migration

This change introduces only new files; no existing harness
contract, schema, command, plugin, Wiki page semantics or test is
altered. The Phase 1 implementation:

- does **not** change `harness.py` behaviour;
- does **not** change `openspec/specs/2026-09-07-*`,
  `2026-10-03-*`, `2026-10-04-harness-command-lifecycle`;
- does **not** import or call harness scripts from the platform
  code (the project lock is a separate implementation of the
  advisory file-lock semantics);
- does **not** remove or relocate any existing harness artifact;
- does **not** alter `.gitignore` for the implementation project
  (only for the bound target project's `.gitignore` when
  `init-project` is run).

## Risks and rollback

Risks:

- **phase-1 module boundary mistakes** — mitigated by following
  the documented design and by exposing ports rather than concrete
  classes for every Phase 1 capability.
- **deterministic serialization drift** — mitigated by the
  `tests.test_canonical_roundtrip` property-based test.
- **materialise-on-startup regression** — mitigated by the
  approval-gated `MaterialiseService` default and by the
  write-ahead log rollback.
- **license gate false positives** — mitigated by the explicit
  `licensing.review` and `licensing.denyPatterns` configuration
  documented in the spec and exercised by
  `tests.test_license_policy`.

Rollback:

- the change reverts cleanly by deleting `platform/` and the
  scaffolded `project-knowledge/`, `.project-intelligence-cache/`,
  `distribution/` directories; reverting the Wiki edits and the ADR
  status flips is additive;
- because Phase 1 introduces only new files and no existing
  artefact is altered, no runtime migration is required.