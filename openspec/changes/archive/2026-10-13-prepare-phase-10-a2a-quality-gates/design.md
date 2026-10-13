# Design — prepare-phase-10-a2a-quality-gates

## Scope

This change specifies Phase 10 behaviour only. It ships zero
production code under `pi_platform/`. The following
`implement-phase-10-a2a-quality-gates` change implements these deltas.

## Affected architecture

```text
                                  External Agent / A2A peer
                                            │
                                            │ A2A JSON-RPC over HTTP(S)
                                            │ or stdio JSON-lines
                                            ↓
                 pi_platform/adapters/a2a/{http_transport,stdio_transport,envelope}.py
                                            │ A2A-envelope DTO only
                                            ↓
                          pi_platform/core/a2a/a2a_adapter.py
                                            │ ports only
                                            ↓
     ports/a2a/{A2aAdapterPort, AgentCardPort, ReverseDelegationPort, ExternalAgentPort}
                                            │
                                            ↓
   ports/orchestration · ports/control · ports/security · ports/retrieval
                                            │
                                            ↓
              Existing canonical + runtime + control plane

Reverse direction (§51):

   Orchestrator → ReverseDelegationPort → ExternalAgentPort
                                            │
                                  Adapters agent_integration/
                                            │ official CLI/API/A2A of target
                                            ↓
              External Strong Agent (Claude Code · Codex · OpenCode · Hermes · …)
```

A2A is **complementary** to MCP (§36) and REST (§44.3). A2A exposes
the platform as a peer agent; MCP exposes tools and context; REST
exposes the human UI surface. None replaces the others.

## Adapter isolation invariant

The architectural split from §50 is enforced by:

- `core/` never imports `adapters/a2a/*` or any A2A protocol library;
- A2A protocol versions live behind a single `A2aAdapterPort` whose
  value-types only expose domain concepts (`A2aTask`, `A2aArtifact`,
  `A2aMessage`, `A2aPart`, `AgentCard`) shaped by the platform's own
  domain model, never by the wire protocol;
- the adapter-to-port translation is the only place where wire types
  (JSON-RPC, JSON-lines, content types, streaming flags, auth
  envelopes) are interpreted;
- a future A2A spec revision replaces the adapter, not the core and
  not the spec.

## Reverse delegation (plan task 118, §51)

`platform.core.orchestrator.QueryOrchestrator` (Phase 5) already
decides L0/L1/L2 escalation deterministically. Phase 10 adds:

- `ReverseDelegationPort` (in `ports/a2a/`) — the orchestrator hands
  the L2 escalation decision (and its bounded context) to a port whose
  implementation in `core/a2a/reverse_delegation.py` chooses between
  the available `ExternalAgentPort` instances;
- `ExternalAgentPort` (in `ports/a2a/`) — one implementation per
  supported external agent (Claude Code, Codex, OpenCode, Hermes,
  generic MCP, generic A2A);
- selection is **deterministic policy** (`ReverseDelegationPolicy`)
  driven by the central policy engine — no small LLM in the loop;
- the LLM token budget for the chosen agent is enforced by the
  Context Assembler (`platform.context`); what crosses the boundary
  is a `ReverseDelegationTask` whose `taskContext` references the
  bounded TaskContext from Phase 5 task 81, never raw repository
  state.

## A2A capability handshake

The Phase 5 capability discovery descriptor from §47 is extended with:

```yaml
protocols:
  mcp: { version: "1.3.0" }
  a2a: { enabled: <bool>, version: "<tracked>", endpoint: "<loopback-or-pinned>" }
reverseDelegation: { enabled: <bool>, supportedAgents: [ "<name>" … ] }
```

The A2A version field is bound to a tracked, machine-readable
constant in `pi_platform.core.a2a.spec_version`. When the wire
version on the incoming side disagrees, the adapter rejects the
handshake with `version-incompatible` exactly as MCP does in Phase 6
task 88.

## Reverse delegation policy shape

```text
Decision inputs
  identity · role · requested operation · resource
  project/version context · egress decision
        ↓
ReverseDelegationPolicy
        ↓
SELECT_AGENT(<agentId>) | DENY | REQUIRE_APPROVAL
```

A coding agent that lacks the `agent.delegate` capability receives
`DENY`. An operator approval may upgrade `REQUIRE_APPROVAL` to
`SELECT_AGENT`. Egress classification is consulted before
`SELECT_AGENT` is returned — a `network.external = deny` blocks the
outbound call. Every decision writes one audit record with the same
shape as the Phase 7 audit log.

## Protocol surface

Phase 10 ships the minimum A2A surface required by §50 and §51 — no
streaming beyond what the protocol mandates, no agent-card extensions
beyond what the bundled profile needs:

| Wire | Adapter module | Direction | Failure mode |
|---|---|---|---|
| HTTP POST JSON-RPC `invoke` | `adapters/a2a/http_transport.py` | inbound to platform | 400 unknown method, 403 policy, 410 version-incompatible |
| HTTP POST JSON-RPC `tasks/send` (A2A `tasks/send`) | `adapters/a2a/http_transport.py` | inbound to platform | 400, 403, 410, 503 if hydration incomplete |
| HTTP GET `/.well-known/agent-card.json` | `adapters/a2a/http_transport.py` | outbound | served when flag enabled, 404 otherwise |
| A2A delegate `tasks/send` to external agent | `adapters/agent_integration/a2a_delegate.py` | outbound | retry then policy-defined fallback |

Streaming and `tasks/sendSubscribe` are explicitly out of scope — the
spec records a `streaming: not-supported` capability entry until the
implementation grows them. The collected protocols catalog keeps a
single ADR-style comment field in the capability descriptor explaining
the deferral.

## Quality gates topology

```text
tests/
├── test_phase_10_a2a.py                 # 117/118
│   ├── AgentCardPublishedScenario
│   ├── InboundA2aTasksScenario
│   ├── ReverseDelegationScenario
│   ├── A2aAdapterVersionMismatchScenario
│   └── CapabilityDescriptorAdvertisesA2aScenario
├── test_phase_10_quality_gates.py       # 119
│   ├── RetrievalFirstComplianceScenario
│   ├── VersionMismatchScenario
│   ├── StaleAndConflictScenario
│   ├── SecurityFilterScenario
│   ├── RoundTripScenario
│   ├── OkfConformanceScenario
│   ├── BranchSwitchScenario
│   └── TokenContextCostScenario
├── test_phase_10_invariants.py          # 120
│   └── one @invariant_<n> scenario per §68 invariant (52)
└── test_phase_10_schema_migration.py    # 121
    └── SchemaVersionMismatchScenario
```

Each scenario references the OpenSpec requirement it asserts (with
its stable `MUST`/`SHALL` clause) so the harness `openspec-check`
matrix stays useful.

## Metrics surface (plan 119)

`pi_platform/core/eval/metrics.py` exposes a structured metrics
descriptor that the integration-quality-gates suites collect and the
CI gate writes into `tmp/local/project-context/eval/last.json`:

```json
{
  "schema": "phase-10-eval/1",
  "scope": "<change-id>",
  "timestamp": "...",
  "metrics": {
    "retrieval.recall@k":     <float>,
    "retrieval.precision@k":  <float>,
    "reranker.quality":       <float>,
    "context.bytes":          <int>,
    "context.tokensIn":       <int>,
    "context.tokensOut":      <int>,
    "llm.external.tokens":   <int>,
    "latency.retrieve.p95Ms":<int>,
    "latency.delegate.p95Ms":<int>,
    "cache.reuseRate":       <float>,
    "branchSwitch.hydrationMs":<int>,
    "stale.detectionRate":   <float>,
    "plugin.setupSuccessRate":<float>
  }
}
```

Phase 10 ships the metric collectors (deterministic in-process
counters + timers around the existing ports). Threshold gates
(`--gate-threshold`, default `0.95` for recall, `0.0` for token-cost
delta) are introduced by the CI wiring, not by the metric collectors
themselves. Thresholds are operator policy, not domain logic.

## Schema-version migration guard (plan 121)

`pi_platform.core.sync.hydrate` already errors on missing
manifests. Phase 10 extends the guard for the seven `Phase 11 §11`
identity tuple fields:

- `repositoryIdentity` — required; absent → `IdentityInvalid`;
- `gitHead` — required; absent or unsigned → `IdentityInvalid`;
- `knowledgeSchemaVersion` — required; mismatch against the running
  runtime-schema version → `MigrationRequired` (with the documented
  migration path) or `Incompatible` when no path exists;
- `embeddingModelVersion` — same rule; recorded alongside the
  outdated cache signature so hydration refuses silent re-use;
- `indexSchemaVersion` — same rule for sparse/dense/graph indexes;
- `workingTreeFingerprint` — captured live; mismatch is a warning, not
  an error, but is recorded on the audit log;
- `manifestContentHashes` — content addressed; mismatch is a
  transport corruption error, never silent.

## Security composition (inherited from Phase 8 + Phase 7)

Every A2A inbound request and every reverse-delegation outbound
request passes the same gates as the Phase 9 REST surface:

1. **Authentication** — bearer token (or peer JWT) when configured.
2. **Authorisation** — central policy engine. Actions
   `a2a.invoke`, `a2a.delegate`, `reverse.delegate`. Unknown
   actions default to `DENY`.
3. **Capability gates** — `a2a.invoke` requires the
   `mcp.invoke` or equivalent capability; `reverse.delegate`
   requires `agent.delegate`.
4. **Egress** — every outbound delegation consults the egress
   classifier; an egress `DENY` blocks the call.
5. **Audit** — every inbound and outbound decision writes one
   audit record with the same Phase 7 shape (no secrets, no source
   contents).
6. **Redaction** — outgoing delegation contexts are run through the
   Phase 8 `RedactionPipeline` before they cross the boundary.

The composition is fail-closed in every branch.

## Deployment topology

Phase 10 keeps the Phase 9 single-container default. The A2A HTTP
transport binds to the same loopback port as REST when the
`a2a-adapter` feature flag is enabled, and is absent when the flag is
disabled. The A2A stdio transport is a separate process and is
started only by an operator that has enabled both `a2a-adapter` and
`a2a-stdio-transport`. No daemon process is added to the default
container boot.

| Profile | A2A inbound | A2A outbound |
|---|---|---|
| `core-headless` | disabled | disabled |
| `desktop-lite` | loopback only (when enabled) | disabled by default |
| `desktop-local-ai` | loopback only | enabled only if at least one `ExternalAgentPort` is configured |
| `open-webui` | loopback only | enabled only if configured |
| `enterprise` | loopback by default; operator-configurable | network.egress allows it |

## Compatibility

- No existing capability is retired.
- The three new specs are the only contract changes.
- No new Python dependency is permitted by this change or its
  implementation. A2A implementation stays on the Python stdlib for
  HTTP and JSON. If a future A2A spec revision mandates a parsing
  library that stdlib cannot express, the choice becomes an ADR with
  an SPDX entry and a license-gate verdict before adoption.
- `McpServer` keeps its current contract (Phase 6) and is not
  extended by Phase 10.
- `RestApi` keeps its current contract (Phase 9); the A2A
  capability is added to the `indexing-status` and
  `knowledge-status` payloads only.

## Risks

| Risk | Mitigation |
|---|---|
| A2A surface becomes an alternate authorisation bypass | Capability `a2a.invoke` required; policy action defaults to DENY; negative test asserts unknown action refused |
| Reverse delegation silently egresses to untrusted endpoints | Egress classifier is consulted before `SELECT_AGENT`; negative test asserts `DENY` blocks outbound call |
| Streaming or agent-card extensions leak partial implementations into the core | Spec explicitly records `streaming: not-supported` for v1.0; ADR-style comment field tracks future extensions |
| A2A wire version drift breaks handshake with newer agents | Tracked constant `A2A_SPEC_VERSION`; capability descriptor advertises supported range; `version-incompatible` error |
| Quality-gates suites slow CI | Suites run against in-process fixtures; container/network parts are still gated by environment flag |
| Metrics drift between local and CI runs | Metrics file uses a single deterministic schema `phase-10-eval/1`; threshold gates live in CI, not in collectors |
| Schema-version migration guard breaks existing branch switches | All `MUST` clauses are scoped to "from now on" — Phase 1-9 suites stay green; migration test is additive |
| Adapter A2A library change drags in license-cost library | Stdlib-only implementation for v1.0; ADR documents this as a deliberate deviation if a library is later adopted |
| External-agent adapters leak vendor specifics into the core | One `ExternalAgentPort` per supported agent; orchestrator selects by capability identity, never by name |

## Alternatives rejected

- **Implement A2A before the spec is published** — §50 requires
  tracking a stable A2A spec. Phase 10 records the supported version
  explicitly and pins it via the capability descriptor.
- **Stream A2A responses** — not in v1.0; streaming is an explicit
  Phase 10+ follow-up gated behind an ADR and the supply-chain
  security gate.
- **Make reverse delegation default-on** — §51 makes it an
  *optional* capability; default-off matches §5.5 fail-closed
  discipline.
- **Bake the §68 acceptance suite into `harness.py check`** —
  separation of concerns: `harness.py check` keeps its current scope
  (config/session/Wiki/OpenSpec manifest); Phase 10 adds an opt-in
  `make invariants` target that calls `python -m unittest
  tests.test_phase_10_invariants` and emits the structured metrics
  file. Run both together for release evidence.
- **Ship a database migration tool for schema version bumps** —
  out of scope for v1.0; Phase 10 records the migration path text
  only and refuses silent hydration.
