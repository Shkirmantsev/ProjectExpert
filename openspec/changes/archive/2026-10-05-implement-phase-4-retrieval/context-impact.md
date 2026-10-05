# Context impact — implement-phase-4-retrieval

The Wiki, ADR and `openspec/CURRENT.md` updates are documented in
[`openspec/changes/prepare-phase-4-retrieval/context-impact.md`](../../prepare-phase-4-retrieval/context-impact.md).
This file is a thin reference so the implementation change
carries its own context-impact section.

## Implementation surface (summary)

- `pi_platform/core/retrieval/` — new core subpackage;
- `pi_platform/ports/retrieval/` — new ports subpackage;
- `pi_platform/adapters/retrieval/` — new default adapters;
- `pi_platform/adapters/runtime/graph_expansion.py` — production
  adapter replacing the Phase 3 stub;
- `tests/test_retrieval_benchmark.py` — Phase 4 evaluation fixture;
- `distribution/licenses/dependency-inventory.json` — new SPDX
  entries for embedding / reranker;
- `Containerfile` — install steps for the new Python packages;
- `pi_platform/cli/main.py` — new `retrieval-status`,
  `embedding-status`, `reranker-status` subcommands.

## Knowledge to create / update

See [`openSpec/changes/prepare-phase-4-retrieval/context-impact.md`](../../prepare-phase-4-retrieval/context-impact.md)
for the Wiki, ADR and `CURRENT.md` updates.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md` —
  unaffected.
- `adr/0002-canonical-runtime-separation.md` — unaffected.
- `adr/0003-license-governance-default.md` — unaffected; every
  Phase 4 dependency passes `LicenseGate` before registration.
- `adr/0004-ports-and-adapters-extension-style.md` — unaffected.
- `adr/0005-platform-source-language.md` — unaffected.
- `adr/0006-phase-2-parser-selection.md` — unaffected.
- `adr/0007-phase-2-inbox-policy-default.md` — unaffected.
- `adr/0008-embedded-storage-selection.md` — unaffected; Phase 4
  composes the Phase 3 storage backend through the documented
  ports.
- new `adr/0009-embedding-model-selection.md` — added by this
  change.
- new optional `adr/0010-hybrid-fusion-strategy.md` — added by
  this change.

## Acceptance criteria

- [ ] `python harness.py check` returns `Harness core checks:
  PASS`;
- [ ] `openspec validate implement-phase-4-retrieval --type
  change --strict` returns `valid`;
- [ ] `python harness.py wiki-validate` returns `{"ok": true,
  ...}`;
- [ ] `python3 scripts/artifact_manifest.py verify` returns
  `Artifact manifest: PASS`;
- [ ] `python -m unittest tests.test_platform_phase1
  tests.test_platform_phase2 tests.test_content_address_cross_branch
  tests.test_canonical_roundtrip tests.test_platform_phase3
  tests.test_graph_50k tests.test_retrieval_benchmark -v` returns
  green;
- [ ] `openspec/specs/2026-10-04-*/` includes the eight Phase 4
  capabilities;
- [ ] `openspec/CURRENT.md` lists the eight Phase 4 capabilities
  under "Project product capabilities";
- [ ] `plan-v0-8-platform-architecture/tasks.md` rows 70-78 are
  `[x]`.