# Context impact — implement-phase-10-a2a-quality-gates

## Knowledge nodes to create

Same set documented in
[`prepare-phase-10-a2a-quality-gates/context-impact.md`](../prepare-phase-10-a2a-quality-gates/context-impact.md),
plus the implementation-time evidence in
`.ai/wiki/project/implementation-roadmap.md`.

## Knowledge nodes to update

Same updates as the prepare change, plus the final
`architecture/platform-overview.md` and `architecture/system-overview.md`
status flip to `active`.

## ADRs to create

| ADR | Decision |
|---|---|
| 0021 | A2A adapter isolation from the core domain model |
| 0022 | Reverse delegation is opt-in by default |
| 0023 | A2A transport uses the Python standard library only for v1.0 |

## Implementation areas (delta from the prepare change)

The complete surface is listed in
[`prepare-phase-10-a2a-quality-gates/design.md`](../prepare-phase-10-a2a-quality-gates/design.md)
under "Module map".

## Invariants that must not break

All §68 invariants. The implementation change ships the
`invariants/v0.8.md` wiki node and the probe suite that exercises
every invariant; the probe suite is the executable evidence that
the invariants hold post-Phase 10.

## Verification surface

- `python -m unittest tests.test_phase_10_a2a`
- `python -m unittest tests.test_phase_10_quality_gates`
- `python -m unittest tests.test_phase_10_invariants`
- `python -m unittest tests.test_phase_10_schema_migration`
- `make eval`
- `make invariants`
- Full offline suite remains green
- `python harness.py check`
- `openspec validate --all --strict`

## Close-out gates

- All three capability specs adopted and listed exactly once in
  `openspec/CURRENT.md`
- Plan tasks 117-123 marked `[x]` in
  `plan-v0-8-platform-architecture/tasks.md`
- `tests/test_phase_10_*` green; full offline suite still green
- `python harness.py check` PASS; `openspec validate --all --strict` PASS
- Both changes archived under their archive dates
- v1.0 evidence recorded: container image tag, OCI artefact and
  distribution bundles linked from the README

## Handoff

The implementation change is closed out by archiving itself. A
final session checkpoint with status `complete` is recorded under
`.ai/state/handoffs/implement-phase-10-a2a-quality-gates.json`.
