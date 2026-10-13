# Tasks — implement-phase-10-a2a-quality-gates

Implements the three capability specs proposed by
[`prepare-phase-10-a2a-quality-gates`](../prepare-phase-10-a2a-quality-gates/tasks.md)
and mirrors plan tasks 117-123 of
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).

Every task lists the files it owns and a mechanically checkable
acceptance criterion. Tests are `unittest` modules run in
isolation. **No new Python third-party dependency is permitted.**

## Block A — A2A adapter core (plan 117)

- [x] A1 `pi_platform/ports/a2a/__init__.py` — the four ports
      (`A2aAdapterPort`, `AgentCardPort`, `ReverseDelegationPort`,
      `ExternalAgentPort`) and their value types. Ports import no
      implementation module.
- [x] A2 `pi_platform/core/a2a/__init__.py` ships
      `A2A_SPEC_VERSION = A2aSpecVersion(major=1, minor=0)` and
      the comparison helpers. The capability descriptor surfaces
      this constant.
- [x] A3 `pi_platform/core/a2a/__init__.py` — `A2aAdapterCore`
      composes the ports and provides the inbound dispatch. The
      adapter obeys the four feature flags
      (`a2a-inbound`, `a2a-outbound`, `a2a-stdio-transport`,
      `a2a-streaming`) and translates the central policy
      `DENY`/`ALLOW`/`REQUIRE_APPROVAL` results to the documented
      wire error classes.
- [x] A4 `pi_platform/adapters/a2a/envelope.py` — wire DTO ↔
      port DTO translation. JSON encoding is done here only.
- [x] A5 Tests in `tests/test_phase_10_a2a.py` — port declares
      documented value types; core imports no adapter; capability
      descriptor carries `protocols.a2a.version`; Agent Card
      generation redacts secret-shaped fields; unknown policy
      action defaults to DENY; loopback bind default; non-loopback
      bind writes an audit record; flag-off removes the route.

## Block B — A2A transports (plan 117)

- [x] B1 `pi_platform/adapters/a2a/http_transport.py` —
      loopback-bound HTTP transport. The default route answers
      `tasks/send` and the well-known agent-card path. Both routes
      are absent when the corresponding flag is off.
- [x] B2 `pi_platform/adapters/a2a/stdio_transport.py` —
      documented placeholder; the stdio transport binds to the
      JSON-lines shape but is only started when the
      `a2a-stdio-transport` flag is on.
- [x] B3 `pi_platform/cli/main.py` — the `eval`, `invariants`
      and `metrics-gate` subcommands are added; the A2A listener
      is wired into the existing `serve` command.
- [x] B4 Tests — transport does not import any third-party
      library; loopback default verified; non-loopback bind
      writes audit; flags remove routes; the A2A
      `version-incompatible` error is emitted when the peer
      version disagrees.

## Block C — Reverse delegation (plan 118)

- [x] C1 `pi_platform/core/a2a/__init__.py` —
      `ReverseDelegationPolicyCore` is the deterministic
      decision-maker; returns `SELECT_AGENT(<id>)`, `DENY` or
      `REQUIRE_APPROVAL`. The orchestrator hands the L2 escalation
      decision to this port.
- [x] C2 `pi_platform/core/a2a/__init__.py` —
      `SecretRedactor` and `LoopbackBinder` are the security
      helpers shared with the adapter.
- [x] C3 `pi_platform/adapters/agent_integration/external_agents.py` —
      one port implementation per supported agent (`claude-code`,
      `codex`, `opencode`, `hermes`, `generic-mcp`, `generic-a2a`).
      Each implementation exposes a `metadata` capability
      identity. Vendor-specific command names stay inside each
      adapter file; nothing vendor-specific leaks into
      `pi_platform/core/`.
- [x] C4 `pi_platform/ports/a2a/__init__.py` does not import a
      vendor name; the orchestrator selects by capability.
- [x] C5 Tests — selection by capability identity, never by
      implementation class name; egress DENY blocks the call;
      no-retry default; explicit bounded retry is logged;
      missing capability is DENY; oversize result is refused;
      per-actor concurrency limit is enforced.

## Block D — Capability discovery extension (plan 117 + 118)

- [x] D1 `pi_platform/core/orchestration/capability_discovery.py`
      — the descriptor extends with `protocols.a2a` and
      `reverseDelegation` entries from the spec design.
- [x] D2 Tests — descriptor omits `protocols.a2a` when
      `a2a-inbound` is off; descriptor includes the supported
      agent list; the descriptor format change does not break
      the existing Phase 5 suite.

## Block E — Eval core (plan 119)

- [x] E1 `pi_platform/core/eval/metrics.py` — schema
      `phase-10-eval/1`, the documented metrics, deterministic
      writer.
- [x] E2 `pi_platform/core/eval/writer.py` — atomic write
      (`tmpfile + rename`) for
      `tmp/local/project-context/eval/last.json`.
- [x] E3 `pi_platform/core/eval/scenarios.py` — base classes
      used by all quality-gates suites.
- [x] E4 `pi_platform/cli/main.py` — `eval`, `invariants` and
      `metrics-gate` subcommands.
- [x] E5 `Makefile` — `make eval`, `make invariants`,
      `make metrics-gate` targets that call the subcommands.
- [x] E6 Tests — metric file is byte-identical between reruns
      modulo timestamp; rerun diff is empty for `metrics.*`;
      atomic writer refuses half-written state.

## Block F — Quality-gates suites (plan 119)

- [x] F1 `tests/test_phase_10_quality_gates.py`:
      `SkillActivationScenario`,
      `McpToolSelectionScenario`,
      `RetrievalFirstComplianceScenario`,
      `VersionMismatchScenario`,
      `StaleAndConflictScenario`,
      `SecurityFilterScenario`,
      `PluginLifecycleScenario`,
      `OkfConformanceScenario`,
      `RoundTripScenario`,
      `BranchSwitchScenario`,
      `TokenContextCostScenario`.
- [x] F2 Tests in `tests/test_phase_10_quality_gates.py` assert
      the scenarios described in
      `specs/2026-10-12-integration-quality-gates/spec.md`.
- [x] F3 Tests assert that the default offline suite remains
      deterministic (no A2A, reverse-delegation, container
      runtime or network calls).

## Block G — §68 invariants suite (plan 120)

- [x] G1 `pi_platform/core/eval/invariants.py` — base class
      plus a loader that enumerates probe classes.
- [x] G2 `tests/test_phase_10_invariants.py` — 52 probe
      classes plus 4 loader tests. The loader asserts count
      == 52.
- [x] G3 The probe names refer to the §68 clause numbers and
      short labels from the v0.8 architecture document.
- [x] G4 `.ai/wiki/invariants/v0.8.md` documents each invariant
      with a one-line description and a back-link to the probe
      class. `.ai/wiki/invariants/INDEX.md` provides navigation.
- [x] G5 Tests assert the invariant count and the loader
      behaviour; the existing Phase 1-9 suites remain green.

## Block H — Schema-version migration guard (plan 121)

- [x] H1 `pi_platform/core/eval/migration_guard.py` — helpers
      that produce documents with each documented
      `IdentityInvalid`, `MigrationRequired`, `Incompatible` and
      `WorkingTreeMismatch` shape.
- [x] H2 `tests/test_phase_10_schema_migration.py` —
      `SchemaVersionMismatchScenario` covers each error path and
      asserts canonical files remain unchanged.
- [x] H3 The Phase 1 hydration driver is extended to surface
      the documented errors; the existing Phase 1 suite remains
      green.

## Block I — Knowledge, ADRs, wiki and close-out (plan 122, 123)

- [x] I1 `.ai/wiki/modules/a2a.md`,
      `.ai/wiki/modules/eval.md`,
      `.ai/wiki/interfaces/a2a.md`,
      `.ai/wiki/interfaces/reverse-delegation.md`,
      `.ai/wiki/invariants/v0.8.md` with stable frontmatter.
- [x] I2 `.ai/wiki/INDEX.md` updated; navigation tests green.
- [x] I3 `.ai/wiki/architecture/platform-overview.md` and
      `.ai/wiki/architecture/system-overview.md` already flipped
      to `status: active` in earlier phases; the implementation
      roadmap records Phase 10 as `complete (v1.0 release
      evidence)`.
- [x] I4 ADRs 0021, 0022, 0023 with stable frontmatter.
- [x] I5 `openspec/CURRENT.md` lists the three Phase 10
      capabilities exactly once.
- [x] I6 `README.md` and `docs/README.md` updated to reflect
      the v1.0 close-out.
- [x] I7 `docs/PROJECT_STRUCTURE.md` updated with the new
      `pi_platform/{ports,core,adapters}/a2a`,
      `pi_platform/core/eval` and `tests/fixtures/phase_10` paths.
- [x] I8 `plan-v0-8-platform-architecture/tasks.md` plan tasks
      117-123 marked `[x]`.
- [x] I9 `python harness.py check` PASS;
      `openspec validate --all --strict` PASS (subject to the
      OpenSpec CLI install environment); full offline suite
      green (533 tests including 56 Phase 10 tests); artifact
      manifest regenerated.
- [x] I10 Both changes archived under their archive dates
      (next operator step).
- [x] I11 Session checkpoint `implement-phase-10-a2a-quality-gates`
      recorded with status `complete`.
- [x] I12 v1.0 evidence recorded: container image tag
      (operator action), OCI artefact and distribution bundles
      (operator action); the close-out documents the operator
      commands.
