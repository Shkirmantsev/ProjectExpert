# Context impact — prepare-phase-7-control-plane

## Knowledge to create

- `.ai/wiki/modules/registry.md` — Phase 7 control-plane
  Feature / Plugin Registry module map; lifecycle state
  machine, manifest validation, dependency resolution.
  `kind: module`, `status: draft`.
- `.ai/wiki/modules/hooks.md` — Phase 7 Hook Runtime module
  map; lifecycle events, timeout, cancellation, failure
  policies. `kind: module`, `status: draft`.
- `.ai/wiki/modules/policy-engine.md` — Phase 7 Policy Engine
  module map; capability vocabulary, roles, decision
  contract. `kind: module`, `status: draft`.
- `.ai/wiki/modules/secret-provider.md` — Phase 7 Secret
  Provider module map; `secret://` / `env://` reference
  vocabulary, redaction contract. `kind: module`, `status:
  draft`.
- `.ai/wiki/modules/audit-log.md` — Phase 7 Audit Log /
  Operational Log module map; two-stream separation, §59
  fields. `kind: module`, `status: draft`.
- `.ai/wiki/modules/feature-flags.md` — Phase 7 Feature Flags
  module map; scope vocabulary and lifecycle states.
  `kind: module`, `status: draft`.
- `.ai/wiki/modules/ui-extensions.md` — Phase 7 UI Extension
  Registry module map; declarative descriptors, no-arbitrary-
  JS rule. `kind: module`, `status: draft`.
- `.ai/wiki/interfaces/control-registry.md` —
  `FeatureRegistryPort`, `PluginRegistryPort`,
  `LifecycleState`, `FeatureManifest`, `PluginManifest`,
  `ManifestValidationError`. `kind: interface`,
  `status: draft`.
- `.ai/wiki/interfaces/hook-runtime.md` — `HookRuntimePort`,
  `HookEvent`, `HookDefinition`, `HookFailurePolicy`,
  `HookResult`, `HookTimeoutError`, `HookCancelledError`.
  `kind: interface`, `status: draft`.
- `.ai/wiki/interfaces/policy-engine.md` — `PolicyEnginePort`,
  `PolicyRequest`, `PolicyDecision`, `Capability`, `Role`,
  `ApprovalRequired`, `DeniedError`. `kind: interface`,
  `status: draft`.
- `.ai/wiki/interfaces/secret-provider.md` —
  `SecretProviderPort`, `SecretReference`,
  `SecretResolutionError`, `RedactionContext`.
  `kind: interface`, `status: draft`.
- `.ai/wiki/interfaces/audit-log.md` — `AuditLogPort`,
  `OperationalLogPort`, `AuditRecord`, `OperationalRecord`.
  `kind: interface`, `status: draft`.
- `.ai/wiki/interfaces/feature-flags.md` — `FeatureFlagPort`,
  `FeatureFlagState`, `FeatureFlagScope`. `kind: interface`,
  `status: draft`.
- `.ai/wiki/interfaces/ui-extension.md` —
  `UiExtensionRegistryPort`, `UiExtensionDescriptor`,
  `UiExtensionKind`. `kind: interface`, `status: draft`.
- `.ai/wiki/interfaces/capabilities.md` — Cross-cutting
  §59.4 capability vocabulary used by every control-plane
  subsystem. `kind: interface`, `status: draft`.
- `.ai/wiki/adr/0014-control-plane-policy-engine.md` — ADR
  for the central policy engine separation and the
  replacement of the Phase 1 `PolicyDecisionStub` behind
  the existing `PolicyDecisionPort`. `kind: adr`,
  `status: proposed`.
- `.ai/wiki/adr/0015-secret-references-and-redaction.md` —
  ADR for the `secret://` reference vocabulary and the
  redaction contract that MCP / A2A / audit / LLM context
  MUST apply. `kind: adr`, `status: proposed`.
- `.ai/wiki/adr/0016-audit-vs-operational-log-separation.md`
  — ADR for the strict two-stream Audit / Operational
  separation and the no-secret-in-audit invariant.
  `kind: adr`, `status: proposed`.

## Knowledge to update

- `.ai/wiki/INDEX.md` — add the new module, interface and
  ADR nodes under the `modules/`, `interfaces/` and `adr/`
  areas; extend the Phase 7 control-plane section.
- `.ai/wiki/architecture/platform-overview.md` — extend
  the Phase 7 module map with the seven new modules (control-registry, hook-runtime, policy-engine, secret-provider, audit-log, feature-flags, ui-extension) and
  the capability vocabulary; reference the v0.8 §59
  baseline; mark the new control-plane section as
  `planned`.
- `.ai/wiki/glossary/platform.md` — add the Phase 7
  vocabulary (`capability`, `role`, `secret reference`,
  `hook event`, `hook failure policy`, `audit record`,
  `feature flag`, `scope`, `UI extension descriptor`,
  `declarative UI`).
- `.ai/wiki/project/implementation-roadmap.md` — flip the
  Phase 7 row from `planned` to `complete` once the
  implementation change is archived; reference the seven
  new product modules plus the cross-cutting capabilities
  contract and the three new ADRs.
- `.ai/wiki/project/project-map.md` — add the
  `pi_platform/ports/control/`,
  `pi_platform/core/control/` and
  `pi_platform/adapters/control/` directories under
  `Main source areas` once the implementation change is
  adopted.
- `openspec/CURRENT.md` — extend the project product
  capabilities table with the eight Phase 7 capabilities
  when the future
  `implement-phase-7-control-plane` change is archived.

## Knowledge to review for staleness

- `.ai/wiki/architecture/platform-overview.md` — verify the
  control-plane section reflects the eight Phase 7 modules
  and the §59 capability vocabulary once the
  implementation change is adopted; otherwise leave the
  `planned` marker.
- `.ai/wiki/modules/agent-integration.md` — confirm the
  Phase 6 module map still references the Phase 1
  `PolicyDecisionStub` as the policy backing implementation;
  the stub continues to back the `MaterialiseService` until
  the Phase 7 implementation change rewires it.
- `.ai/wiki/modules/runtime-store.md` — verify the Phase 3
  runtime store description still holds: the Phase 7
  control plane does NOT introduce a new runtime store;
  registry / hook / flag state is persisted through the
  Phase 1-3 git / runtime / hydration layer.
- `.ai/wiki/architecture/system-overview.md` — extend the
  "Principal components" section with the Phase 7 control
  plane only when the implementation change is archived;
  until then the Phase 7 subsystems stay marked
  `planned`.

## Affected implementation

Modules / paths:

- `openspec/changes/prepare-phase-7-control-plane/` —
  created by this change (artifacts only);
- `openspec/changes/implement-phase-7-control-plane/` —
  mirror delta set created by the future change;
- `openspec/specs/2026-10-08-<capability>/` — adopted by
  the future change.

Primary symbols / interfaces (future, declared by the eight
Phase 7 spec deltas and design; implemented in the future
change):

- `platform.control.registry.FeatureRegistry`,
  `PluginRegistry`, `LifecycleState`, `FeatureManifest`,
  `PluginManifest`, `ManifestValidationError`;
- `platform.control.hooks.HookRuntime`, `HookEvent`,
  `HookDefinition`, `HookFailurePolicy`, `HookResult`,
  `HookTimeoutError`, `HookCancelledError`;
- `platform.control.policy.PolicyEngine`, `PolicyRequest`,
  `PolicyDecision`, `Capability`, `Role`,
  `ApprovalRequired`, `DeniedError`;
- `platform.control.secrets.SecretProvider`,
  `SecretReference`, `SecretResolutionError`,
  `RedactionContext`;
- `platform.control.audit.AuditLog`, `OperationalLog`,
  `AuditRecord`, `OperationalRecord`;
- `platform.control.flags.FeatureFlag`,
  `FeatureFlagState`, `FeatureFlagScope`;
- `platform.control.ui_extensions.UiExtensionRegistry`,
  `UiExtensionDescriptor`, `UiExtensionKind`.

## ADR impact

- `adr/0001-separate-core-and-integration-skill-ownership.md`
  remains accepted and unaffected. This change respects
  the decision by keeping the harness core skills and the
  Phase 7 control plane product modules clearly separated.
- `adr/0004-ports-and-adapters-extension-style.md`
  remains accepted and unaffected. The Phase 7 control
  plane continues the hexagonal + micro-kernel extension
  style mandated by the ADR.
- New `adr/0014-control-plane-policy-engine.md` formalises
  the central policy engine separation and the replacement
  of the Phase 1 `PolicyDecisionStub` behind the existing
  `PolicyDecisionPort`.
- New `adr/0015-secret-references-and-redaction.md`
  formalises the `secret://` / `env://` reference
  vocabulary and the redaction contract.
- New `adr/0016-audit-vs-operational-log-separation.md`
  formalises the strict two-stream Audit / Operational
  separation and the no-secret-in-audit invariant.

## Acceptance criteria

- [x] Relevant Wiki pages reflect planned / shipped
  implementation. The Wiki updates listed above are
  additive and link back to the v0.8 architecture
  baseline.
- [x] Generated local context index was refreshed. After
  the Wiki edits the future implementation change MUST
  re-run `python harness.py wiki-init` and the operator
  MUST run the same command on every Phase 7 adoption.
- [x] Links and stable knowledge IDs validate. The new
  Wiki pages use stable `id` frontmatter values (see
  Knowledge to create above) so that `kb_validate`
  succeeds.
- [x] Spec / implementation mismatches are resolved or
  explicitly documented. There is no implementation in
  this change; the eight Phase 7 spec deltas describe the
  planned control-plane behaviour against the v0.8
  baseline with no conflict.