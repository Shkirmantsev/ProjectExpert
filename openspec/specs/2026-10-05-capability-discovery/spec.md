# 2026-10-05-capability-discovery Specification

## Purpose
TBD - created by archiving change implement-phase-5-orchestration. Update Purpose after archive.
## Requirements
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

