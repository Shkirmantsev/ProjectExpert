"""Phase 7 §59.15 Feature Flag port.

The flag registry exposes the documented scope vocabulary
and the documented lifecycle states. Git-versioned feature
declarations and local overrides remain distinct.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Optional


__all__ = [
    "FeatureFlagPort",
    "FeatureFlagScope",
    "FeatureFlagState",
    "InvalidFeatureFlagScopeError",
    "IllegalFeatureFlagTransitionError",
]


class FeatureFlagScope(str, enum.Enum):
    """§59.15 documented scope vocabulary."""

    MACHINE = "machine"
    PROJECT = "project"
    BRANCH = "branch"
    USER = "user"
    DEPLOYMENT_PROFILE = "deploymentProfile"


# Resolution precedence (most specific wins)
_SCOPE_ORDER: tuple[FeatureFlagScope, ...] = (
    FeatureFlagScope.USER,
    FeatureFlagScope.DEPLOYMENT_PROFILE,
    FeatureFlagScope.BRANCH,
    FeatureFlagScope.PROJECT,
    FeatureFlagScope.MACHINE,
)


class FeatureFlagState(str, enum.Enum):
    """§59.15 documented lifecycle states."""

    DISABLED = "disabled"
    ENABLED = "enabled"
    EXPERIMENTAL = "experimental"
    DEPRECATED = "deprecated"


# Documented transition graph
_ALLOWED: Mapping[FeatureFlagState,
                 frozenset[FeatureFlagState]] = {
    FeatureFlagState.DISABLED: frozenset({
        FeatureFlagState.ENABLED,
        FeatureFlagState.EXPERIMENTAL,
    }),
    FeatureFlagState.ENABLED: frozenset({
        FeatureFlagState.DISABLED,
        FeatureFlagState.DEPRECATED,
    }),
    FeatureFlagState.EXPERIMENTAL: frozenset({
        FeatureFlagState.ENABLED,
        FeatureFlagState.DISABLED,
        FeatureFlagState.DEPRECATED,
    }),
    FeatureFlagState.DEPRECATED: frozenset({
        FeatureFlagState.DISABLED,
    }),
}


@dataclass(frozen=True)
class FeatureFlagContext:
    """The context object the flag registry resolves
    against.
    """

    machine_id: str = ""
    project_version: str = ""
    branch: str = ""
    user_id: str = ""
    deployment_profile: str = ""


class InvalidFeatureFlagScopeError(RuntimeError):
    """Raised when a flag declaration omits the scope."""


class IllegalFeatureFlagTransitionError(RuntimeError):
    """Raised when a flag transition is not part of the
    documented lifecycle state machine.
    """

    def __init__(self, current: FeatureFlagState,
                 target: FeatureFlagState) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"illegal-feature-flag-transition: current={current.value} "
            f"target={target.value}"
        )


class FeatureFlagPort(abc.ABC):
    """§59.15 Feature Flag port."""

    @abc.abstractmethod
    def register(self, flag_id: str, *,
                 state: FeatureFlagState,
                 scope: FeatureFlagScope) -> None: ...

    @abc.abstractmethod
    def override(self, flag_id: str, *,
                 state: FeatureFlagState,
                 scope: FeatureFlagScope,
                 scope_key: str) -> None: ...

    @abc.abstractmethod
    def resolve(self, flag_id: str, *,
                context: FeatureFlagContext) -> FeatureFlagState: ...

    @abc.abstractmethod
    def list(self) -> Iterable[tuple[str, FeatureFlagState,
                                     FeatureFlagScope]]: ...

    @abc.abstractmethod
    def transition(self, flag_id: str,
                   target: FeatureFlagState) -> FeatureFlagState: ...

    @abc.abstractmethod
    def serialise(self) -> str: ...