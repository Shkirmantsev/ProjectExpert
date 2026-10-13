---
id: interfaces-reverse-delegation
kind: interface
title: Reverse Delegation interface
status: active
pi_phase: 10
pi_section: "§51"
pi_capability: external-coding-agent-integration
---

# Reverse Delegation interface

The reverse delegation interface is the outbound port used by the
Phase 10 orchestrator to escalate Level 2 tasks to a strong external
coding agent through its officially supported interface.

## Decision contract

`pi_platform.ports.a2a.ReverseDelegationPort.evaluate` returns a
`ReverseDelegationEvaluation` with one of three decisions:

- `SELECT_AGENT(<identity>)`
- `DENY`
- `REQUIRE_APPROVAL`

The policy is **deterministic**: it never calls a language model.
The decision is computed from:

1. the actor identity and requested operation;
2. the actor's capability set (`agent.delegate` is required);
3. the egress decision for the resolved destination;
4. the configured `ExternalAgentMetadata` candidates.

Ambiguous matches return `REQUIRE_APPROVAL`. Egress `DENY`
short-circuits to `DENY` regardless of capability state.

## Bounded TaskContext

A `ReverseDelegationTask` carries only the Phase 5 `TaskContext`
fields; raw repository state, runtime internals or any field not
exposed by the documented value type are never sent. The receiving
agent receives a `ReverseDelegationResult` whose status is
`completed`, `failed`, `unsupported`, or a documented transient.

## External agent identities

Phase 10 ships one `ExternalAgentPort` per documented identity:

- `claude-code` (CLI, Apache-2.0)
- `codex` (API, Apache-2.0)
- `opencode` (CLI, MIT)
- `hermes` (API stub, Apache-2.0)
- `generic-mcp` (MCP, Apache-2.0)
- `generic-a2a` (A2A, Apache-2.0)

The orchestrator selects by `ExternalAgentMetadata.identity`, never
by class name. Adding a new identity is additive and requires an
ADR-style update.

## Concurrency, retry and oversize limits

- per-actor in-flight delegations are bounded (default 4);
- the response payload byte cap is enforced (default 16 MiB);
- the default retry policy is **no retry**; an explicit, bounded
  retry policy must be operator-configured and is logged per
  attempt.

## Security composition

Reverse delegation inherits the Phase 8 enterprise security
boundary:

1. **Authentication** — operator credential (or approved
   automation token).
2. **Authorisation** — `agent.delegate` capability is mandatory.
3. **Egress** — egress classifier is consulted before
   `SELECT_AGENT`; egress DENY blocks the call.
4. **Audit** — every decision writes one audit record.
5. **Redaction** — the outgoing context is redacted through the
   `RedactionPipeline`.

## Related

- `kb://modules.a2a`
- `kb://modules.eval`
- `kb://interfaces.a2a`
- `kb://adr.0022-reverse-delegation-default-off`
- `openspec/specs/2026-10-12-external-coding-agent-integration/spec.md`
