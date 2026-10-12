"""Phase 7 §59 control-plane ports.

The control plane exposes the seven documented extension
points that every administrative surface consults:

* ``FeatureRegistryPort`` / ``PluginRegistryPort`` — the
  single source of truth for built-in and installed features
  and their documented lifecycle state.
* ``HookRuntimePort`` — the lifecycle event dispatcher
  with bounded timeout, cancellation, correlation id, audit
  record and documented failure policies.
* ``PolicyEnginePort`` — the central authorisation source
  with the documented capability vocabulary, the documented
  role defaults and the ``ALLOW / DENY / REQUIRE_APPROVAL``
  decision contract.
* ``SecretProviderPort`` — the ``secret://`` /
  ``env://`` reference resolver with mandatory redaction in
  MCP / A2A / audit / LLM context.
* ``AuditLogPort`` / ``OperationalLogPort`` — two strictly
  separated streams; secret values MUST never appear in
  audit records.
* ``FeatureFlagPort`` — the documented scope resolver and
  the documented lifecycle states.
* ``UiExtensionRegistryPort`` — the declarative UI
  descriptor registry with the no-arbitrary-JavaScript
  rule.

Adapters live under ``pi_platform/adapters/control/*``;
default production implementations live under
``pi_platform/core/control/*``. The control plane never
imports a concrete adapter from a port module and never
modifies a Phase 1-6 capability spec.
"""

from .audit import (
    AuditLogPort,
    AuditRecord,
    InvalidAuditRecordError,
    OperationalLogPort,
    OperationalRecord,
)
from .flags import (
    FeatureFlagContext,
    FeatureFlagPort,
    FeatureFlagScope,
    FeatureFlagState,
    InvalidFeatureFlagScopeError,
    IllegalFeatureFlagTransitionError,
)
from .hooks import (
    HookCancelledError,
    HookContext,
    HookDefinition,
    HookEvent,
    HookFailurePolicy,
    HookResult,
    HookRuntimePort,
    HookTimeoutError,
)
from .policy import (
    ApprovalRequired,
    Capability,
    Decision,
    DeniedError,
    PolicyDecision,
    PolicyEnginePort,
    PolicyRequest,
    Role,
    UnknownCapabilityError,
    DEFAULT_ROLE_CAPABILITIES,
    ROLE_VIEWER,
    ROLE_DEVELOPER,
    ROLE_MAINTAINER,
    ROLE_ADMINISTRATOR,
    ROLE_CODING_AGENT_READ_ONLY,
)
from .registry import (
    FeatureManifest,
    FeatureRegistryPort,
    IllegalLifecycleTransition,
    LifecycleState,
    ManifestValidationError,
    PluginManifest,
    PluginRegistryPort,
)
from .secrets import (
    InvalidSecretReferenceError,
    RedactionContext,
    SecretProviderPort,
    SecretReference,
    SecretResolutionError,
)
from .ui_extensions import (
    InvalidUiExtensionDescriptorError,
    UiExtensionDescriptor,
    UiExtensionKind,
    UiExtensionRegistryPort,
)

__all__ = [
    # registry
    "FeatureManifest",
    "FeatureRegistryPort",
    "IllegalLifecycleTransition",
    "LifecycleState",
    "ManifestValidationError",
    "PluginManifest",
    "PluginRegistryPort",
    # hooks
    "HookCancelledError",
    "HookContext",
    "HookDefinition",
    "HookEvent",
    "HookFailurePolicy",
    "HookResult",
    "HookRuntimePort",
    "HookTimeoutError",
    # policy
    "ApprovalRequired",
    "Capability",
    "Decision",
    "DeniedError",
    "PolicyDecision",
    "PolicyEnginePort",
    "PolicyRequest",
    "Role",
    "UnknownCapabilityError",
    "DEFAULT_ROLE_CAPABILITIES",
    "ROLE_VIEWER",
    "ROLE_DEVELOPER",
    "ROLE_MAINTAINER",
    "ROLE_ADMINISTRATOR",
    "ROLE_CODING_AGENT_READ_ONLY",
    # secrets
    "InvalidSecretReferenceError",
    "RedactionContext",
    "SecretProviderPort",
    "SecretReference",
    "SecretResolutionError",
    # audit
    "AuditLogPort",
    "AuditRecord",
    "InvalidAuditRecordError",
    "OperationalLogPort",
    "OperationalRecord",
    # flags
    "FeatureFlagContext",
    "FeatureFlagPort",
    "FeatureFlagScope",
    "FeatureFlagState",
    "InvalidFeatureFlagScopeError",
    "IllegalFeatureFlagTransitionError",
    # ui_extensions
    "InvalidUiExtensionDescriptorError",
    "UiExtensionDescriptor",
    "UiExtensionKind",
    "UiExtensionRegistryPort",
]