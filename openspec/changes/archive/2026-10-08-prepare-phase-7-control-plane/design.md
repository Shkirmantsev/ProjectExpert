# Design — prepare-phase-7-control-plane

## Current state

The repository currently contains:

- the development harness framework (`harness.py`, `Makefile`,
  `scripts/`, `.agents/skills/`, `openspec/`, `.ai/`,
  `tools/mcp/`, `.opencode/`, `.claude/`, `.codex/`);
- the v0.8 architecture baseline document at the repository
  root (`project-intelligence-platform-architecture-v0.8.md`);
- the accepted Phase 1-6 capability specs under
  `openspec/specs/2026-09-07-*`,
  `openspec/specs/2026-10-03-*`,
  `openspec/specs/2026-10-04-*`,
  `openspec/specs/2026-10-05-*` and
  `openspec/specs/2026-10-07-*`;
- the `pi_platform/` Python package with the Phase 1-6
  modules (canonical, git, sync, licensing, ingest,
  retrieval, orchestration, runtime, agent integration, mcp);
- the Phase 1 `PolicyDecisionStub`
  (`pi_platform/core/sync/policy_stub.py`) that backs the
  `MaterialiseService` approval gate until the future
  `implement-phase-7-control-plane` change replaces it with
  the Phase 7 Policy Engine;
- the existing Wiki nodes documenting the platform overview,
  the implementation roadmap, the Phase 6 readiness review and
  the Phase 6 interface contracts;
- the accepted ADRs for the architectural style, the canonical
  / runtime separation, the license governance default, the
  ports-and-adapters extension style, the platform source
  language, the Phase 6 agent integration packaging, the
  Phase 6 version compatibility handshake and the Phase 6
  plugin supply-chain security.

The repository does NOT yet contain any control-plane module,
any Feature / Plugin Registry, any Hook Runtime, any Policy
Engine, any Secret Provider, any Audit Log, any Feature Flag
surface or any UI Extension registry. The Phase 1
`PolicyDecisionStub` is the only authorization backend in
production today. The architecture document is the only
source of control-plane intent.

This design covers two scopes:

1. the overall Phase 7 control-plane architecture, used to
   align the eight OpenSpec specs with the same vocabulary,
   module boundaries and dependency rules;
2. the eight Phase 7 spec deltas the implementation change
   will adopt, derived from §59 of the v0.8 architecture
   baseline.

## Architectural style

The Phase 7 control plane continues the architectural style
mandated by §59:

- **Hexagonal / Ports-and-Adapters core.** The control
  plane is a set of stable extension ports
  (`FeatureRegistryPort`, `PluginRegistryPort`,
  `HookRuntimePort`, `PolicyEnginePort`, `SecretProviderPort`,
  `AuditLogPort`, `OperationalLogPort`, `FeatureFlagPort`,
  `UiExtensionRegistryPort`). Adapters in
  `pi_platform/adapters/control/*` implement the ports for
  the default in-process scenario; future isolated sidecar
  adapters (Phase 9+) implement the same ports behind an
  authenticated local protocol.
- **Micro-kernel / Plugin extension surface.** The control
  plane registers plugins, hooks, UI extensions, observability
  providers and exporters through the documented stable
  extension contract. Plugins never extend the core domain
  types or services directly; they short-circuit through the
  control-plane authorisation, audit and lifecycle.
- **Single modular deployable.** The default deployable
  remains one process. The control plane is shipped in the
  default container; it does not require a separate
  microservice. The Phase 9 distribution profile may add an
  optional UI sidecar.

The control plane is agent-neutral, model-neutral and
storage-neutral. The core does not depend on a specific
observability vendor, a specific UI framework or a specific
secret backend. Vendor adapters plug in through the documented
ports.

## Control plane and data plane

The platform separates:

- **Control plane** — Phase 7 ships the seven product
  subsystems that realise it (Feature / Plugin Registry,
  Hook Runtime, Policy Engine, Secret Provider, Audit Log,
  Feature Flags and UI Extension registry) plus the
  cross-cutting capabilities contract. Every administrative
  surface (CLI, future UI, future A2A administration
  channel) consults the control plane for configuration,
  policy, secrets, audit and registry operations.
- **Data plane** — Phase 1-6 ingest, index, retrieve, graph,
  context-assemble, run the MCP server, run the agent adapter
  and run the orchestrator. Every data-plane execution path
  consults the Phase 7 Policy Engine for authorisation, the
  Phase 7 Audit Log for audit emission, the Phase 7 Secret
  Provider for secret resolution and the Phase 7 Hook Runtime
  for the documented lifecycle events.

The control plane configures and observes the data plane but
must not bypass the same authorization rules that apply to
agents and plugins. Both planes call into the same central
Policy Engine for authorization decisions.

## Modules and packages

Phase 7 ships the following top-level product modules under
`pi_platform/`:

- `pi_platform/ports/control/`
  - `registry.py` — `FeatureRegistryPort`,
    `PluginRegistryPort`, `LifecycleState`,
    `FeatureManifest`, `PluginManifest`,
    `ManifestValidationError`;
  - `hooks.py` — `HookRuntimePort`, `HookEvent`,
    `HookDefinition`, `HookFailurePolicy`,
    `HookResult`, `HookTimeoutError`,
    `HookCancelledError`;
  - `policy.py` — `PolicyEnginePort`, `PolicyRequest`,
    `PolicyDecision`, `Capability`, `Role`,
    `ApprovalRequired`, `DeniedError`;
  - `secrets.py` — `SecretProviderPort`, `SecretReference`,
    `SecretResolutionError`, `RedactionContext`;
  - `audit.py` — `AuditLogPort`, `OperationalLogPort`,
    `AuditRecord`, `OperationalRecord`;
  - `flags.py` — `FeatureFlagPort`, `FeatureFlagState`,
    `FeatureFlagScope`;
  - `ui_extensions.py` — `UiExtensionRegistryPort`,
    `UiExtensionDescriptor`, `UiExtensionKind`;
- `pi_platform/core/control/`
  - `registry.py` — `DefaultFeatureRegistry`,
    `DefaultPluginRegistry`, the lifecycle state machine
    and the manifest validator;
  - `hooks.py` — `DefaultHookRuntime`, the event dispatcher,
    the timeout / cancellation engine, the correlation-id
    generator, the bounded retry policy and the failure-
    policy resolver;
  - `policy.py` — `DefaultPolicyEngine`, the capability
    vocabulary from §59, the role default resolution, the
    `ALLOW / DENY / REQUIRE_APPROVAL` decision contract, the
    typed `ApprovalRequired` exception and the typed
    `DeniedError`;
  - `secrets.py` — `DefaultSecretProvider`, the
    `secret://` / `env://` reference parser, the redaction
    filter used by MCP / A2A / audit / LLM context and the
    typed `SecretResolutionError`;
  - `audit.py` — `DefaultAuditLog`, `DefaultOperationalLog`,
    the record schemas and the strict two-stream separation;
  - `flags.py` — `DefaultFeatureFlagRegistry`, the
    scope-resolver and the documented lifecycle states;
  - `ui_extensions.py` — `DefaultUiExtensionRegistry`, the
    declarative UI descriptor validator and the
    no-arbitrary-JavaScript-injection guard.
- `pi_platform/adapters/control/`
  - `secret_backends.py` — OS keychain / environment /
    encrypted local store adapters;
  - `audit_sinks.py` — JSONL local sink and the
    OpenTelemetry adapter (optional, not bundled by
    default);
  - `flag_sources.py` — git-versioned, project-local and
    machine-local feature flag sources.

The control plane does NOT introduce a new runtime store;
all registry / hook / flag state is persisted through the
Phase 1-3 git / runtime / hydration layer. The Phase 7
implementation MUST NOT bypass the Phase 1
`MaterialiseService` approval gate when writing
control-plane state.

## Capability vocabulary

The Phase 7 capability vocabulary is the cross-cutting
contract every subsystem uses (§59.4). The vocabulary is
declared in `pi_platform/ports/control/policy.py` and
includes:

```text
knowledge.read
knowledge.write
knowledge.materialize

retrieval.query
retrieval.admin

graph.read
graph.write

source.read
source.import

filesystem.read
filesystem.write

git.read
git.write

config.read
config.write

secret.reference
secret.resolve

mcp.invoke
mcp.admin

agent.delegate

network.local
network.external

audit.read
audit.write
```

The same vocabulary is used for UI users, coding agents,
A2A agents, plugins, hooks, CLI operations and automation.

## Role defaults

The Phase 7 policy engine provides four documented role
defaults (§59.5):

```text
Viewer        — knowledge.read, retrieval.query, graph.read,
                source.read, git.read, config.read, audit.read
Developer     — Viewer + filesystem.write, config.write,
                source.import, mcp.invoke, audit.write
Maintainer    — Developer + knowledge.write, graph.write,
                retrieval.admin, git.write, secret.reference,
                mcp.admin, agent.delegate, network.local
Administrator — Maintainer + knowledge.materialize,
                secret.resolve, network.external,
                config.write (all)
```

A coding agent has its own role with the documented
read-only capability set from §59.8. The Policy Engine MUST
resolve authorization to capabilities; role defaults are
convenience initialisers, not the authorization source of
truth.

## Hook events

The Hook Runtime fires on the documented §59.6 events:

```text
beforeIngestion
afterIngestion
beforeIndexUpdate
afterIndexUpdate
beforeRetrieval
afterRetrieval
beforeContextAssembly
afterContextAssembly
beforeMcpTool
afterMcpTool
beforeAgentDelegation
afterAgentDelegation
beforeMaterialization
afterMaterialization
onBranchSwitch
onProjectOpen
onProjectClose
```

Each hook definition carries `hook id`, `plugin id`, `event`,
`priority`, `timeout`, `permissions`, `failure policy`,
`configuration` and `version`. The hook runtime enforces the
documented failure policy
(`FAIL_OPEN / FAIL_CLOSED / WARN_ONLY / DISABLE_PLUGIN`).
Security-sensitive hooks (`beforeMaterialization`,
`beforeMcpTool`, `beforeAgentDelegation`) fail closed;
observability-only hooks (`afterRetrieval`,
`afterContextAssembly`, `afterMcpTool`) may fail open.

## Secret references

`pi_platform/ports/control/secrets.py` declares the
`SecretReference` value type and the reference vocabulary:

```text
secret://local/confluence-token
secret://enterprise/internal-api-key
env://HTTP_PROXY
```

`SecretProviderPort.resolve(reference)` returns the resolved
value to the calling subsystem; `SecretProviderPort.redact`
returns the redacted form used by MCP responses, A2A payloads,
audit payloads and LLM context. The runtime database MUST
NOT become a plain-text secret vault.

## Audit vs Operational Log separation

`pi_platform/ports/control/audit.py` declares the
`AuditLogPort` and `OperationalLogPort` as two strictly
separated streams. The Audit Log is append-only, records
the §59.13 fields and never records secret values or
unnecessary source contents. The Operational Log remains
the diagnostics / performance / health surface; the two
streams MUST NOT share a sink or a writer.

## Feature flag scope

`pi_platform/ports/control/flags.py` declares the
`FeatureFlagScope` vocabulary:

```text
machine
project
branch
user
deploymentProfile
```

Git-versioned feature declarations and local overrides
remain distinct. Each flag has one of the §59.15 lifecycle
states (`disabled`, `enabled`, `experimental`,
`deprecated`). The Policy Engine consults the flag
registry when deciding whether to expose an experimental
capability.

## UI extension registry

`pi_platform/ports/control/ui_extensions.py` declares the
declarative UI descriptor and the `UiExtensionRegistryPort`.
The registry accepts only declarative descriptors
(`settingsPanel`, `statusPanel`, `dashboardWidget`,
`menuItem`); it rejects any descriptor carrying executable
JavaScript or any field outside the documented schema. The
Phase 9 UI renderer consumes the registry; no plugin can
inject arbitrary JavaScript.

## Concurrency

The control plane uses cooperative scheduling:

- the registry uses the Phase 1 `GitPort` and `RuntimeStore`
  for atomic state transitions; concurrent enable / disable
  requests are serialised through the Phase 1
  `ProjectLock`;
- the Hook Runtime uses per-event bounded concurrency: at
  most one hook per (event, plugin) pair fires concurrently;
  hooks run in a worker pool sized by the documented
  configuration;
- the Policy Engine is stateless and thread-safe; each call
  resolves to a typed decision;
- the Audit Log and the Operational Log use append-only JSONL
  sinks with a per-stream writer lock; the two streams never
  share a writer;
- the Secret Provider uses an in-memory LRU cache keyed by
  reference; cache TTL is bounded by the documented
  configuration.

## Failure modes

The control plane fails closed by default:

- a registry that cannot validate a manifest MUST refuse
  installation and record an audit entry;
- a Hook Runtime that cannot run a security-sensitive hook
  MUST apply `FAIL_CLOSED` or `DISABLE_PLUGIN`;
- a Policy Engine that cannot reach the role registry MUST
  return `DENY` and record an audit entry;
- a Secret Provider that cannot resolve a reference MUST
  raise `SecretResolutionError`; the calling consumer MUST
  translate the error into `DENY` if the calling capability
  is `secret.resolve`;
- an Audit Log that cannot write MUST close the calling
  data-plane action and return a typed error to the
  operator;
- a Feature Flag Registry that cannot resolve a scope MUST
  return the default `disabled` state.

## Interfaces

The control plane exposes:

- `pi_platform.ports.control.registry.FeatureRegistryPort`
  — `install`, `uninstall`, `enable`, `disable`,
    `inspect`, `list_features`, `list_state`;
- `pi_platform.ports.control.hooks.HookRuntimePort`
  — `register`, `unregister`, `dispatch`,
    `list_event_hooks`, `cancel`;
- `pi_platform.ports.control.policy.PolicyEnginePort`
  — `evaluate`, `authorize`,
    `require_approval`, `deny`;
- `pi_platform.ports.control.secrets.SecretProviderPort`
  — `resolve`, `redact`, `list_references`,
    `invalidate`;
- `pi_platform.ports.control.audit.AuditLogPort` —
  `record`, `query`, `flush`;
- `pi_platform.ports.control.audit.OperationalLogPort` —
  `record`, `query`, `flush`;
- `pi_platform.ports.control.flags.FeatureFlagPort`
  — `resolve`, `set`, `list`, `scope`;
- `pi_platform.ports.control.ui_extensions.UiExtensionRegistryPort`
  — `register`, `unregister`, `list`,
    `validate_descriptor`.

## Affected paths

- `openspec/changes/prepare-phase-7-control-plane/` — new
  artifacts only;
- `openspec/changes/implement-phase-7-control-plane/` —
  mirror delta set created by the future change;
- `openspec/specs/2026-10-08-<capability>/` — adopted by
  the future change;
- `pi_platform/ports/control/`, `pi_platform/core/control/`,
  `pi_platform/adapters/control/` — created by the future
  change;
- `tests/test_phase_7_control_plane.py` — created by the
  future change;
- `tests/test_phase_6_quality_gates.py` — extended by the
  future change with Phase 7 quality gates (policy
  allow/deny/require-approval, hook failure policy, audit
  redaction, secret redaction, UI extension validation);
- `.ai/wiki/interfaces/` — new nodes;
- `.ai/wiki/modules/` — new nodes;
- `.ai/wiki/adr/` — new ADRs;
- `openspec/CURRENT.md` — updated when adopted;
- `plan-v0-8-platform-architecture/tasks.md` — rows 96-104
  flipped to `[x]` by the implementation change.

## Compatibility

The Phase 7 control plane is a compatibility-safe swap of
the Phase 1 `PolicyDecisionStub` behind the existing
Phase 1 `PolicyDecisionPort`. No accepted Phase 1-6 spec is
modified. The Phase 6 MCP server, agent adapter contract,
plugin supply-chain security gate, version handshake and
capability discovery continue to operate; only the central
authorization decision source changes. Migration happens in the
future `implement-phase-7-control-plane` change and is
covered by the focused regression tests recorded in the
implementation `tasks.md`.

## Risks

- **Authorisation regression.** A wrong default in the
  Policy Engine could lock out read-only coding agents or
  expose durable writes. Mitigation: comprehensive focused
  tests, default-deny posture, full audit emission and the
  Phase 1 `MaterialiseService` approval boundary as a
  last-resort safety net.
- **Hook deadlock.** A misconfigured hook could deadlock
  MCP / retrieval execution. Mitigation: bounded timeout,
  cancellation, structured result, the documented failure
  policy and the "failed hook MUST NOT silently deadlock"
  invariant from §59.
- **Secret leakage.** An MCP response, A2A payload, audit
  record or LLM context could leak a raw secret value.
  Mitigation: the `SecretProviderPort.redact` filter, the
  no-secret-in-audit invariant and the focused redaction
  tests.
- **Audit stream mixing.** A bug in the writer dispatch
  could let the Operational Log receive audit records or
  vice versa. Mitigation: separate sinks, separate writers,
  separate ports and a focused separation test.
- **UI extension injection.** A bug in the descriptor
  validator could allow an untrusted plugin to inject
  JavaScript. Mitigation: the schema validator, the
  no-arbitrary-JS rule and a focused fuzz-style test.

## Out of scope

- Phase 8 enterprise boundary, Phase 9 distribution
  one-click launcher, Phase 10 A2A adapter — Phase 8-10
  tasks 105-123;
- the pre-existing harness-side MCP server at
  `tools/mcp/project-context-mcp/`;
- any change to the accepted Phase 1-6 capability specs;
- any change to the Phase 1 `MaterialiseService` approval
  boundary or the Phase 1 `TrustedApprovalBoundary`;
- any change to the Phase 6 MCP tool surface, the Phase 6
  agent adapter contract, the Phase 6 version handshake or
  the Phase 6 plugin supply-chain security gate (only the
  authorisation source changes behind the existing ports).