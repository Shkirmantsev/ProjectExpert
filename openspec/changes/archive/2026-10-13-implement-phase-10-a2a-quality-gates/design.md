# Design — implement-phase-10-a2a-quality-gates

This design record is provided so the implementation change has a
stable reference. The architectural design is in
[`prepare-phase-10-a2a-quality-gates/design.md`](../prepare-phase-10-a2a-quality-gates/design.md);
this document only enumerates the implementation seams needed by
the Blocks below.

## Module map (delta from Phase 9)

```text
pi_platform/ports/a2a/                       # new (4 files)
  ├── __init__.py
  ├── a2a_adapter.py            # A2aAdapterPort, AgentCardPort
  ├── reverse_delegation.py     # ReverseDelegationPort, ReverseDelegationPolicy
  └── external_agent.py         # ExternalAgentPort, ExternalAgentMetadata

pi_platform/core/a2a/                         # new (5 files)
  ├── __init__.py
  ├── spec_version.py           # A2A_SPEC_VERSION constant
  ├── a2a_adapter.py            # A2aAdapterCore composing the ports
  ├── reverse_delegation.py     # ReverseDelegationPolicyCore
  └── policy_gate.py            # ReverseDelegationPolicyGate (delegates to PolicyEngine)

pi_platform/adapters/a2a/                     # new (4 files)
  ├── __init__.py
  ├── http_transport.py         # loopback HTTP JSON-RPC, no new deps
  ├── stdio_transport.py        # JSON-lines on stdin/stdout
  └── envelope.py               # wire DTO ↔ port DTO translation

pi_platform/core/eval/                        # new (6 files)
  ├── __init__.py
  ├── metrics.py                # schema `phase-10-eval/1`, deterministic collector
  ├── scenarios.py              # scenario base class + harness wiring
  ├── invariants.py             # §68 invariant probe base + helpers
  ├── migration_guard.py        # schema-version migration helpers
  └── writer.py                 # atomic writer for `eval/last.json`

pi_platform/adapters/agent_integration/       # extension
  ├── claude_code.py            # ExternalAgentPort implementation
  ├── codex.py                  # ExternalAgentPort implementation
  ├── opencode.py               # ExternalAgentPort implementation
  ├── hermes.py                 # ExternalAgentPort implementation (stub)
  ├── generic_mcp.py            # ExternalAgentPort implementation (stub)
  └── generic_a2a.py            # ExternalAgentPort implementation (stub)

tests/
  ├── test_phase_10_a2a.py
  ├── test_phase_10_quality_gates.py
  ├── test_phase_10_invariants.py
  ├── test_phase_10_schema_migration.py
  └── fixtures/phase_10/        # synthetic project + deliberate conflicts + stale entries
```

The existing `pi_platform/core/orchestration/capability_discovery.py`
is extended by adding two optional fields to its descriptor; the
Phase 5 suite remains green. `pi_platform/cli/main.py` gains
`eval`, `invariants` and `metrics-gate` subcommands. `Makefile`
gains three targets.

## Constraints

- No new Python third-party dependency. The HTTP transport uses
  `http.server` (stdlib). The stdio transport uses the
  `BaseTransport` shape from Phase 9. JSON encoding uses `json`
  (stdlib).
- Every new port has a unit test that proves it can be implemented
  outside `core/` (Phase 5 pattern).
- Every new module lives behind a port; tests verify the boundary.
- The integration-quality-gates metric file is always written
  atomically through `tmpfile + rename` so the harness never reads
  a half-written JSON.
- The §68 suite uses one Python class per invariant, named
  `Invariant<n>`; the loader asserts count == 52.
