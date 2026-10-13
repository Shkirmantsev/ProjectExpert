# control-registry Specification delta

## Purpose

Expose the Feature / Plugin Registry that every control-plane subsystem consults as the single source of truth for built-in and installed features and their documented lifecycle state.

## Requirements


### Requirement: Feature Registry and Plugin Registry share the documented lifecycle state machine

The control plane MUST expose a `FeatureRegistry` and a
`PluginRegistry` (both thin adapters over the same
`FeatureRegistryPort`) with the documented §59.1 lifecycle
states: `installed`, `enabled`, `disabled`, `failed`,
`incompatible`, `blocked-by-policy`, `update-available`. A
feature or plugin MUST transition through the documented
order; an illegal transition MUST raise the typed
`IllegalLifecycleTransition` error. The registry MUST NOT
introduce a new runtime store; it MUST reuse the Phase 3
`RuntimeStore` through the Phase 1 `GitPort` /
`WorkingTreeOverlayPort` for durable state.

#### Scenario: registry rejects an illegal lifecycle transition

Given a plugin is currently in state `disabled`
When the operator invokes `enable` while the policy engine
denies the transition
Then the registry raises `IllegalLifecycleTransition`
And the registry state remains `disabled`
And the registry records an audit entry with
`operation=enable`, `result=denied`.

#### Scenario: registry transitions through the documented states

Given a plugin is currently in state `installed`
When the operator invokes `enable` and the policy engine
authorises the transition
Then the registry transitions to `enabled`
And the registry records an audit entry with
`operation=enable`, `result=allowed`.

### Requirement: Manifest validation enforces license, capabilities, compatibility and content hash

The registry MUST validate every feature and plugin manifest
before installation. The validator MUST check the SPDX
license through the Phase 1 `LicenseGatePort`, the requested
capabilities against the §59.4 vocabulary, the compatibility
range against the §39 version handshake and the content hash
against the supplied manifest body. The validator MUST reject
any manifest that fails any of these checks with the typed
`ManifestValidationError` carrying the failing check name and
the failing value.

#### Scenario: validator rejects a manifest with an unknown capability

Given a plugin manifest declares `capabilities=["net.free"]`
When the registry invokes the manifest validator
Then the validator raises `ManifestValidationError` with
`check="capabilities"`, `value="net.free"`.
And the registry rejects the installation
And the registry records an audit entry with
`operation=install`, `result=denied`.

#### Scenario: validator rejects a manifest with an incompatible version

Given a plugin manifest declares
`platformVersion="<2.0.0" >=1.0.0`
and the server advertises `>=2.0.0 <3.0.0`
When the registry invokes the manifest validator
Then the validator raises `ManifestValidationError` with
`check="compatibility"`,
`value="<2.0.0 >=1.0.0"`.

### Requirement: enable / disable consult the Policy Engine and record an audit entry

Every control-registry mutation MUST consult the Policy Engine and
record an audit entry. Every `enable` / `disable` / `install` / `uninstall` /
`configure` call MUST consult the Phase 7 `PolicyEngine`
before mutating registry state. The registry MUST record an
audit entry with `actorType`, `actorId`, `operation`,
`resource`, `policyDecision`, `result`, `duration` and
`correlationId`. The registry MUST NOT bypass the Phase 1
`MaterialiseService` approval boundary when writing durable
registry state.

#### Scenario: enable requires an approval token when the policy engine returns REQUIRE_APPROVAL

Given a `Maintainer` invokes `enable` on a third-party plugin
When the policy engine returns `REQUIRE_APPROVAL`
Then the registry raises `ApprovalRequired`
And the registry state remains `installed`
And the registry records an audit entry with
`policyDecision="require_approval"`, `result=denied`.

### Requirement: serialise() is byte-stable

The control-registry serialise MUST be byte-stable. Two
consecutive `serialise()` calls on the same registry
MUST return byte-identical JSON. The serialised form MUST
include every registered feature and plugin with its
`id`, `version`, `state`, `capabilities`, `license`,
`compatibility` and `contentHash`. The serialised form MUST
NOT include resolved secret values; the registry persists
`SecretReference` only.

#### Scenario: serialise is byte-stable

Given the registry has two registered plugins
When the operator invokes `serialise()` twice
Then the two returned JSON strings are byte-identical.
And neither string contains a resolved secret value.
