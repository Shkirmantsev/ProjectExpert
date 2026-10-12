"""Phase 7 §59.6, §59.7, §59.8 Hook Runtime port.

The Hook Runtime fires on the documented lifecycle events
with bounded timeout, cancellation, structured result,
correlation id, audit record, bounded retries if explicitly
configured and the documented failure policies.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional


__all__ = [
    "HookCancelledError",
    "HookDefinition",
    "HookEvent",
    "HookFailurePolicy",
    "HookResult",
    "HookRuntimePort",
    "HookTimeoutError",
]


class HookEvent(str, enum.Enum):
    """§59.6 documented lifecycle events."""

    BEFORE_INGESTION = "beforeIngestion"
    AFTER_INGESTION = "afterIngestion"
    BEFORE_INDEX_UPDATE = "beforeIndexUpdate"
    AFTER_INDEX_UPDATE = "afterIndexUpdate"
    BEFORE_RETRIEVAL = "beforeRetrieval"
    AFTER_RETRIEVAL = "afterRetrieval"
    BEFORE_CONTEXT_ASSEMBLY = "beforeContextAssembly"
    AFTER_CONTEXT_ASSEMBLY = "afterContextAssembly"
    BEFORE_MCP_TOOL = "beforeMcpTool"
    AFTER_MCP_TOOL = "afterMcpTool"
    BEFORE_AGENT_DELEGATION = "beforeAgentDelegation"
    AFTER_AGENT_DELEGATION = "afterAgentDelegation"
    BEFORE_MATERIALIZATION = "beforeMaterialization"
    AFTER_MATERIALIZATION = "afterMaterialization"
    ON_BRANCH_SWITCH = "onBranchSwitch"
    ON_PROJECT_OPEN = "onProjectOpen"
    ON_PROJECT_CLOSE = "onProjectClose"


# Security-sensitive hooks MUST fail closed by default
SECURITY_SENSITIVE_EVENTS: frozenset[HookEvent] = frozenset({
    HookEvent.BEFORE_MATERIALIZATION,
    HookEvent.BEFORE_MCP_TOOL,
    HookEvent.BEFORE_AGENT_DELEGATION,
})

# Observability-only hooks MAY fail open by default
OBSERVABILITY_EVENTS: frozenset[HookEvent] = frozenset({
    HookEvent.AFTER_RETRIEVAL,
    HookEvent.AFTER_CONTEXT_ASSEMBLY,
    HookEvent.AFTER_MCP_TOOL,
})


class HookFailurePolicy(str, enum.Enum):
    """§59.7 failure policies."""

    FAIL_OPEN = "FAIL_OPEN"
    FAIL_CLOSED = "FAIL_CLOSED"
    WARN_ONLY = "WARN_ONLY"
    DISABLE_PLUGIN = "DISABLE_PLUGIN"


@dataclass(frozen=True)
class HookDefinition:
    """The documented §59.6 hook definition shape."""

    hook_id: str
    plugin_id: str
    event: HookEvent
    priority: int = 100
    timeout_ms: int = 1000
    permissions: tuple[str, ...] = ()
    failure_policy: HookFailurePolicy = HookFailurePolicy.WARN_ONLY
    configuration: Mapping[str, str] = field(default_factory=dict)
    version: str = "0.0.0"
    max_retries: int = 0
    callback: Optional[Callable[["HookContext"], "HookResult"]] = None

    def as_dict(self) -> dict:
        return {
            "hookId": self.hook_id,
            "pluginId": self.plugin_id,
            "event": self.event.value,
            "priority": self.priority,
            "timeoutMs": self.timeout_ms,
            "permissions": list(self.permissions),
            "failurePolicy": self.failure_policy.value,
            "configuration": dict(self.configuration),
            "version": self.version,
            "maxRetries": self.max_retries,
        }


@dataclass(frozen=True)
class HookContext:
    """The context object passed to a hook callback.

    Carries the correlation id, the project / version
    context and the input payload. The output is captured
    in the :class:`HookResult`.
    """

    hook_id: str
    plugin_id: str
    event: HookEvent
    correlation_id: str
    project_version: str
    input_payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class HookResult:
    """The documented §59.6 structured hook result."""

    hook_id: str
    plugin_id: str
    event: HookEvent
    duration_ms: int
    status: str  # "ok" | "timeout" | "cancelled" | "error"
    output: Mapping[str, object] = field(default_factory=dict)
    correlation_id: str = ""


class HookTimeoutError(RuntimeError):
    """Raised when a hook exceeds the documented timeout."""


class HookCancelledError(RuntimeError):
    """Raised when a hook is cancelled by the calling data
    plane action."""


class HookRuntimePort(abc.ABC):
    """§59.6 Hook Runtime port."""

    @abc.abstractmethod
    def register(self, definition: HookDefinition) -> None: ...

    @abc.abstractmethod
    def unregister(self, hook_id: str) -> None: ...

    @abc.abstractmethod
    def dispatch(self, event: HookEvent, *,
                correlation_id: str,
                project_version: str,
                input_payload: Mapping[str, object]) -> HookResult: ...

    @abc.abstractmethod
    def list_event_hooks(self, event: HookEvent
                          ) -> Iterable[HookDefinition]: ...

    @abc.abstractmethod
    def cancel(self, correlation_id: str) -> None: ...

    @abc.abstractmethod
    def serialise(self) -> str: ...