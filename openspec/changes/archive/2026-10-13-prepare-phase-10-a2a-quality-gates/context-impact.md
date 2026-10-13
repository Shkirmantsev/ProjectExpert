# Context impact — prepare-phase-10-a2a-quality-gates

## Knowledge nodes to create (during implementation)

| Node | Content |
|---|---|
| `.ai/wiki/modules/a2a.md` | Adapter, ports, reverse delegation, capability descriptor, deployment topology |
| `.ai/wiki/modules/eval.md` | Quality-gates suites, §68 invariants suite, schema-migration guard, metrics surface |
| `.ai/wiki/interfaces/a2a.md` | A2A wire surface (version pinned), `AgentCard`, `A2aTask`, A2A capability handshake, errors |
| `.ai/wiki/interfaces/reverse-delegation.md` | Reverse-delegation port, `ExternalAgentPort`, deterministic selection policy, egress composition |
| `.ai/wiki/invariants/v0.8.md` | 52 §68 invariants with one probe each; each entry links to the Phase 10 scenario |
| `.ai/wiki/project/distribution-vendors.md` | v1.0 close-out additions: A2A feature-flag matrix, profiles updated |

The implementation change updates `.ai/wiki/INDEX.md` with each new
node. `.ai/wiki/invariants/INDEX.md` (new) gains a back-link to
`architecture/system-overview.md`.

## Knowledge nodes to update

| Node | Update |
|---|---|
| `.ai/wiki/architecture/system-overview.md` | Mark `status: active`; add A2A + Quality Gates paragraphs (data plane ↔ control plane integration unchanged) |
| `.ai/wiki/architecture/platform-overview.md` | Mark `status: active`; A2A reverse delegation enters the data-plane view; quality-gates suites under the control-plane observability theme |
| `.ai/wiki/project/implementation-roadmap.md` | Phase 10 status; link to `invariants/v0.8.md` |
| `.ai/wiki/glossary/platform.md` | Add: `A2A Adapter`, `Agent Card`, `Reverse Delegation`, `External Agent`, `Version Migration Guard`, `Integration Quality Gate`, `Metric Schema` |
| `.ai/wiki/interfaces/capability-discovery.md` | Add the `protocols.a2a` and `reverseDelegation` fields to the descriptor template |
| `.ai/wiki/adr/0021-a2a-adapter-isolation.md` | A2A adapter isolation from the core domain |
| `.ai/wiki/adr/0022-reverse-delegation-default-off.md` | Reverse delegation is opt-in by default |
| `.ai/wiki/adr/0023-stdlib-only-a2a-transport.md` | A2A transport stays on the Python stdlib for v1.0 |
| `README.md` | Phase 10 status once shipped |
| `docs/README.md` | A2A + quality-gates documentation links |
| `docs/PROJECT_STRUCTURE.md` | `pi_platform/ports/a2a`, `pi_platform/core/a2a`, `pi_platform/adapters/a2a`, `pi_platform/core/eval`, `tests/test_phase_10_*` |

## ADRs to create

| ADR | Decision |
|---|---|
| 0021 | A2A adapter isolation from the core domain model — wire types stay in `adapters/a2a/`, port types live in `ports/a2a/`, core imports no wire library |
| 0022 | Reverse delegation is opt-in by default — feature-flagged under `reverse-delegation`, available only when an `ExternalAgentPort` is configured and the egress policy allows it |
| 0023 | A2A transport is implemented on the Python stdlib only for v1.0 — no new dependency; future library adoption requires an ADR + license-gate verdict |

These ADRs are required because each one introduces a non-default
choice: bypassing them silently would weaken the architectural
invariants in §68.

## Implementation areas

- New `pi_platform/ports/a2a/`
- New `pi_platform/core/a2a/`
- New `pi_platform/adapters/a2a/`
- New `pi_platform/core/eval/` (metrics + scenarios + invariant probes + schema-migration guard helpers)
- New `tests/test_phase_10_a2a.py`, `tests/test_phase_10_quality_gates.py`,
  `tests/test_phase_10_invariants.py`, `tests/test_phase_10_schema_migration.py`,
  `tests/fixtures/phase_10/` (synthetic project with deliberate
  conflicts, stale entries, version-mismatch payload)
- Changed `pi_platform/core/orchestration/capability_discovery.py`
  (advertise the `a2a`/`reverseDelegation` fields)
- Changed `pi_platform/cli/main.py` (add `a2a` flag/disable, add
  `eval` and `invariants` subcommands)
- Changed `Makefile` — add `make eval`, `make invariants`, `make
  metrics-gate`
- Possibly updated `Containerfile` — record the A2A port as a
  documented, gated capability

## Invariants that must not break (from §68)

- §68.1-2 — Git remains the source of truth; A2A does not introduce a second knowledge store.
- §68.5-8 — Content addressing, manifest hashing, version stamping stay deterministic.
- §68.16-18 — Hybrid retrieval, hierarchical context, retrieval-first escalation order.
- §68.20 — Orchestrator owns escalation; reverse delegation is selected deterministically, not by an LLM.
- §68.22-23 — MCP and A2A remain complementary; A2A is not a substitute for MCP.
- §68.26, §68.47-50 — every A2A boundary passes the egress, policy, audit and redaction gates.
- §68.35 — A2A transport does not introduce a vendor-mandatory dependency.
- §68.36-41 — agent skill/plugin contract remains unchanged; Phase 10 quality gates assert skill/plugin lifecycle, not a redesign.
- §68.45-52 — control-plane primitives unchanged; the A2A adapter participates as one more adapter, not as an alternate authorisation path.

The Phase 10 implementation change ships the `invariants/v0.8.md`
node and the probe suite; the wiki node is the human-readable map,
the probe suite is the executable evidence.

## Verification surface

- `python -m unittest tests.test_phase_10_a2a`
- `python -m unittest tests.test_phase_10_quality_gates`
- `python -m unittest tests.test_phase_10_invariants`
- `python -m unittest tests.test_phase_10_schema_migration`
- `make eval` (collects metrics, writes `tmp/local/project-context/eval/last.json`)
- `make invariants` (same metric file, all 52 probes must pass)
- Full offline suite remains green (672 tests before Phase 10; Phase
  10 is additive)
- `python harness.py check` PASS
- `openspec validate --all --strict` PASS

## Close-out gates for the implementation change

- All three capability specs adopted under
  `openspec/specs/2026-10-12-*/` and listed exactly once in
  `openspec/CURRENT.md`
- `tests/test_phase_10_*` green; the full offline suite still green
- `python harness.py check` PASS; `openspec validate --all --strict`
  PASS
- Plan tasks 117-123 marked `[x]`
- `invariants/v0.8.md` exists and links resolve
- `docs/README.md` and `README.md` reflect the v1.0 close-out
- Container image is built and tagged; OCI artefact and distribution
  bundles recorded (operators run the actual `docker/podman build`
  step using the existing `Containerfile` and `docker-compose.yml`)
- This change archived under its archive date
- The mirrored `implement-phase-10-a2a-quality-gates` change archived
  under its archive date
