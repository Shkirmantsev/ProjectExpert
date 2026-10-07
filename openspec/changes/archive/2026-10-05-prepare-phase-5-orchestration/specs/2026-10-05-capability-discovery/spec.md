# capability-discovery Specification delta

Covers architecture section §47 (Capability Discovery). The
`CapabilityDiscovery` port returns the deterministic
`CapabilityDescriptor` JSON that the Phase 6 MCP server
exposes via `describe_capabilities` and that skills / plugins
consume to adapt to the actual deployment.

The descriptor reports the server version, the MCP API
version, the knowledge schema version and a structured
`features` map (`hybridRetrieval`, `graphExpansion`,
`okf`, `materialization`, `a2a`, `localLlm`). Optional
features report `False` when the corresponding runtime is
not registered; the descriptor is the source of truth the
agents and skills use to avoid assuming a feature is
available.

## ADDED Requirements

### Requirement: CapabilityDiscoveryPort contract

The platform MUST expose a `CapabilityDiscoveryPort` abstract
class in
`pi_platform/ports/orchestration/capability_discovery.py`
with the following operations:

- `describe() -> CapabilityDescriptor` — return the
  deterministic capability descriptor for the current
  deployment;
- `refresh() -> CapabilityDescriptor` — re-evaluate the
  runtime registrations (e.g. after a `LocalLLMPort`
  registration / unregistration) and return the updated
  descriptor;
- `stats() -> Mapping[str, int]` — operational counters
  including `describe_calls`, `refresh_calls`,
  `feature_count`.

`CapabilityDescriptor` carries:

- `serverVersion` (str) — the platform server version
  (semver);
- `mcpApiVersion` (str) — the MCP API version the server
  speaks (semver);
- `knowledgeSchemaVersion` (str) — the canonical knowledge
  schema version (semver);
- `okfVersions` (Sequence[str]) — the OKF profiles the
  platform accepts (e.g. `["0.2"]`);
- `features` (CapabilityFeatures) — a structured map of
  optional features.

`CapabilityFeatures` carries:

- `hybridRetrieval` (bool) — `True` when the Phase 4
  `HybridRetrievalPort` is registered;
- `graphExpansion` (bool) — `True` when the Phase 4
  production `GraphExpansion` adapter is registered;
- `okf` (Sequence[str]) — the OKF profiles the platform
  accepts (duplicate of `okfVersions` for backward
  compatibility);
- `materialization` (bool) — `True` when the Phase 1
  materialise service is available;
- `a2a` (bool) — `True` when the Phase 10 A2A adapter is
  registered (always `False` until Phase 10 ships);
- `localLlm` (bool) — `True` when the Phase 5
  `LocalLLMPort.is_available() == True`.

#### Scenario: describe returns a deterministic descriptor

Given a deployment with the Phase 4 `HybridRetrievalPort`
registered and the stub `LocalLLMPort` (no model)
When `describe()` runs
Then the returned `CapabilityDescriptor` reports
`features.hybridRetrieval == True`
And `features.graphExpansion == True`
And `features.localLlm == False`
And `features.a2a == False`
And the descriptor serialises to a deterministic JSON
string.

### Requirement: refresh re-evaluates registrations

The `CapabilityDiscoveryPort.refresh` operation MUST
re-evaluate the runtime registrations and return the
updated `CapabilityDescriptor`. The `refresh` call MUST
NOT allocate a new port; it MUST inspect the existing
registry.

#### Scenario: refresh picks up a new LLM registration

Given a deployment where the stub `LocalLLMPort` is
initially registered
When `refresh()` runs after an LLM registration
Then the returned descriptor reports
`features.localLlm == True`.

### Requirement: capability descriptor is serialisable

The `CapabilityDescriptor` value type MUST be JSON-
serialisable via the platform's canonical serializer.
The serialised output MUST be stable byte-for-byte for a
fixed deployment state.

#### Scenario: serialised descriptor is stable

Given a deployment with a fixed set of registrations
When `describe()` runs twice consecutively
Then the serialised JSON of both descriptors is
byte-identical.

### Requirement: skills query the descriptor at startup

The `CapabilityDiscovery` port MUST be the single source of
truth for skill / plugin capability decisions. The skills
MUST query the descriptor at startup; they MUST NOT assume
every deployment exposes every optional feature.

#### Scenario: skill reads the descriptor

Given a skill that requires the `localLlm` feature
When the skill initialises
Then it reads the `CapabilityDescriptor` via
`CapabilityDiscoveryPort.describe()`
And if `features.localLlm == False` the skill degrades
gracefully to the no-LLM path
And if `features.localLlm == True` the skill uses the
local LLM.

### Requirement: discovery report covers the §47 example shape

The `CapabilityDescriptor` MUST include the documented §47
example fields. The `serverVersion`, `mcpApiVersion`,
`knowledgeSchemaVersion` and `features.{hybridRetrieval,
graphExpansion, okf, materialization, a2a, localLlm}` keys
MUST all be present in the serialised descriptor.

#### Scenario: descriptor matches the §47 example shape

Given any deployment
When `describe()` runs
Then the serialised JSON contains the keys
`serverVersion`, `mcpApiVersion`, `knowledgeSchemaVersion`,
`features`
And `features` contains the keys `hybridRetrieval`,
`graphExpansion`, `okf`, `materialization`, `a2a`,
`localLlm`.

## Phase 5 task coverage

The change covers Phase 5 task 82 (CapabilityDiscovery
returning the §47 descriptor). Task 80 (LocalLLMPort) and
task 84 (Wiki maintenance) reference the descriptor.

Out of scope:

- the QueryOrchestrator implementation — Phase 5 task 79
  (`query-orchestrator`);
- the LocalLLMPort implementation — Phase 5 task 80
  (`local-llm-port`);
- the TaskContextBuilder implementation — Phase 5 task 81
  (`task-context-builder`);
- the §83 retrieval-first policy regression test — Phase 5
  task 83 (`retrieval-first-policy`);
- the MCP server exposing `describe_capabilities` — Phase 6
  task 85 (`mcp-server`);
- the A2A capability — Phase 10 tasks 119-123.