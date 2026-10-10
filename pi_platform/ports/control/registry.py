"""Phase 7 §59.1, §59.2 Feature / Plugin Registry port.

The registry is the single source of truth every other
control-plane subsystem consults. Built-in and installed
features share the documented lifecycle vocabulary.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


__all__ = [
    "FeatureManifest",
    "FeatureRegistryPort",
    "IllegalLifecycleTransition",
    "LifecycleState",
    "ManifestValidationError",
    "PluginManifest",
    "PluginRegistryPort",
]


class LifecycleState(str, enum.Enum):
    """§59.1 documented lifecycle states."""

    INSTALLED = "installed"
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"
    INCOMPATIBLE = "incompatible"
    BLOCKED_BY_POLICY = "blocked-by-policy"
    UPDATE_AVAILABLE = "update-available"


# Documented transition graph (subset; FAIL_CLOSED hooks and
# INCOMPATIBLE manifests may move a feature into FAILED /
# INCOMPATIBLE; the registry records the transition).
_ALLOWED: Mapping[LifecycleState, frozenset[LifecycleState]] = {
    LifecycleState.INSTALLED: frozenset({
        LifecycleState.ENABLED,
        LifecycleState.DISABLED,
        LifecycleState.FAILED,
        LifecycleState.INCOMPATIBLE,
        LifecycleState.BLOCKED_BY_POLICY,
        LifecycleState.UPDATE_AVAILABLE,
    }),
    LifecycleState.ENABLED: frozenset({
        LifecycleState.DISABLED,
        LifecycleState.FAILED,
        LifecycleState.UPDATE_AVAILABLE,
    }),
    LifecycleState.DISABLED: frozenset({
        LifecycleState.ENABLED,
        LifecycleState.FAILED,
        LifecycleState.UPDATE_AVAILABLE,
    }),
    LifecycleState.FAILED: frozenset({
        LifecycleState.DISABLED,
        LifecycleState.UPDATE_AVAILABLE,
    }),
    LifecycleState.INCOMPATIBLE: frozenset({
        LifecycleState.UPDATE_AVAILABLE,
    }),
    LifecycleState.BLOCKED_BY_POLICY: frozenset({
        LifecycleState.DISABLED,
        LifecycleState.UPDATE_AVAILABLE,
    }),
    LifecycleState.UPDATE_AVAILABLE: frozenset({
        LifecycleState.ENABLED,
        LifecycleState.DISABLED,
        LifecycleState.FAILED,
        LifecycleState.INCOMPATIBLE,
    }),
}


def _assert_can_transition(
        current: LifecycleState,
        target: LifecycleState) -> None:
    allowed = _ALLOWED.get(current, frozenset())
    if target not in allowed:
        raise IllegalLifecycleTransition(current, target)


class IllegalLifecycleTransition(RuntimeError):
    """Raised when a registry transition is not part of the
    documented lifecycle state machine."""

    def __init__(self, current: LifecycleState,
                 target: LifecycleState) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"illegal-lifecycle-transition: current={current.value} "
            f"target={target.value}"
        )


@dataclass(frozen=True)
class FeatureManifest:
    """§59.1 feature / plugin manifest."""

    id: str
    name: str
    version: str
    api_version: str
    license: str
    provider: str
    type: str  # "plugin" or "feature"
    capabilities: tuple[str, ...] = ()
    configuration_schema: str = ""
    permissions_required: tuple[str, ...] = ()
    permissions_optional: tuple[str, ...] = ()
    hooks: tuple[str, ...] = ()
    ui_settings_panel: bool = False
    ui_status_panel: bool = False
    content_hash: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "apiVersion": self.api_version,
            "license": self.license,
            "provider": self.provider,
            "type": self.type,
            "capabilities": list(self.capabilities),
            "configurationSchema": self.configuration_schema,
            "permissions": {
                "required": list(self.permissions_required),
                "optional": list(self.permissions_optional),
            },
            "hooks": list(self.hooks),
            "ui": {
                "settingsPanel": self.ui_settings_panel,
                "statusPanel": self.ui_status_panel,
            },
            "contentHash": self.content_hash,
        }


# Aliases for plugin-only manifests (semantic sugar)
PluginManifest = FeatureManifest


class ManifestValidationError(RuntimeError):
    """Raised when a manifest fails validation.

    The ``check`` attribute carries the failing check name
    (``"license"``, ``"capabilities"``, ``"compatibility"``,
    ``"content_hash"``); ``value`` carries the failing value.
    """

    def __init__(self, *, check: str, value: str,
                 manifest_id: str) -> None:
        self.check = check
        self.value = value
        self.manifest_id = manifest_id
        super().__init__(
            f"manifest-validation-error: manifest={manifest_id!r} "
            f"check={check!r} value={value!r}"
        )


class _BaseRegistryPort(abc.ABC):
    """Shared interface for Feature and Plugin registries."""

    @abc.abstractmethod
    def install(self, manifest: FeatureManifest) -> LifecycleState: ...

    @abc.abstractmethod
    def uninstall(self, feature_id: str) -> None: ...

    @abc.abstractmethod
    def enable(self, feature_id: str,
               approval_token: Optional[str] = None) -> LifecycleState: ...

    @abc.abstractmethod
    def disable(self, feature_id: str,
                approval_token: Optional[str] = None) -> LifecycleState: ...

    @abc.abstractmethod
    def inspect(self, feature_id: str) -> tuple[FeatureManifest,
                                                LifecycleState]: ...

    @abc.abstractmethod
    def list_features(self) -> Iterable[tuple[FeatureManifest,
                                              LifecycleState]]: ...

    @abc.abstractmethod
    def transition(self, feature_id: str,
                   target: LifecycleState) -> LifecycleState: ...

    @abc.abstractmethod
    def serialise(self) -> str: ...


class FeatureRegistryPort(_BaseRegistryPort):
    """§59.1 Feature Registry port.

    Built-in features use the same lifecycle vocabulary as
    installed features.
    """


class PluginRegistryPort(_BaseRegistryPort):
    """§59.1 Plugin Registry port.

    Installed plugins use the same lifecycle vocabulary as
    built-in features.
    """