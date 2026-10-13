# Tasks — prepare-phase-10-a2a-quality-gates

This change ships the three Phase 10 capability specs and zero
production code under `pi_platform/`. The specification deltas under
[`specs/`](specs) are the authoritative behavioural contract.

The future
[`implement-phase-10-a2a-quality-gates`](../implement-phase-10-a2a-quality-gates/tasks.md)
change implements and verifies them before adoption.

Plan tasks 117-123 in
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md)
remain unchecked until the implementation change completes.

## Preparation tasks

- [x] P1. Author `proposal.md` naming the three affected capabilities
      and the explicit non-goals (A2A core domain isolation,
      reverse-delegation default-off, integration-quality-gates
      suite, §68 acceptance suite, schema-version migration guard,
      v1.0 release evidence).
- [x] P2. Author `specs/2026-10-12-a2a-adapter/spec.md` covering the
      adapter-isolation invariant, the supported A2A spec version
      pin, the `A2aAdapterPort` and `AgentCardPort` contracts, the
      HTTP/stdio transport pair, the capability handshake, the
      error model, the failure modes, the no-domain-leak invariant
      and the feature flag matrix.
- [x] P3. Author
      `specs/2026-10-12-external-coding-agent-integration/spec.md`
      covering the reverse-delegation deterministic policy,
      `ReverseDelegationPort` and `ExternalAgentPort`, the egress
      composition, the audit shape, the supported external agents
      (Claude Code, Codex, OpenCode, Hermes, generic MCP, generic
      A2A), the opt-in default, the failure modes and the no-vendor-
      leaks-into-core invariant.
- [x] P4. Author
      `specs/2026-10-12-integration-quality-gates/spec.md` covering
      the eight evaluation suites (retrieval-first compliance, MCP
      tool-selection, version-mismatch, stale/conflict handling,
      security-filter, plugin install/uninstall smoke, OKF materialise
      conformance, round-trip, branch-switch, token/context cost),
      the 52-invariant §68 acceptance suite, the schema-version
      migration guard, the deterministic metric schema
      `phase-10-eval/1`, the CI wiring (`make eval`,
      `make invariants`) and the failure-policy rules.
- [x] P5. Author `design.md` recording the affected architecture,
      the adapter isolation invariant, the reverse-delegation flow,
      the capability handshake, the protocol surface, the metrics
      topology, the schema-migration guard, the security composition,
      the deployment topology, the compatibility rules, the risks
      and the rejected alternatives.
- [x] P6. Author `context-impact.md` naming the knowledge nodes, the
      ADRs, the implementation areas, the invariants that must not
      break and the close-out gates.
- [x] P7. Author the mirrored
      `implement-phase-10-a2a-quality-gates` change with the
      implementation and verification checklist (one Block per plan
      task).
- [x] P8. Validate: `python harness.py openspec-check` and
      `openspec validate --all --strict` PASS with zero production
      code added under `pi_platform/`.

## Implementation tasks (owned by the next change)

These mirror plan tasks 117-123 and are executed by
`implement-phase-10-a2a-quality-gates`:

- 117 A2A adapter (`A2aAdapter`, `AgentCardPort`, transport pair, capability handshake)
- 118 Reverse delegation (`ReverseDelegationPort`, `ExternalAgentPort`, deterministic policy)
- 119 Integration quality-gates suites
- 120 §68 acceptance suite (52 invariants)
- 121 Schema-version migration guard
- 122 Wiki / ADR / `openspec/CURRENT.md` updates
- 123 Archive both changes; produce the v1.0 release evidence
  (image tag, OCI artefact, distribution bundles)

## Close-out gate for the implementation change

- All three capability specs adopted under
  `openspec/specs/2026-10-12-*/` and listed exactly once in
  `openspec/CURRENT.md`
- `tests/test_phase_10_*` green; full offline suite still green
- `python harness.py check` PASS; `openspec validate --all --strict` PASS
- Plan tasks 117-123 marked `[x]`
- `invariants/v0.8.md` exists and links resolve
- This change archived under its archive date
- The mirrored implementation change archived under its archive date
- Container image, OCI artefact and distribution bundles recorded
