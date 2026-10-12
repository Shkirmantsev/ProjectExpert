# Tasks — prepare-phase-9-distribution

This change ships the three Phase 9 capability specs and zero production code.
The specification deltas under [`specs/`](specs) are the authoritative
behavioural contract. The future
[`implement-phase-9-distribution`](../implement-phase-9-distribution/tasks.md)
change implements and verifies them before adoption.

Plan tasks 109-116 in
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md)
remain unchecked until the implementation change completes.

## Preparation tasks

- [x] P1. Author `proposal.md` naming the three affected capabilities and the
  explicit non-goals.
- [x] P2. Author `specs/2026-10-11-human-interface-web-ui/spec.md` covering the
  §57 ten-operation surface, adapter-only REST, no-coding-harness operation,
  loopback binding, bearer token, policy authorisation, approval-controlled
  materialisation, egress-governed delegation, static frontend without a Node
  runtime, replaceable frontends, the feature-flagged Open WebUI profile and the
  minimal OpenAI-compatible shim.
- [x] P3. Author `specs/2026-10-11-okf-wiki-profile-distribution/spec.md`
  covering validation before durable commit, declared OKF version, mandatory
  concept `type`, reserved file semantics, `pi_` extension fields, runtime-data
  exclusion, adapter isolation, no bundled project knowledge and the
  operator-callable conformance gate.
- [x] P4. Author `specs/2026-10-11-one-click-distribution/spec.md` covering the
  seven launcher duties, single-container default, optional second container, the
  five documented profiles, pinned image inputs, health/readiness separation,
  gated launch smoke verification and launcher parity.
- [x] P5. Author `design.md` recording the transport, frontend, OKF scope
  correction, deployment model and rejected alternatives.
- [x] P6. Author `context-impact.md` naming the knowledge nodes, ADRs,
  implementation areas and invariants that must not break.
- [x] P7. Author the mirrored `implement-phase-9-distribution` change with the
  implementation and verification checklist.
- [x] P8. Validate: `python harness.py openspec-check` and
  `openspec validate --all --strict` PASS with zero production code added under
  `pi_platform/`.

## Implementation tasks (owned by the next change)

These mirror plan tasks 109-116 and are executed by
`implement-phase-9-distribution`:

- 109 REST API surface and policy/approval/egress composition
- 110 lightweight static frontend served by the core container
- 111 optional Open WebUI adapter behind a feature flag
- 112 OKF validation gate and profile distribution
- 113 Linux and Windows one-click launchers
- 114 single-container default image and compose profile finalisation
- 115 launch smoke tests
- 116 Wiki, ADR, `openspec/CURRENT.md` and archive

## Close-out gate for the implementation change

- All three capability specs adopted under
  `openspec/specs/2026-10-11-*/` and listed exactly once in `openspec/CURRENT.md`
- `tests/test_phase_9_distribution.py` green; full offline suite still green
- `python harness.py check` PASS
- Plan tasks 109-116 marked `[x]`
- This change archived under its archive date