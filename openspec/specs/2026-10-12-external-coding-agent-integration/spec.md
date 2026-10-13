# 2026-10-12-external-coding-agent-integration Specification

## Purpose
Enable operator-selected external coding agents through deterministic,
capability-based reverse delegation. Send only bounded TaskContext values
through supported agent interfaces, enforce approval and egress decisions, and
audit delegation without giving external agents direct access to runtime state.

## Requirements
### Requirement: Reverse delegation is opt-in by default

The `reverse-delegation` feature flag MUST default to disabled. When
disabled, no `ExternalAgentPort` is selected, no outbound delegation
runs and the orchestrator escalates within the on-platform L1 path.
Enabling reverse delegation MUST require an operator decision and
MUST be recorded in the audit log.

#### Scenario: reverse delegation is disabled by default

Given a fresh configuration
When the orchestrator is asked to handle a Level 2 task
Then it MUST NOT call any `ExternalAgentPort` and MUST escalate to
the on-platform L1 path or refuse.

#### Scenario: enabling reverse delegation writes an audit record

Given `reverse-delegation` is disabled
When an operator enables it
Then one audit record is written with
`operation = "reverse-delegation.enable"` before any delegation
runs.

### Requirement: Deterministic reverse-delegation policy

The orchestrator MUST select the external agent through a
deterministic policy (`ReverseDelegationPolicy`) that resolves an
identity, role, requested operation, project/version context, egress
decision and a list of configured `ExternalAgentPort` instances into
`SELECT_AGENT(<agentId>)`, `DENY` or `REQUIRE_APPROVAL`. The policy
MUST NOT call a language model or any non-deterministic source.
`SELECT_AGENT` MUST be followed by an egress decision before any
outbound call is made.

#### Scenario: ambiguous delegation is refused

Given multiple `ExternalAgentPort` instances are configured and the
policy resolves to more than one match
When the orchestrator runs the policy
Then it returns `REQUIRE_APPROVAL` and does not call any external
agent.

#### Scenario: egress DENY blocks the outbound call

Given the egress policy returns `DENY` for the resolved destination
When the policy reaches the egress check
Then it returns `DENY` regardless of capability state and writes one
audit record with `policyDecision = DENY`.

#### Scenario: missing capability returns DENY

Given the actor lacks the `agent.delegate` capability
When the policy runs
Then it returns `DENY` and does not invoke any external agent.

### Requirement: ExternalAgentPort is one implementation per supported agent

The platform MUST provide one `ExternalAgentPort` implementation per
supported external agent (Claude Code, Codex, OpenCode, Hermes,
generic MCP, generic A2A) under `pi_platform/adapters/agent_integration/`.
Implementations MUST wrap the agent's officially supported interface
(A2A, supported CLI, or supported API) and MUST NOT import or call
internal platform state directly. The orchestrator MUST select by
capability identity, not by vendor name.

#### Scenario: each supported agent has its own port implementation

Given the supported agent list
When the adapter registry is enumerated
Then a port implementation exists for every documented agent.

#### Scenario: selection is by capability identity

Given two `ExternalAgentPort` instances, A and B
When the orchestrator resolves `SELECT_AGENT`
Then the matching step uses the capability identity declared in the
port metadata, never the implementation class name.

### Requirement: Bounded TaskContext only crosses the boundary

The platform MUST construct a `ReverseDelegationTask` whose
`taskContext` is a `TaskContext` from the Phase 5 task 81 builder.
Raw repository state, runtime internals or any field not exposed by
the `TaskContext` value type MUST NOT be sent. The receiving agent
MUST NOT receive a writable handle to the runtime store.

#### Scenario: only TaskContext fields cross the boundary

Given a Level 2 escalation decision
When the orchestrator serialises the delegation
Then the body is a `ReverseDelegationTask` whose every field maps to
the `TaskContext` schema, and the adapter asserts that no foreign
keys or repository paths are present.

#### Scenario: agent cannot mutate runtime through delegation

Given the external agent returns a result
When the orchestrator ingests the result
Then the orchestrator processes the response through a port that
exposes only the documented `ReverseDelegationResult` value type.

### Requirement: Egress, audit and redaction are mandatory on outbound delegation

Every reverse-delegation outbound call MUST consult the egress
classifier before the call is placed, MUST emit one audit record per
attempt with the same Phase 7 audit shape, and MUST run the outgoing
context through the Phase 8 redaction pipeline. The redaction
pipeline MUST operate on the `TaskContext` payload, not on a raw
dictionary.

#### Scenario: redacted secrets never cross the boundary

Given a `TaskContext` whose context includes a secret-shaped value
matching the `secret://...` reference pattern
When the delegation runs
Then the redaction pipeline replaces the value with an opaque
reference before the call is placed.

#### Scenario: failed egress audit record is written

Given the egress classifier returns `DENY`
When the delegation is attempted
Then no outbound call is made and one audit record with
`policyDecision = DENY` and `operation = "reverse.delegate"` is
written.

### Requirement: Supported external agent identities are documented

The platform MUST document the supported external agent list
(`claude-code`, `codex`, `opencode`, `hermes`, `generic-mcp`,
`generic-a2a`) in the capability descriptor. The list MUST be
versioned through the same descriptor version field used by the A2A
adapter. Adding or removing an entry MUST require an ADR-style
update.

#### Scenario: descriptor exposes the supported agent list

Given the capability descriptor is queried
When the descriptor is returned
Then it includes `reverseDelegation.supportedAgents` with every
documented agent identity.

#### Scenario: every supported agent has a documented off-ramp

Given a `ReverseDelegationResult` whose status is `unsupported`
When the orchestrator ingests the result
Then it MUST surface a documented user-facing error code and MUST
NOT silently retry.

### Requirement: Result ingestion is deterministic and rate-limited

The platform MUST bound the response payload size, the response
processing time and the number of in-flight delegations per actor.
When a bound is exceeded the orchestrator MUST refuse the result
with the documented error code and MUST write one audit record.

#### Scenario: oversize response is refused

Given a `ReverseDelegationResult` whose payload exceeds the
documented byte cap
When the orchestrator ingests the result
Then it MUST refuse the result with the documented error code,
record one audit row and not attempt any further processing.

#### Scenario: per-actor concurrency limit is enforced

Given more than the documented per-actor in-flight delegations
When a new delegation is requested
Then the orchestrator refuses the new delegation with
`limit-exceeded` until an in-flight delegation completes.

### Requirement: Reverse delegation has no silent retry

The orchestrator MUST NOT silently retry a failed delegation unless
the operator configured an explicit, bounded retry policy. The
retry policy MUST be recorded in the audit log on every attempt.

#### Scenario: default policy is no retry

Given no retry policy is configured
When a delegation fails
Then the orchestrator surfaces the documented failure to the caller
and writes one audit record with `retry = false`.

#### Scenario: explicit bounded retry is logged

Given an operator configured a bounded retry policy
When the delegation retries
Then every retry attempt is logged with `retryAttempt = <n>` and
the total number of retries stays within the configured cap.

### Requirement: External agent identity never leaks into the core domain model

The orchestrator and the `ReverseDelegationPolicy` MUST refer to
external agents only through capability identities and documented
metadata strings. Vendor-specific CLI command names, environment
variables, or transport identifiers MUST NOT appear in
`pi_platform/core/`.

#### Scenario: core code references no vendor-specific surface

Given a static analysis scan
When every Python module under `pi_platform/core/` is examined
Then no module imports a vendor-specific CLI command, a
vendor-specific environment variable name, or a vendor-specific
transport identifier.

