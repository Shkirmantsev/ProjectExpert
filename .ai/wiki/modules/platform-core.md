---
id: modules.platform-core
title: Platform Core Modules
kind: modules
status: active
summary: Reference page describing the implemented Phase 1 modules under `pi_platform/`.
sourceRefs:
  - pi_platform/core/canonical/value_types.py
  - pi_platform/core/git/version_identity.py
  - pi_platform/core/sync/hydrate.py
  - pi_platform/core/licensing/policy.py
  - openspec/changes/implement-phase-1-foundation/design.md
maintenance:
  mode: authored
---

# Platform Core Modules

Phase 1 ships the following modules under `pi_platform/`. Every
module adheres to the hexagonal + micro-kernel extension style
([`adr.ports-and-adapters-extension-style`](../adr/0004-ports-and-adapters-extension-style.md)).

## `pi_platform.core.canonical`

Deterministic value types, content addressing, manifest I/O and
the OKF v0.2 profile.

- `value_types.py` — every Phase 1 value type as a frozen
  `dataclass`: `Source`, `Document`, `Section`, `Chunk`,
  `ContextualChunk`, `Entity`, `Relation`, `Evidence`,
  `KnowledgeState`, `ProjectVersion`, `Shard`, `Manifest`,
  `RuntimeChange`, `TaskContext`, `Metadata`. Identifier arrays
  are sorted ascending by string value so two equivalent
  in-memory states produce byte-identical canonical files.
- `serializer.py` — canonical JSON / YAML serializers with
  sorted keys, `\n` line endings and trailing newline.
- `content_address.py` — SHA-256 hex digests over the canonical
  serialization plus the `objects/<hash-prefix[0:2]>/<hash-rest>.json`
  shard path.
- `manifest.py` — manifest writer / reader per knowledge family
  (`graph`, `chunks`, `sources`, `objects`) with self-hash
  verification.
- `okf.py` — `OkfAdapter` abstract, `OkfV02Profile` concrete,
  `pi_` extension prefix handling and the bundle validator.
- `validator.py` — OKF conformance validator used as a
  pre-materialisation gate.

## `pi_platform.core.git`

Git CLI adapter, version identity tuple and working-tree
overlay.

- `git_port.py` — re-export of the default adapter.
- `version_identity.py` — `compute_version_identity` returns the
  structured tuple. `embedding_model_version` defaults to the
  literal string `"unknown"` until Phase 4 binds an embedding.
- `working_tree_overlay.py` — deterministic JSON overlay of the
  working-tree changes (modified/added/deleted/untracked).
- The CLI adapter lives in `pi_platform.adapters.git.cli_adapter`
  and uses the system `git` binary with a documented minimum
  version contract (`>= 2.30`).

## `pi_platform.core.sync`

Hydrate, reconcile, materialise, the Phase 1 policy stub, the
per-project advisory file lock and the write-ahead log.

- `hydrate.py` — `HydrateService.restore_runtime` reads every
  manifest and populates the runtime cache with per-shard
  content hashes; reports per-family cache hit rates.
- `reconcile.py` — `ReconcileService.reconcile_branch_switch`
  performs incremental reconciliation reusing unchanged shards
  across branches.
- `materialise.py` — `MaterialiseService.materialise_durable_changes`
  is approval-gated, excludes `LOCAL_ONLY` sources, writes only
  durable changes to canonical shards and updates the affected
  manifests.
- `policy_stub.py` — `PolicyDecisionStub.decide` returns
  `ALLOW / DENY / REQUIRE_APPROVAL`. Default behaviour:
  `hydrate`/`reconcile` → `ALLOW`, `materialise` →
  `REQUIRE_APPROVAL`.
- `project_lock.py` — `ProjectLock` advisory file lock with
  cross-platform `fcntl` / `msvcrt` semantics, scoped to
  `tmp/local/project-locks/<project-id>.lock`.
- `wal.py` — `WriteAheadLog` records one JSON line per
  materialise operation and supports crash-safe recovery via the
  `materialise_in_progress` marker.

## `pi_platform.core.licensing`

License policy, gate, inventory and SBOM / NOTICE emitter.

- `policy.py` — `LicensePolicy.evaluate` returns `allow`,
  `review` or `deny` for a single `Dependency`. Default lists
  match the `license-governance` spec.
- `gate.py` — `LicenseGate.run` is the build-blocking decision
  over an iterable of dependencies; honours the `review`
  acceptance token map.
- `inventory.py` — `DependencyInventory` and
  `ModelLicenseInventory` load / save the JSON artefacts under
  `distribution/licenses/`.
- `sbom.py` — `emit_spdx_sbom` (SPDX-2.3 JSON) and
  `emit_notice_file`.

## `pi_platform.adapters.fs`

`LocalFilesystemAdapter` encapsulates the canonical and runtime
directory contract plus `ensure_gitignore` and the manifest
read / write helpers. The adapter never touches Git, embeddings
or network resources.

## `pi_platform.adapters.git`

`GitCliAdapter` is the default Git port. It uses the system
`git` binary exclusively and validates the minimum version
contract before every invocation.

## `pi_platform.runtime`

`RuntimeCache` is the content-addressed filesystem cache under
`.project-intelligence-cache/`. Each cache entry is stored at
`<cache-root>/<hash-prefix[0:2]>/<hash-rest>.json` and indexed
in `<cache-root>/index.json`. Phase 3 replaces this stub with
the embedded relational + vector + graph store.

## `pi_platform.cli`

The `python -m pi_platform.cli` entry point exposes the
documented subcommands. Subcommands raise non-zero on failure
and emit JSON for machine consumption.

## Failure and recovery contract

- Hydrate is read-only; an interruption leaves the previous
  runtime state intact and the next startup resumes from the
  last committed manifest.
- Materialise writes through the write-ahead log; an
  interruption rolls back to the last committed materialisation.
- The project advisory file lock serialises per-project
  hydrate / materialise calls and refuses concurrent acquisition
  with a clear error.

## Related

- [`interfaces/canonical`](../interfaces/canonical.md)
- [`interfaces/git`](../interfaces/git.md)
- [`interfaces/sync`](../interfaces/sync.md)
- [`interfaces/licensing`](../interfaces/licensing.md)
- [`architecture/platform-overview`](../architecture/platform-overview.md)