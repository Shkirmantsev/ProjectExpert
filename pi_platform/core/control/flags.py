"""Phase 7 §59.15 default Feature Flag registry.

The registry resolves the most specific scope in the
documented order (``user > deploymentProfile > branch >
project > machine``). Git-versioned feature declarations
and local overrides remain in separate sources.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional

from pi_platform.core.control.audit import _safe_record
from pi_platform.ports.control.flags import (
    FeatureFlagContext,
    FeatureFlagPort,
    FeatureFlagScope,
    FeatureFlagState,
    IllegalFeatureFlagTransitionError,
    InvalidFeatureFlagScopeError,
    _ALLOWED,
    _SCOPE_ORDER,
)


__all__ = ["DefaultFeatureFlagRegistry"]


def _assert_can_transition(current: FeatureFlagState,
                            target: FeatureFlagState) -> None:
    allowed = _ALLOWED.get(current, frozenset())
    if target not in allowed:
        raise IllegalFeatureFlagTransitionError(current, target)


def _default_for_experimental(current: FeatureFlagState,
                               explicit: bool) -> FeatureFlagState:
    if current is FeatureFlagState.EXPERIMENTAL and not explicit:
        return FeatureFlagState.DISABLED
    return current


@dataclass
class DefaultFeatureFlagRegistry(FeatureFlagPort):
    """Default production Feature Flag registry."""

    _declarations: dict[str,
                         tuple[FeatureFlagState,
                                FeatureFlagScope]] = field(
        default_factory=dict)
    _overrides: dict[str, dict[str,
                                tuple[FeatureFlagState, str]]] = field(
        default_factory=dict)
    _audit_hook: Optional[object] = field(default=None, repr=False)

    def register(self, flag_id: str, *,
                 state: FeatureFlagState,
                 scope: FeatureFlagScope) -> None:
        if scope is None:
            raise InvalidFeatureFlagScopeError(
                f"flag={flag_id!r} scope is required")
        self._declarations[flag_id] = (state, scope)

    def override(self, flag_id: str, *,
                 state: FeatureFlagState,
                 scope: FeatureFlagScope,
                 scope_key: str) -> None:
        self._overrides.setdefault(flag_id, {})[scope.value] = (
            state, scope_key,
        )

    def resolve(self, flag_id: str, *,
                context: FeatureFlagContext) -> FeatureFlagState:
        if flag_id not in self._declarations:
            raise KeyError(flag_id)
        base_state, _ = self._declarations[flag_id]
        resolved = _default_for_experimental(base_state, explicit=False)
        for scope in _SCOPE_ORDER:
            scope_key = _scope_key_for(scope, context)
            if scope_key == "":
                continue
            override = self._overrides.get(flag_id, {}).get(scope.value)
            if override is None:
                continue
            override_state, override_key = override
            if override_key == scope_key:
                resolved = override_state
                self._audit(operation="flag.override_applied",
                            result="allowed", flag_id=flag_id,
                            scope=scope.value)
                break
        self._audit(operation="flag.resolve", result="allowed",
                    flag_id=flag_id, scope=resolved.value)
        return resolved

    def list(self) -> Iterable[tuple[str, FeatureFlagState,
                                     FeatureFlagScope]]:
        for flag_id in sorted(self._declarations):
            state, scope = self._declarations[flag_id]
            yield flag_id, state, scope

    def transition(self, flag_id: str,
                   target: FeatureFlagState) -> FeatureFlagState:
        if flag_id not in self._declarations:
            raise KeyError(flag_id)
        current, scope = self._declarations[flag_id]
        _assert_can_transition(current, target)
        self._declarations[flag_id] = (target, scope)
        return target

    def serialise(self) -> str:
        payload = {
            "declarations": {
                fid: {"state": state.value, "scope": scope.value}
                for fid, (state, scope) in sorted(
                    self._declarations.items())
            },
            "overrides": {
                fid: {
                    scope_value: {"state": state.value, "key": key}
                    for scope_value, (state, key) in sorted(
                        overrides.items())
                }
                for fid, overrides in sorted(self._overrides.items())
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _audit(self, *, operation: str, result: str,
               flag_id: str, scope: str = "") -> None:
        _safe_record(
            self._audit_hook,
            operation=operation,
            result=result,
            resource=f"{flag_id}@{scope}" if scope else flag_id,
        )

    def attach_audit_log(self, audit_log: object) -> None:
        self._audit_hook = audit_log


def _scope_key_for(scope: FeatureFlagScope,
                    context: FeatureFlagContext) -> str:
    return {
        FeatureFlagScope.MACHINE: context.machine_id,
        FeatureFlagScope.PROJECT: context.project_version,
        FeatureFlagScope.BRANCH: context.branch,
        FeatureFlagScope.USER: context.user_id,
        FeatureFlagScope.DEPLOYMENT_PROFILE: context.deployment_profile,
    }.get(scope, "")