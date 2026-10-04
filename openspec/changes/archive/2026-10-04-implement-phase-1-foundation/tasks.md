# Tasks — implement-phase-1-foundation

This tasks file mirrors Phase 1 (tasks 13-44) of the
[`plan-v0-8-platform-architecture/tasks.md`](../../changes/archive/2026-10-04-plan-v0-8-platform-architecture/tasks.md)
file. Tasks are grouped by section in the order they will be
executed by the implementer; lower-numbered tasks are prerequisites
for higher-numbered tasks.

The acceptance criteria are recorded inline; the task is marked
complete only when both the task body and the verification
command pass.

## 1. Decisions and ADRs

- [ ] 1.1 — Record the platform source language decision in a new
  ADR [`adr.platform-source-language`](../../../.ai/wiki/adr/0005-platform-source-language.md)
  (Python 3.11; rationale and rejected alternatives documented).
- [ ] 1.2 — Flip [`adr.canonical-runtime-separation`](../../../.ai/wiki/adr/0002-canonical-runtime-separation.md)
  to `status: accepted`.
- [ ] 1.3 — Flip [`adr.license-governance-default`](../../../.ai/wiki/adr/0003-license-governance-default.md)
  to `status: accepted`.
- [ ] 1.4 — Flip [`adr.ports-and-adapters-extension-style`](../../../.ai/wiki/adr/0004-ports-and-adapters-extension-style.md)
  to `status: accepted`.

## 2. Repository scaffolding

- [ ] 2.1 — Create the `platform/` module tree documented in
  [`design.md`](design.md) — `platform/{core/{canonical,git,sync,
  licensing},ports,adapters/{fs,git},runtime,cli}/` with
  `__init__.py` files. Do not create empty subpackages for later
  phases.
- [ ] 2.2 — Add `distribution/{licenses,skills,codex,claude-code,
  opencode,generic-agent,sbom}/.gitkeep` so the empty distribution
  tree survives checkout.
- [ ] 2.3 — Add `Containerfile` skeleton and `docker-compose.yml`
  documenting the five profiles.
- [ ] 2.4 — Add `scripts/project-intelligence.sh` (Linux) and
  `scripts/Start-ProjectIntelligence.ps1` (Windows) launcher
  skeletons.

## 3. Core canonical module

- [ ] 3.1 — Implement the value types
  (`Source`, `Document`, `Section`, `Chunk`, `ContextualChunk`,
  `Entity`, `Relation`, `Evidence`, `KnowledgeState`,
  `ProjectVersion`, `Shard`, `Manifest`, `RuntimeChange`,
  `TaskContext`, `Metadata`) in
  `platform/core/canonical/value_types.py` using `dataclasses`
  with deterministic JSON/YAML serializers
  (`platform/core/canonical/serializer.py`).
- [ ] 3.2 — Implement the SHA-256 content addressing utility in
  `platform/core/canonical/content_address.py` and the property-
  based round-trip test in
  [`tests/test_canonical_roundtrip.py`](../../../tests/test_canonical_roundtrip.py).
- [ ] 3.3 — Implement the manifest writer/reader per knowledge
  family (`graph`, `chunks`, `sources`, `objects`) in
  `platform/core/canonical/manifest.py` and the manifest-driven
  hydration driver in
  `platform/core/sync/hydrate.py`.
- [ ] 3.4 — Implement the `OkfAdapter` interface, the OKF v0.2
  profile implementation, the `pi_` extension prefix handling and
  the conformance validator in
  `platform/core/canonical/okf.py` and `okf_validator.py`.
- [ ] 3.5 — Implement the §23 metadata value type and the
  `validFrom <= validTo` validator in
  `platform/core/canonical/value_types.py`.

## 4. Core git module

- [ ] 4.1 — Implement `platform/core/git/git_port.py` with the
  CLI adapter default and the minimum Git version contract
  documentation (>= 2.30 documented in code).
- [ ] 4.2 — Implement `platform/core/git/version_identity.py`
  with `compute_version_identity(...)` returning the structured
  tuple and `embedding_model_version` defaulting to `"unknown"`.
- [ ] 4.3 — Implement `platform/core/git/working_tree_overlay.py`
  with deterministic overlay serialization.

## 5. Core sync module

- [ ] 5.1 — Implement `platform/core/sync/hydrate.py`
  (`HydrateService.restore_runtime`).
- [ ] 5.2 — Implement `platform/core/sync/reconcile.py`
  (`ReconcileService.reconcile_branch_switch`).
- [ ] 5.3 — Implement `platform/core/sync/materialise.py`
  (`MaterialiseService.materialise_durable_changes`) with the
  approval-gated flow.
- [ ] 5.4 — Implement `platform/core/sync/policy_stub.py`
  (`PolicyDecisionStub`) returning `ALLOW / DENY / REQUIRE_APPROVAL`.
- [ ] 5.5 — Implement `platform/core/sync/project_lock.py`
  (`ProjectLock`) using the same advisory file-lock semantics as
  `scripts/file_lock.py`.
- [ ] 5.6 — Implement `platform/core/sync/wal.py`
  (`WriteAheadLog`) for crash-safe materialise recovery.

## 6. Core licensing module

- [ ] 6.1 — Implement `platform/core/licensing/policy.py`
  (`LicensePolicy.allow_review_deny`).
- [ ] 6.2 — Implement `platform/core/licensing/gate.py`
  (`LicenseGate.run`).
- [ ] 6.3 — Implement `platform/core/licensing/inventory.py`
  (`DependencyInventory` and `ModelLicenseInventory`).
- [ ] 6.4 — Implement `platform/core/licensing/sbom.py` emitting
  SPDX SBOM and NOTICE file.

## 7. Adapters and runtime stub

- [ ] 7.1 — Implement `platform/adapters/fs/fs_adapter.py`
  (`LocalFilesystemAdapter`).
- [ ] 7.2 — Implement `platform/adapters/git/cli_adapter.py`
  (`GitCliAdapter`).
- [ ] 7.3 — Implement `platform/runtime/cache.py` with the
  content-addressed cache and the per-project runtime cache root
  contract.

## 8. CLI

- [ ] 8.1 — Implement `platform/cli/main.py` exposing
  `init-project`, `hydrate`, `materialise`, `license-gate`,
  `okf-validate`, `version-identity`, `wal-recover`.

## 9. Tests and verification

- [ ] 9.1 — Add focused regression tests under `tests/` covering
  every Phase 1 scenario in the five foundation specs.
- [ ] 9.2 — Add the end-to-end round-trip test
  [`tests/test_sync_roundtrip.py`](../../../tests/test_sync_roundtrip.py).
- [ ] 9.3 — Add the CI license-gate regression test
  [`tests/test_license_gate.py`](../../../tests/test_license_gate.py).
- [ ] 9.4 — Update affected Wiki nodes
  (`architecture/platform-overview`, `glossary/platform`,
  `modules/platform-core`, `interfaces/canonical`,
  `interfaces/git`, `interfaces/sync`, `interfaces/licensing`)
  and `INDEX.md`.
- [ ] 9.5 — Run
  `openspec validate implement-phase-1-foundation --type change`
  and `python harness.py check`; both MUST pass.
- [ ] 9.6 — Run `python harness.py wiki-init` to regenerate the
  Wiki FTS index.

## 10. Archive

- [ ] 10.1 — Archive this change with
  `openspec archive implement-phase-1-foundation -y`.
- [ ] 10.2 — Verify `openspec/CURRENT.md` lists the five Phase 1
  capabilities (already true after step 9.5; the archive step
  promotes the additive delta spec files but does not modify
  the five Phase 1 base spec identities).
- [ ] 10.3 — Commit on `feature/generate-init-project`.