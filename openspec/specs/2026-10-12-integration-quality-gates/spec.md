# 2026-10-12-integration-quality-gates Specification

## Purpose
TBD - created by archiving change prepare-phase-10-a2a-quality-gates. Update Purpose after archive.
## Requirements
### Requirement: Integration-quality-gates suites are deterministic

Every integration-quality-gates suite MUST be deterministic and
reproducible. Each suite MUST seed its random sources, MUST bound its
wall-clock time, MUST bound its memory footprint and MUST record its
inputs and outputs in a single structured metrics file under
`tmp/local/project-context/eval/last.json` with schema
`phase-10-eval/1`.

#### Scenario: metric file is produced deterministically

Given an integration-quality-gates suite run
When the suite completes
Then the file `tmp/local/project-context/eval/last.json` exists,
its `schema` is `phase-10-eval/1`, its `timestamp` is the suite
start time and all `metrics.*` values are integers or floats
between documented bounds.

#### Scenario: rerun produces identical metrics

Given the same suite is run twice against the same inputs
When the second metrics file is diffed against the first
Then only the `timestamp` field differs and every `metrics.*`
field is byte-identical.

### Requirement: Skill activation and MCP tool-selection suites

The integration-quality-gates suites MUST include a `Skill
activation` suite that verifies an agent skill activates on
inbound context and a `MCP tool-selection` suite that verifies the
agents prefer MCP retrieval tools over broad file scanning for
project-context questions.

#### Scenario: agent prefers MCP retrieval

Given a stub coding agent with MCP tools available
When the agent is prompted with a project-context question
Then it calls an MCP retrieval tool before opening any source
file, and the suite records the call order.

#### Scenario: known identifier routes to exact lookup

Given a stub coding agent
When the agent is asked where a documented identifier lives
Then it uses an exact lookup tool and skips dense/sparse search.

### Requirement: Retrieval-first compliance suite

The integration-quality-gates suites MUST include a
`Retrieval-first compliance` suite that asserts an integrated
coding agent follows the §33 escalation order rather than
broad repository scanning. The suite MUST assert this across at
least five representative scenarios enumerated by the platform.

#### Scenario: agent respects the escalation order

Given a stub coding agent with retrieval tools available
When the agent is asked each §33 scenario
Then it does not scan more than the documented source-file budget
before MCP retrieval.

### Requirement: Version-mismatch suite

The integration-quality-gates suites MUST include a `version
mismatch` suite that creates canonical knowledge with deliberately
outdated `knowledgeSchemaVersion`, `embeddingModelVersion` and
`indexSchemaVersion` fields, then asserts the platform refuses
silent hydration and reports the documented `MigrationRequired`
or `Incompatible` error.

#### Scenario: outdated knowledge schema refuses hydration

Given a canonical knowledge shard with `knowledgeSchemaVersion`
older than the running runtime schema
When the platform hydrates
Then hydration returns `MigrationRequired` with the documented
migration path and writes no canonical shard.

#### Scenario: outdated embedding model refuses silent cache reuse

Given cached embeddings from an older `embeddingModelVersion`
When the platform hydrates against a new schema
Then the cache is not reused and the platform records the version
mismatch in the audit log.

### Requirement: Stale and conflicting knowledge suite

The integration-quality-gates suites MUST include a `stale and
conflict handling` suite that exercises the §54 `KnowledgeState`
enum and the Phase 3 freshness tracking surfaces. The suite MUST
verify that stale, conflicting and inferred knowledge are
surfaced, not silently overwritten.

#### Scenario: stale knowledge is reported by the suite

Given a fixture with stale entries from a deleted source
When the suite runs
Then every stale entry is reported and the count is recorded in
the metrics file.

#### Scenario: conflicting knowledge is reported

Given a fixture with two contradicting entities
When the suite runs
Then both entities are reported with their `KnowledgeState` and
the suite does not auto-resolve.

### Requirement: Security-filter suite

The integration-quality-gates suites MUST include a
`security-filter` suite that asserts retrieved evidence respects
source classification, secret detection, redaction and the
egress classifier. The suite MUST cover the Phase 8
`enterprise-security-boundary` capability with at least one
positive and one negative scenario per gateway.

#### Scenario: redaction policy is applied to retrieved evidence

Given a retrieval query whose result includes a redaction-shaped
field
When the suite runs
Then the field is redacted before the result leaves the data
plane boundary.

#### Scenario: outgoing delegation respects egress policy

Given an outbound delegation to a denied destination
When the suite exercises the gate
Then the gate returns DENY and writes one audit record.

### Requirement: Plugin install/uninstall smoke suite

The integration-quality-gates suites MUST include a `plugin
install/uninstall smoke` suite that exercises the plugin
lifecycle: install, validate, enable, health-check, disable,
uninstall. The suite MUST verify the Phase 7 capability-based
permissions and the supply-chain security gate refuse an
incompatible or untrusted plugin before activation.

#### Scenario: incompatible plugin is not enabled

Given a plugin manifest whose `apiVersion` is incompatible
When the registry validates the manifest
Then it MUST mark the plugin as `incompatible` and MUST refuse to
enable it.

#### Scenario: untrusted plugin is blocked by policy

Given a plugin whose capability requests exceed the operator policy
When the registry enables the plugin
Then activation fails with a documented `blocked-by-policy`
error.

### Requirement: OKF materialisation conformance suite

The integration-quality-gates suites MUST include an `OKF
materialisation conformance` suite that asserts a conforming OKF
v0.2 bundle validates and that invalid bundles fail with the
specific violation recorded by the implementation change.

#### Scenario: conforming bundle validates

Given a conforming OKF v0.2 bundle fixture
When the suite runs the validator
Then the bundle validates and the metric for
`okf.passRate` is `1.0`.

#### Scenario: invalid bundle fails with the specific violation

Given an invalid OKF bundle (missing `type`, bad `okf_version`,
binary file present, etc.)
When the suite runs the validator
Then it returns the documented error class and the
`okf.failRateByReason` metric increments the matching reason.

### Requirement: Round-trip and branch-switch suites

The integration-quality-gates suites MUST include a `round-trip
DB ↔ Git` suite and a `branch-switch` suite that exercises the
Phase 1 hydrate/materialise round-trip and the Phase 1 reconcile
branch switch. The branch-switch suite MUST assert cache reuse
across unchanged sources and the documented hydration time
budget.

#### Scenario: round-trip produces no diff for unchanged knowledge

Given a hydrated canonical knowledge A
When the platform materialises with no changes
Then the resulting Git diff is empty for the durable shards and the
metric `roundTrip.unchangedDiffBytes = 0`.

#### Scenario: branch switch reuses cache for unchanged content

Given two branches sharing an unchanged source
When the suite switches branches
Then the unchanged source's parsed structures and embeddings are
reused and `cache.reuseRate` is recorded.

### Requirement: Token and context cost suite

The integration-quality-gates suites MUST include a `token
and context cost` suite that records `context.bytes`,
`context.tokensIn`, `context.tokensOut`, `llm.external.tokens`
for each representative scenario. The suite MUST emit a
non-blocking report when the recorded value exceeds the
documented soft cap; the report MUST be a metric, not an
exception.

#### Scenario: context size metric is recorded per scenario

Given a representative scenario
When the suite runs
Then the metrics file records the actual `context.bytes` and the
`context.tokensIn/Out` values.

#### Scenario: exceeding the soft cap produces a non-blocking report

Given a scenario that exceeds the documented token soft cap
When the suite runs
Then the metric `context.softCapExceeded = true` is recorded and
the scenario still passes.

### Requirement: §68 invariants acceptance suite

The integration-quality-gates suites MUST include a §68
acceptance suite. Each of the 52 invariants in §68 MUST have at
least one named probe method whose scenario references this
specification by its stable identifier.

#### Scenario: every §68 invariant has a probe

Given the §68 list as recorded in
`openspec/changes/plan-v0-8-platform-architecture/design.md`
When the suite is enumerated
Then the probe count equals the invariant count and each probe
name maps to the documented invariant.

#### Scenario: invariant probe failure points to the §68 clause

Given a probe fails
When the failure is reported
Then the report includes the §68 clause number and a short
explanatory label without leaking internal class names.

### Requirement: Schema-version migration guard

The integration-quality-gates suites MUST include a
`schema-version migration` guard that asserts the platform
behaves correctly when a stored canonical knowledge shard
advertises a different `knowledgeSchemaVersion`,
`embeddingModelVersion` or `indexSchemaVersion` than the running
runtime supports. The guard MUST verify the documented
`IdentityInvalid`, `MigrationRequired`, `Incompatible` and
`WorkingTreeMismatch` error paths and MUST NOT mutate canonical
files.

#### Scenario: missing manifest fails IdentityInvalid

Given a canonical knowledge tree missing the documented manifests
When the platform attempts hydrate
Then it returns `IdentityInvalid` and writes no canonical shard.

#### Scenario: bumping knowledgeSchemaVersion is MigrationRequired

Given a canonical knowledge shard with `knowledgeSchemaVersion`
strictly greater than the running runtime
When the platform attempts hydrate
Then it returns `MigrationRequired` with a `migrationPath`
documented value and writes no canonical shard.

### Requirement: CI wiring through `make` targets

The integration-quality-gates suites MUST be runnable through
documented `make` targets `make eval`, `make invariants` and
`make metrics-gate`. The targets MUST be additive, MUST NOT slow
the default offline suite and MUST NOT introduce a new dependency
on a container runtime.

#### Scenario: `make eval` runs the suite deterministically

Given the integration-quality-gates suites exist
When `make eval` runs
Then the suite completes within the documented time budget, the
metrics file is updated and the build exits zero.

#### Scenario: `make invariants` runs the §68 acceptance suite

Given the §68 acceptance suite exists
When `make invariants` runs
Then every probe runs, the count of passing probes equals the
invariant count and the build exits zero.

#### Scenario: default offline suite stays green

Given the integration-quality-gates suites are present
When the default offline suite runs
Then it does not invoke A2A, reverse delegation, container
runtimes or the network and it remains deterministic.

