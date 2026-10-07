# Context impact — implement-phase-5-orchestration

The Wiki, ADR and `openspec/CURRENT.md` updates are
documented in
[`openspec/changes/prepare-phase-5-orchestration/context-impact.md`](../../prepare-phase-5-orchestration/context-impact.md).
This file is a thin reference so the implementation change
carries its own context-impact section.

## Implementation surface (summary)

- `pi_platform/core/orchestration/` — new core subpackage;
- `pi_platform/ports/orchestration/` — new ports subpackage;
- `pi_platform/adapters/orchestration/` — new default
  adapters;
- `tests/test_orchestration_phase5.py` — per-capability
  regression suite;
- `tests/test_orchestration_policy.py` — §33 retrieval-
  first policy regression test;
- `distribution/licenses/dependency-inventory.json` — no
  new entries; the default stub `LocalLLMPort` ships under
  Apache-2.0 with no new runtime dependency;
- `pi_platform/cli/main.py` — new `orchestrator-status`,
  `llm-status`, `capabilities` subcommands.

## Knowledge to create / update

See
[`openspec/changes/prepare-phase-5-orchestration/context-impact.md`](../../prepare-phase-5-orchestration/context-impact.md)
for the Wiki, ADR and `CURRENT.md` updates.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md`
  — unaffected.
- `adr/0002-canonical-runtime-separation.md` — unaffected;
  Phase 5 task context bundles are ephemeral per §52.
- `adr/0003-license-governance-default.md` — unaffected;
  every Phase 5 LLM dependency passes `LicenseGate` before
  registration.
- `adr/0004-ports-and-adapters-extension-style.md` —
  unaffected.
- `adr/0005-platform-source-language.md` — unaffected.
- `adr/0006-phase-2-parser-selection.md` — unaffected.
- `adr/0007-phase-2-inbox-policy-default.md` — unaffected.
- `adr/0008-embedded-storage-selection.md` — unaffected;
  Phase 5 composes the Phase 4 retrieval surface through
  the documented ports.

## Acceptance criteria

- [ ] `python harness.py check` returns `Harness core
  checks: PASS`;
- [ ] `openspec validate implement-phase-5-orchestration
  --type change --strict` returns `valid`;
- [ ] `python harness.py wiki-validate` returns
  `{"ok": true, ...}`;
- [ ] `python3 scripts/artifact_manifest.py verify` returns
  `Artifact manifest: PASS`;
- [ ] `python -m unittest tests.test_platform_phase1
  tests.test_platform_phase2
  tests.test_content_address_cross_branch
  tests.test_canonical_roundtrip
  tests.test_platform_phase3 tests.test_graph_50k
  tests.test_platform_phase4
  tests.test_retrieval_benchmark
  tests.test_orchestration_phase5
  tests.test_orchestration_policy -v` returns green;
- [ ] `openspec/specs/2026-10-05-*/` includes the five
  Phase 5 capabilities;
- [ ] `openspec/CURRENT.md` lists the five Phase 5
  capabilities under "Project product capabilities";
- [ ] `plan-v0-8-platform-architecture/tasks.md` rows
  79-84 are `[x]`.