# Proposal — Prepare the v0.8 Phase 10 A2A and Quality Gates Capability Specs

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
divides agent interoperability into two interfaces: MCP for tools and
context (§36), A2A for agent-to-agent task collaboration (§50). §51
defines the symmetric reverse direction — the platform initiating
communication with external strong agents through their officially
supported interfaces (Claude Code, Codex, OpenCode, Hermes, A2A-compatible
agents, future enterprise agents).

§49 requires an integration quality-gate layer to verify, on every
release, that integrated agents actually follow the retrieval-first
policy, respect version/security filters, cite provenance, and avoid
unauthorised materialisation. §49 also enumerates a baseline metric
suite (retrieval recall/precision, reranker quality, context size,
external LLM token consumption, latency, cache reuse, branch-switch
hydration time, stale-knowledge detection, plugin setup success rate).

The v0.8 §68 lists 52 architectural invariants that must hold across
all phases. Phases 1-9 delivered the components but did not yet ship a
machine-checkable acceptance suite that exercises every invariant end
to end.

Phases 1-9 shipped canonical/runtime split, ingestion, storage,
retrieval, orchestration, MCP + skill distribution, the control plane,
the enterprise security boundary, the human UI, the OKF distribution
gate and the launchers. None of those phases addresses §49, §50, §51
or any cross-phase invariant check for the v0.8 §68 list. Without
Phase 10 the platform has:

- no A2A adapter — agents cannot collaborate with the platform in
  agent-card driven flows;
- no reverse delegation — the platform cannot escalate to a strong
  external agent under the orchestrator's deterministic policy;
- no machine-checkable acceptance suite proving the 52 invariants;
- no schema-version migration guard that proves the platform refuses
  to silently lose or corrupt canonical knowledge when the
  `knowledgeSchemaVersion`, `embeddingModelVersion` or
  `indexSchemaVersion` changes across branches;
- no v1.0 release evidence: a tagged container image + signed OCI
  artefact + bundled distribution assets.

## What changes

Three new capability specs are proposed. Nothing in this change is
implemented here; this change ships zero production code under
`pi_platform/`.

| Proposed capability | Parent plan task | Behavioural focus |
|---|---|---|
| `a2a-adapter` | 117 | Pluggable A2A transport, version-pinned adapter, ports-only core domain exposure, capability-gated handshake, fail-closed delegation |
| `external-coding-agent-integration` | 118 | Reverse delegation through the platform's official interfaces (A2A / supported CLI / supported API), capability-gated, deterministic orchestrator policy |
| `integration-quality-gates` | 119-121 | Regression suites for retrieval-first, version-mismatch, stale/conflict, plugin lifecycle, security filter, round-trip, OKF conformance, branch-switch, token/context cost. Final §68 acceptance suite. Schema-version migration guard |

The plan-v0-8 task 122 (Wiki update) and task 123 (archive + v1.0
release) are owned by the implementation change and the harness close-out
flow; they have no behavioural requirements of their own and therefore
need no separate specs.

## Affected capabilities

- Extends the accepted `capability-discovery` capability to advertise the
  A2A protocol surface and reverse-delegation feature through the same
  deterministic descriptor used by MCP and REST.
- Extends the accepted `agent-adapter-contract` requirement set to make
  external coding agents first-class targets — adapters for Claude Code,
  Codex, OpenCode and generic MCP+A2A agents live behind the same port
  family, not bespoke code paths.
- Extends the accepted `plugin-supply-chain-security` capability by
  requiring the integration-quality-gates suites to assert (a) the
  pinned versions, (b) the SPDX identifiers, (c) the
  compatibility-ranges check on every CI run.
- Extends the accepted `mcp-server`, `human-interface-web-ui` and
  `skill-distribution-plane` capabilities only by adding an
  interoperability statement: none of them is replaced by A2A; A2A is
  complementary and is exposed only when its capability flag is
  enabled.
- Adds no change to the accepted `enterprise-security-boundary`; the
  A2A surface inherits the same policy engine, audit log, secret
  redaction and egress classifier already enforced by Phase 8.
- Adds no change to the `control-plane` features (registry, hooks,
  capability tokens, approvals). The A2A adapter participates as one
  more plugin-adapter surface — never as an alternate authorisation
  bypass.

## Out of scope

- New Python third-party dependency.
- Any renegotiation of MCP, REST or skill distribution contracts.
- Bundling additional agent runtimes in the default container; A2A and
  reverse delegation are routed through already-installed adapters.
- Generalising A2A into a multi-protocol gateway. A2A is the
  agent-to-agent protocol; HTTP/REST stays the UI protocol; MCP stays
  the tooling protocol. Phase 10 introduces the adapter and the
  reverse-delegation port, not a generic protocol mux.

## Adoption model (resolves F15)

- **this change IS archivable now** because all acceptance criteria
  are planning artifacts (proposal, three specs, design,
  context-impact, tasks, Wiki/ADR updates) and the planning artifacts
  have been authored and validated by the harness gates without any
  production code added under `pi_platform/`;
- when this change is archived (via the standard OpenSpec archive
  workflow), the three Phase 10 spec deltas are promoted to accepted
  specs under `openspec/specs/2026-10-12-<capability>/`;
- the future `implement-phase-10-a2a-quality-gates` change depends on
  the three accepted Phase 10 specs being present in
  `openspec/specs/` and implements exactly the Phase 10 tasks (117-123)
  from `plan-v0-8-platform-architecture/tasks.md`;
- the implementation change ships a closed-out v1.0 release evidence
  (container image tag, OCI artefact, distribution bundles, harness
  `python harness.py check` PASS, `openspec validate --all --strict`
  PASS, full offline suite green).

## Impact

New capability specifications only. The following
`implement-phase-10-a2a-quality-gates` change will ship the A2A
transport adapter, the reverse-delegation port, the quality-gate
suites, the §68 acceptance suite, the schema-migration guard, the
final Wiki + ADR updates and the v1.0 close-out.
