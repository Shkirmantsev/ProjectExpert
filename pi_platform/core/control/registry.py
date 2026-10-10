"""Phase 7 §59.1 default Feature / Plugin Registry.

The default registry tracks lifecycle state for every
registered feature and plugin, enforces the documented
manifest validator and consults the policy engine before
mutating state.

The registry does NOT introduce a new runtime store;
durable state is persisted through the Phase 3 runtime
store via the Phase 1 ``GitPort`` /
``WorkingTreeOverlayPort``. The in-memory default is the
authoritative implementation behind the focused regression
tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Optional

from pi_platform.ports.control.policy import (
    Capability,
    Decision,
    PolicyEnginePort,
    PolicyRequest,
    Role,
)
from pi_platform.ports.control.registry import (
    FeatureManifest,
    FeatureRegistryPort,
    LifecycleState,
    ManifestValidationError,
    PluginRegistryPort,
    _assert_can_transition,
)

from pi_platform.core.control.audit import _safe_record


__all__ = ["DefaultFeatureRegistry", "DefaultPluginRegistry"]


_KNOWN_CAPABILITIES: frozenset[str] = frozenset(c.value for c in Capability)


def _validate_manifest(manifest: FeatureManifest) -> None:
    # Capabilities and permissions: every entry must belong
    # to the documented §59.4 vocabulary.
    for cap in (*manifest.capabilities, *manifest.permissions_required,
                *manifest.permissions_optional):
        if cap not in _KNOWN_CAPABILITIES:
            raise ManifestValidationError(
                check="capabilities", value=cap, manifest_id=manifest.id,
            )
    # License: must be a documented SPDX-like identifier.
    # Phase 1's LicenseGate is the thorough checker; here we
    # only refuse empty / whitespace-only identifiers and
    # characters that have no place in an SPDX identifier.
    if (not manifest.license
            or not manifest.license.strip()
            or any(c in manifest.license for c in (" ", "\t", "\n"))):
        raise ManifestValidationError(
            check="license", value=str(manifest.license),
            manifest_id=manifest.id,
        )
    # Content hash: must be a 64-character lowercase hex string.
    if (manifest.content_hash
            and (len(manifest.content_hash) != 64
                 or not all(c in "0123456789abcdef" for c in
                            manifest.content_hash))):
        raise ManifestValidationError(
            check="content_hash", value=manifest.content_hash,
            manifest_id=manifest.id,
        )
    # API version: must look like MAJOR.MINOR.PATCH.
    parts = manifest.api_version.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ManifestValidationError(
            check="api_version", value=manifest.api_version,
            manifest_id=manifest.id,
        )


@dataclass
class _BaseRegistry:
    _items: dict[str, tuple[FeatureManifest, LifecycleState]] = field(
        default_factory=dict)
    _policy: Optional[PolicyEnginePort] = field(default=None, repr=False)
    _audit_log: Optional[object] = field(default=None, repr=False)

    def _audit(self, *, operation: str, result: str,
               feature_id: str,
               duration_ms: int = 0,
               policy_decision: str = "") -> None:
        _safe_record(
            self._audit_log,
            operation=operation,
            result=result,
            resource=feature_id,
            duration_ms=duration_ms,
            policy_decision=policy_decision,
        )

    def _check_policy(self, *, operation: str,
                      actor_id: str,
                      role: Role,
                      resource: str,
                      approval_token: Optional[str]
                      ) -> None:
        if self._policy is None:
            return
        capability = Capability.MCP_ADMIN
        try:
            self._policy.authorize(
                PolicyRequest(
                    actor_type="automation",
                    actor_id=actor_id,
                    role=role,
                    capability=capability,
                    resource=resource,
                    project_version="phase-7",
                    correlation_id=operation,
                    approval_token=approval_token,
                )
            )
        except Exception:
            self._audit(operation=operation, result="denied",
                        feature_id=resource,
                        policy_decision=Decision.DENY.value)
            raise

    def attach_policy_engine(self, policy: PolicyEnginePort) -> None:
        self._policy = policy

    def attach_audit_log(self, audit_log: object) -> None:
        self._audit_log = audit_log

    def install(self, manifest: FeatureManifest,
                *, actor_id: str = "operator",
                role: Role = Role.ADMINISTRATOR,
                approval_token: Optional[str] = None) -> LifecycleState:
        _validate_manifest(manifest)
        self._check_policy(operation="install", actor_id=actor_id,
                           role=role,
                           resource=manifest.id,
                           approval_token=approval_token)
        if manifest.id in self._items:
            raise ManifestValidationError(
                check="duplicate", value=manifest.id,
                manifest_id=manifest.id,
            )
        self._items[manifest.id] = (manifest, LifecycleState.INSTALLED)
        self._audit(operation="install", result="allowed",
                    feature_id=manifest.id)
        return LifecycleState.INSTALLED

    def uninstall(self, feature_id: str, *,
                  actor_id: str = "operator",
                  role: Role = Role.ADMINISTRATOR,
                  approval_token: Optional[str] = None) -> None:
        self._check_policy(operation="uninstall", actor_id=actor_id,
                           role=role, resource=feature_id,
                           approval_token=approval_token)
        self._items.pop(feature_id, None)
        self._audit(operation="uninstall", result="allowed",
                    feature_id=feature_id)

    def enable(self, feature_id: str,
               approval_token: Optional[str] = None, *,
               actor_id: str = "operator",
               role: Role = Role.MAINTAINER) -> LifecycleState:
        return self.transition(feature_id, LifecycleState.ENABLED,
                               actor_id=actor_id,
                               role=role,
                               approval_token=approval_token)

    def disable(self, feature_id: str,
                approval_token: Optional[str] = None, *,
                actor_id: str = "operator",
                role: Role = Role.MAINTAINER) -> LifecycleState:
        return self.transition(feature_id, LifecycleState.DISABLED,
                               actor_id=actor_id,
                               role=role,
                               approval_token=approval_token)

    def inspect(self, feature_id: str
                ) -> tuple[FeatureManifest, LifecycleState]:
        if feature_id not in self._items:
            raise KeyError(feature_id)
        return self._items[feature_id]

    def list_features(self) -> Iterable[tuple[FeatureManifest,
                                              LifecycleState]]:
        # deterministic order by id
        for fid in sorted(self._items):
            yield self._items[fid]

    def transition(self, feature_id: str,
                   target: LifecycleState, *,
                   actor_id: str = "operator",
                   role: Role = Role.MAINTAINER,
                   approval_token: Optional[str] = None
                   ) -> LifecycleState:
        if feature_id not in self._items:
            raise KeyError(feature_id)
        manifest, current = self._items[feature_id]
        operation = "enable" if target is LifecycleState.ENABLED else (
            "disable" if target is LifecycleState.DISABLED else "transition"
        )
        self._check_policy(operation=operation, actor_id=actor_id,
                           role=role, resource=feature_id,
                           approval_token=approval_token)
        _assert_can_transition(current, target)
        self._items[feature_id] = (manifest, target)
        self._audit(operation=operation, result="allowed",
                    feature_id=feature_id)
        return target

    def serialise(self) -> str:
        payload = {
            "items": [
                {**manifest.as_dict(), "state": state.value}
                for _feature_id, (manifest, state) in sorted(
                    self._items.items(),
                    key=lambda kv: kv[0],
                )
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _force_state(self, feature_id: str,
                     state: LifecycleState) -> None:
        """Test-only seam: bypass the lifecycle state machine
        when wiring deterministic fixtures. The lock is
        intentionally simple and MUST NOT be used in
        production code paths.
        """
        if feature_id not in self._items:
            raise KeyError(feature_id)
        manifest, _ = self._items[feature_id]
        self._items[feature_id] = (manifest, state)


class DefaultFeatureRegistry(_BaseRegistry, FeatureRegistryPort):
    """Default production Feature Registry."""


class DefaultPluginRegistry(_BaseRegistry, PluginRegistryPort):
    """Default production Plugin Registry.

    Identical to :class:`DefaultFeatureRegistry` in this
    in-memory implementation; the two ports are kept
    separate so a future distributed implementation can
    diverge cleanly.
    """