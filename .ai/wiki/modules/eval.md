---
id: a2a-eval
kind: module
title: Eval Core
status: active
pi_phase: 10
pi_section: "§49, §120, §121"
pi_capability: integration-quality-gates
---

# Eval Core

The Phase 10 eval core ships the deterministic regression harness
required by v0.8 §49, §120 and §121. It is the Python home of the
**structured metric file**, the **scenario base classes** the
quality-gates suites consume, the **§68 invariant probe base**, and
the **schema-version migration guard** helpers.

## Module map

- `pi_platform/core/eval/metrics.py` — the `EvalMetrics` accumulator
  and the `EvalReport` value type carrying the
  `phase-10-eval/1` schema;
- `pi_platform/core/eval/writer.py` — atomic write helper for
  `tmp/local/project-context/eval/last.json` (`tmpfile + rename`);
- `pi_platform/core/eval/scenarios.py` — `Scenario`,
  `ScenarioContext`, `ScenarioOutcome`, and the deterministic
  `StubCodingAgent` used by the retrieval-first scenarios;
- `pi_platform/core/eval/invariants.py` — `InvariantProbe` base
  class and the loader. `INVARIANT_COUNT = 52` is the architecture
  source of truth;
- `pi_platform/core/eval/migration_guard.py` — the four typed
  errors (`IdentityInvalid`, `MigrationRequired`, `Incompatible`,
  `WorkingTreeMismatch`) and the `check_schema_identity` helper.

## Test modules

- `tests/test_phase_10_quality_gates.py` — 11 scenario classes
  covering skill activation, MCP tool-selection, retrieval-first
  compliance, version mismatch, stale/conflict, security filter,
  plugin lifecycle, OKF conformance, round-trip, branch-switch,
  token-context-cost and deterministic metric file;
- `tests/test_phase_10_invariants.py` — 4 loader tests plus 52
  probe classes (one per §68 invariant); every probe asserts
  something — see `kb://invariants.v0.8`; the adversarial suite
  in `tests/test_phase_10_adversarial.py` proves every probe
  flips to False under a real break;
- `tests/test_phase_10_schema_migration.py` — 9 tests covering the
  four typed errors and the no-mutation invariant.

## CLI and CI wiring

Three subcommands are added to `pi_platform.cli`:

- `eval` — runs the §49 suites and atomically writes
  `tmp/local/project-context/eval/last.json`;
- `invariants` — runs the §120 acceptance suite, writes the same
  file, and reports the enforced/declared probe split;
- `metrics-gate` — validates that file: schema name/version, then
  real bounds (rates in `[0.0, 1.0]`, counters `>= 0`,
  `invariants_passed <= invariants_run`). It exits non-zero and
  prints the offending metric names on any violation.

`Makefile` exposes them as `make eval`, `make invariants` and
`make metrics-gate`. The targets are additive and keep the default
offline suite deterministic (no A2A, no reverse delegation, no
container runtime, no network).

## Related

- `kb://interfaces.a2a`
- `kb://interfaces.reverse-delegation`
- `kb://modules.a2a`
- `kb://adr.0021-a2a-adapter-isolation`
- `kb://adr.0022-reverse-delegation-default-off`
- `openspec/specs/2026-10-12-integration-quality-gates/spec.md`
