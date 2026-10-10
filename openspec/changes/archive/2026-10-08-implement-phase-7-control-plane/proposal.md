# Proposal — Prepare the v0.8 Phase 7 Control Plane Capability Specs

## Why

The v0.8 architecture baseline
([`project-intelligence-platform-architecture-v0.8.md`](../../../project-intelligence-platform-architecture-v0.8.md))
defines the **Control Plane** as the seventh implementation
phase (§5, §59, §47). Phase 7 turns the Phase 6 MCP server,
agent adapter contract and supply-chain security gate into a
production-grade administration surface: a Feature / Plugin
Registry that tracks lifecycle state for every built-in and
installed feature; a first-class Hook Runtime that fires on the
documented lifecycle events with bounded timeout, cancellation,
correlation ID, audit record and failure policy; a centralised
Policy Engine that resolves actor + role + capability + resource
+ project/version context into the documented
`ALLOW / DENY / REQUIRE_APPROVAL` decision contract; a Secret
Provider that resolves the `secret://` reference vocabulary with
mandatory redaction in MCP / A2A / audit / LLM context; an
Audit Log kept strictly separate from the Operational Log; a
scoped Feature-Flag surface; and a declarative UI Extension
registry that does not allow arbitrary JavaScript injection.

Phase 1 supplies the canonical `PolicyDecisionStub` that this
phase replaces with the full Policy Engine; Phase 2 supplies the
canonical chunks, entities and relations that the registry
metadata references; Phase 3 supplies the
`KnowledgeReadinessPort` and runtime store; Phase 4 supplies
the retrieval, metadata filter and context assembler ports the
control plane guards; Phase 5 supplies the capability
discovery, query orchestrator, local LLM port and task context
builder that the control plane now authorizes; Phase 6 supplies
the MCP server, agent adapter contract, version handshake and
plugin supply-chain security gate that consume the new policy
engine and audit log.

Without Phase 7 specs:

- there is no authoritative behavioural contract for the
  Feature / Plugin Registry lifecycle states
  (`installed / enabled / disabled / failed / incompatible /
  blocked-by-policy / update-available`) or for manifest
  validation;
- there is no authoritative behavioural contract for hook
  lifecycle events, timeouts, cancellation, failure policy or
  audit emission;
- the Phase 1 `PolicyDecisionStub` stays in production forever;
  coding agents cannot be granted the documented
  read-only capability set; high-impact materialisation cannot
  return `REQUIRE_APPROVAL` through a typed decision contract;
- secrets have no portable reference vocabulary, and redaction
  in MCP / A2A / audit / LLM context is unspecified;
- Audit Log is indistinguishable from Operational Log, so
  operators cannot prove who called which MCP tool with which
  capability at which project version;
- feature flags have no documented scoping vocabulary
  (machine / project / branch / user / deployment profile);
- UI extensions have no declarative contract, so any plugin can
  inject arbitrary JavaScript into the control plane UI.

Phase 8's enterprise boundary has no Policy Engine to wrap;
Phase 9's distribution one-click launcher has no Feature /
Plugin Registry to populate; Phase 10's A2A delegation has no
centralised authorization to delegate through. This change
authoring gap is the prerequisite for the Phase 7
implementation.

This change resolves the gap by authoring eight Phase 7
capability specs and the supporting design, context-impact
and tasks, while shipping zero production code. The
implementation work is proposed under
`implement-phase-7-control-plane`; its mirrored deltas remain
future requirements until implementation, verification and
adoption. Preparation completion does not adopt these
capabilities. At adoption, reconcile the provisional
`2026-10-08-*` delta identities in both changes to the actual
first Git acceptance date, then promote exactly one delta set.
Archive preparation without reapplying its duplicate ADDED
requirements.

## Goal

Author the Phase 7 capability specs and change artifacts so
that a later `implement-phase-7-control-plane` change can:

- ship `FeatureRegistry` and `PluginRegistry`
  (`platform.control.registry`) with the documented lifecycle
  states from §59, manifest validation (license, capabilities,
  compatibility, content hash), the lifecycle state machine,
  installation ordering, dependency resolution, update
  detection and the controlled enable / disable / configure
  surface. The registry is the single source of truth that
  every other control-plane subsystem consults; built-in and
  installed features share the same lifecycle vocabulary.
- ship `HookRuntime` (`platform.control.hooks`) with the
  documented lifecycle events from §59
  (`beforeIngestion`, `afterIngestion`,
  `beforeIndexUpdate`, `afterIndexUpdate`,
  `beforeRetrieval`, `afterRetrieval`,
  `beforeContextAssembly`, `afterContextAssembly`,
  `beforeMcpTool`, `afterMcpTool`,
  `beforeAgentDelegation`, `afterAgentDelegation`,
  `beforeMaterialization`, `afterMaterialization`,
  `onBranchSwitch`, `onProjectOpen`, `onProjectClose`),
  bounded timeout, cancellation, structured result, correlation
  ID, audit record, bounded retries if explicitly configured
  and the documented failure policies (`FAIL_OPEN`,
  `FAIL_CLOSED`, `WARN_ONLY`, `DISABLE_PLUGIN`). Security-
  sensitive hooks fail closed; observability-only hooks may
  fail open. A failed hook never silently deadlocks MCP /
  retrieval execution.
- ship `PolicyEngine` (`platform.control.policy`) with
  capability-based authorization, the §59 capability
  vocabulary, the role defaults (`Viewer`, `Developer`,
  `Maintainer`, `Administrator`), the
  `ALLOW / DENY / REQUIRE_APPROVAL` decision contract, the
  typed `PolicyDecision` value and the typed
  `ApprovalRequired` exception that MCP tools, the Agent
  Adapter, hooks and the materialisation flow raise when
  high-impact actions are requested. The engine replaces the
  Phase 1 `PolicyDecisionStub` without changing the Phase 1
  `MaterialiseService` approval boundary or the trusted
  approval gate.
- ship `SecretProvider` (`platform.control.secrets`) with the
  `secret://` and `env://` reference vocabulary, mandatory
  redaction in MCP responses, A2A payloads (unless explicitly
  authorized), audit payloads and LLM context, the
  `SecretReference` value type and the typed
  `SecretResolutionError`. The runtime database MUST NOT
  become a plain-text secret vault; the provider resolves
  through OS keychain / environment / encrypted local store
  adapters that ship under separate dependency entries.
- ship `AuditLog` and `OperationalLog`
  (`platform.control.audit`) as two strictly separated
  streams. The Audit Log records the §59 fields
  (`timestamp`, `correlationId`, `projectVersion`, `actorType`,
  `actorId`, `plugin/agentId`, `operation`, `resource`,
  `policyDecision`, `result`, `duration`). Secret values and
  unnecessary source contents MUST never be written into audit
  records. The Operational Log remains the diagnostics /
  performance / health surface; the two streams MUST NOT
  share a sink or a writer.
- ship `FeatureFlags` (`platform.control.flags`) with the
  documented scope vocabulary (`machine`, `project`, `branch`,
  `user`, `deploymentProfile`) and the documented lifecycle
  states (`disabled`, `enabled`, `experimental`, `deprecated`).
  Git-versioned feature declarations and local overrides
  remain distinct.
- ship `UiExtension` registry
  (`platform.control.ui_extensions`) with declarative UI
  descriptors (settings panel, status panel, dashboard
  widgets), stable identifier contracts and a strict
  no-arbitrary-JavaScript-injection rule. Untrusted plugins
  cannot inject executable code; the UI runtime renders only
  the documented declarative descriptors.

What this change does:

- proposes the eight Phase 7 capability specs under
  `openspec/changes/prepare-phase-7-control-plane/specs/`;
- documents the technical design covering the registry, hook
  runtime, policy engine, secret provider, audit log, feature
  flags and UI extension registry;
- creates the `implement-phase-7-control-plane` change folder
  under
  `openspec/changes/implement-phase-7-control-plane/` and
  mirrors the eight delta specs verbatim so the future
  implementation archive carries the same delta set;
- lists the Wiki, ADR and context-impact nodes the future
  `implement-phase-7-control-plane` change will need to create
  or update;
- enumerates Phase 7 tasks 96-104 (mirroring
  [`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md))
  with concrete verification commands; task 104 is the
  close-out task and does not require its own capability
  spec.

Out of scope for this change:

- any production code under `pi_platform/core/control/`,
  `pi_platform/ports/control/`,
  `pi_platform/adapters/control/`, `.ai/wiki/modules/control/`
  or any related Phase 7 module;
- any addition to the runtime dependency inventory beyond
  the optional encrypted local store, OS keychain, JSON
  schema validator and (where required) HTTP redirector
  entries the future
  `implement-phase-7-control-plane` change MUST add through
  the documented `LicenseGate`;
- the implementation of the Feature / Plugin Registry (task
  96), Hook Runtime (task 97), Policy Engine (task 98),
  Secret Provider (task 99), Audit Log (task 100), Feature
  Flags (task 101), UI Extension (task 102), the focused
  regression tests (task 103) and the Wiki maintenance (task
  104) — all Phase 7 implementation work;
- the Phase 8 enterprise security boundary, the Phase 9
  distribution one-click launcher, the Phase 10 A2A adapter —
  Phase 8-10 tasks 105-123;
- the pre-existing harness-side MCP server at
  `tools/mcp/project-context-mcp/` — that is a different
  deliverable owned by the harness scope, not by the
  product scope.

## Affected capabilities

This change authors eight additive capability specs under
`openspec/changes/prepare-phase-7-control-plane/specs/` that
cover tasks 96-102 from
[`plan-v0-8-platform-architecture/tasks.md`](../plan-v0-8-platform-architecture/tasks.md).
Task 103 (focused regression tests) and task 104 (Wiki +
ADR + archive + `CURRENT.md`) are the close-out tasks and
do not require their own capability spec. The eight specs:

| Spec delta | Capability surface | Architecture section | Task |
|---|---|---|---|
| `control-registry` | Feature / Plugin Registry with lifecycle state machine, manifest validation, dependency resolution | §59.1, §59.2 | 96 |
| `hook-runtime` | Hook lifecycle events, timeout, cancellation, correlation, failure policies | §59.6, §59.7, §59.8 | 97 |
| `policy-engine` | Centralised Policy Engine, `ALLOW / DENY / REQUIRE_APPROVAL` decision contract | §59.11, §59.12 | 98 |
| `secret-provider` | `secret://` and `env://` reference vocabulary, mandatory redaction | §59.10 | 99 |
| `audit-log` | Audit Log vs Operational Log separation, §59 fields, no-secret invariant | §59.13 | 100 |
| `feature-flags` | Feature flag scope vocabulary and lifecycle states | §59.15 | 101 |
| `ui-extension` | Declarative UI extension registry, no-arbitrary-JS rule | §59.16 | 102 |
| `capabilities` | Cross-cutting §59.4 capability vocabulary, role defaults, read-only coding-agent set | §59.4, §59.5, §59.8 | (cross-cutting) |

The eight spec deltas are additive; the preparation change
does NOT modify the accepted Phase 1-6 capability specs under
`openspec/specs/`. The Phase 1 `PolicyDecisionStub` remains
the documented behaviour of the Phase 1 sync layer until the
future `implement-phase-7-control-plane` change replaces it
with the Phase 7 Policy Engine. The Phase 6
`PluginSupplyChainSecurityGate` continues to operate against
the Phase 1 stub until the implementation change rewires it.

## Compatibility / migration impact

This change authors eight new capability specs and ships
zero production code. It does NOT modify the accepted
Phase 1-6 capability specs under `openspec/specs/`. It does
NOT remove or deprecate the Phase 1 `PolicyDecisionStub`;
the stub continues to back the Phase 1 `MaterialiseService`
approval gate until the future
`implement-phase-7-control-plane` change replaces it with the
Phase 7 Policy Engine.

The future implementation change is a compatibility-safe
swap of the policy backing implementation behind the existing
Phase 1 `PolicyDecisionPort` and the Phase 6 MCP server, the
Phase 6 plugin supply-chain security gate, the Phase 6 agent
adapter contract, the Phase 5 capability discovery and the
Phase 5 query orchestrator. The Phase 6 handshakes, MCP tool
schemas and audit fields remain stable; only the central
authorization decision source changes.

## Related knowledge

- `kb://architecture.platform-overview` — extended with the
  Phase 7 module map (registry, hooks, policy engine, secret
  provider, audit, flags, UI extensions);
- `kb://glossary.platform` — extended with the Phase 7
  vocabulary (capability, role, secret reference, hook
  event, hook failure policy, audit record, feature flag,
  scope, UI extension descriptor, declarative UI);
- new `kb://interfaces.capabilities`,
  `kb://interfaces.hook-runtime`,
  `kb://interfaces.policy-engine`,
  `kb://interfaces.secret-provider`,
  `kb://interfaces.audit-log`,
  `kb://interfaces.feature-flags`,
  `kb://interfaces.ui-extension`,
  `kb://interfaces.control-registry`;
- new `kb://modules.registry`,
  `kb://modules.hooks`,
  `kb://modules.policy-engine`,
  `kb://modules.secret-provider`,
  `kb://modules.audit-log`,
  `kb://modules.feature-flags`,
  `kb://modules.ui-extensions`;
- new `kb://adr.0014-control-plane-policy-engine` — central
  policy engine separation;
- new `kb://adr.0015-secret-references-and-redaction` —
  `secret://` reference vocabulary and redaction contract;
- new `kb://adr.0016-audit-vs-operational-log-separation` —
  the two-stream audit / operational split;
- external:
  `project-intelligence-platform-architecture-v0.8.md`
  §5, §17, §33, §47, §59, §49.