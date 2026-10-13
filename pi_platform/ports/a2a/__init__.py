"""Phase 10 §50 + §51 A2A and reverse-delegation ports.

The v0.8 architecture splits agent interoperability into two interfaces:
MCP for tools and context (§36) and A2A for agent-to-agent collaboration
(§50). The platform MUST expose A2A through a stable port family so that
the protocol never leaks into the core domain model.

This module ships four ports:

- :class:`A2aAdapterPort`   — the inbound dispatch surface used by transports.
- :class:`AgentCardPort`     — read-only Agent Card generation.
- :class:`ReverseDelegationPort`  — deterministic reverse-delegation policy.
- :class:`ExternalAgentPort` — one port per supported external agent identity.

Value types are dataclasses only. The wire protocol (JSON-RPC,
JSON-lines) is translated in :mod:`pi_platform.adapters.a2a.envelope`
and never leaks past the adapter boundary.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence


__all__ = [
    # Errors
    "A2aError",
    "A2aVersionIncompatible",
    "A2aForbidden",
    "A2aUnauthorized",
    "A2aNotFound",
    "A2aUnsupported",
    "A2aLimitExceeded",
    # Value types
    "A2aSpecVersion",
    "A2aTask",
    "A2aMessagePart",
    "A2aMessage",
    "A2aArtifact",
    "A2aTaskStatus",
    "A2aTaskResult",
    "AgentCard",
    "AgentCardSkill",
    "ReverseDelegationTask",
    "ReverseDelegationResult",
    "ReverseDelegationDecision",
    "ExternalAgentMetadata",
    # Ports
    "A2aAdapterPort",
    "AgentCardPort",
    "ReverseDelegationPort",
    "ExternalAgentPort",
]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class A2aError(RuntimeError):
    """Base typed error for A2A operations."""


class A2aVersionIncompatible(A2aError):
    """The peer's advertised A2A spec version disagrees with our pin."""


class A2aForbidden(A2aError):
    """The central policy engine returned DENY for this operation."""


class A2aUnauthorized(A2aError):
    """The actor is missing the required capability."""


class A2aNotFound(A2aError):
    """The requested well-known path or task id does not exist."""


class A2aUnsupported(A2aError):
    """The requested feature is not supported by this deployment."""


class A2aLimitExceeded(A2aError):
    """A documented bound (size, concurrency, retry) was exceeded."""


# ---------------------------------------------------------------------------
# Version value type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class A2aSpecVersion:
    """Tracked A2A spec version.

    Phase 10 pins v1 of the A2A envelope shape used in v0.8 of the
    platform. The wire is a single integer major version; future
    spec revisions add a new value here and a new adapter module.
    """

    major: int
    minor: int = 0

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"{self.major}.{self.minor}"

    def compatible_with(self, other: "A2aSpecVersion") -> bool:
        """Compatibility is major-version equality only."""
        return self.major == other.major

    def as_dict(self) -> dict:
        return {"major": self.major, "minor": self.minor}


# ---------------------------------------------------------------------------
# Message / task value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class A2aMessagePart:
    kind: str  # "text" | "data" | "file" — platform-defined vocabulary
    text: str = ""
    data: Optional[Mapping[str, Any]] = None

    def as_dict(self) -> dict:
        out: dict = {"kind": self.kind}
        if self.kind == "text":
            out["text"] = self.text
        elif self.kind == "data":
            out["data"] = dict(self.data or {})
        return out


@dataclass(frozen=True)
class A2aMessage:
    role: str  # "user" | "agent" | "system"
    parts: Sequence[A2aMessagePart] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"role": self.role, "parts": [p.as_dict() for p in self.parts]}


class A2aTaskStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class A2aTask:
    """Inbound/outbound A2A task envelope.

    The port value type is independent of the wire format. The
    envelope translation happens in ``adapters/a2a/envelope.py``.
    """

    task_id: str
    session_id: Optional[str] = None
    messages: Sequence[A2aMessage] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "taskId": self.task_id,
            "sessionId": self.session_id,
            "messages": [m.as_dict() for m in self.messages],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class A2aArtifact:
    name: str
    mime_type: str
    data: bytes = b""
    text: str = ""

    def as_dict(self) -> dict:
        out: dict = {"name": self.name, "mimeType": self.mime_type}
        if self.text:
            out["text"] = self.text
        else:
            # Do not leak raw bytes via dict; the wire format handles
            # byte-safe encoding. The dict shape is for logging only.
            out["bytes"] = len(self.data)
        return out


@dataclass(frozen=True)
class A2aTaskResult:
    status: A2aTaskStatus
    artifacts: Sequence[A2aArtifact] = field(default_factory=tuple)
    message: Optional[A2aMessage] = None

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "artifacts": [a.as_dict() for a in self.artifacts],
            "message": self.message.as_dict() if self.message is not None else None,
        }


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentCardSkill:
    id: str
    description: str
    tags: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class AgentCard:
    """Public, redacted Agent Card published by the platform."""

    name: str
    description: str
    version: str
    spec_version: A2aSpecVersion
    supported_protocols: Sequence[str] = field(default_factory=tuple)
    skills: Sequence[AgentCardSkill] = field(default_factory=tuple)
    capabilities: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "specVersion": str(self.spec_version),
            "supportedProtocols": list(self.supported_protocols),
            "skills": [{"id": s.id, "description": s.description, "tags": list(s.tags)} for s in self.skills],
            "capabilities": dict(self.capabilities),
        }


# ---------------------------------------------------------------------------
# Reverse delegation value types
# ---------------------------------------------------------------------------


class ReverseDelegationDecision(str, enum.Enum):
    SELECT_AGENT = "select-agent"
    DENY = "deny"
    REQUIRE_APPROVAL = "require-approval"


@dataclass(frozen=True)
class ReverseDelegationTask:
    """Bounded context handed to an external agent.

    Only the Phase 5 :class:`TaskContext` schema values are exposed.
    """

    task_id: str
    reason: str
    bounded_context: Mapping[str, Any]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "taskId": self.task_id,
            "reason": self.reason,
            "boundedContext": dict(self.bounded_context),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ReverseDelegationResult:
    task_id: str
    status: A2aTaskStatus
    output: Mapping[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def as_dict(self) -> dict:
        out: dict = {"taskId": self.task_id, "status": self.status.value, "output": dict(self.output)}
        if self.error is not None:
            out["error"] = self.error
        return out


@dataclass(frozen=True)
class ExternalAgentMetadata:
    """Capabilities declared by an external agent identity.

    The orchestrator selects by ``identity``, never by class name.
    """

    identity: str            # e.g. "claude-code", "generic-mcp"
    display_name: str        # e.g. "Claude Code"
    interface_kind: str      # "a2a" | "cli" | "api" | "mcp"
    api_version: str
    license: str             # SPDX identifier of the external agent itself
    transport_options: Mapping[str, Any] = field(default_factory=dict)
    tags: Sequence[str] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {
            "identity": self.identity,
            "displayName": self.display_name,
            "interfaceKind": self.interface_kind,
            "apiVersion": self.api_version,
            "license": self.license,
            "transportOptions": dict(self.transport_options),
            "tags": list(self.tags),
        }


# ---------------------------------------------------------------------------
# Ports
# ---------------------------------------------------------------------------


class A2aAdapterPort(abc.ABC):
    """Inbound dispatch surface for A2A operations.

    Adapters under :mod:`pi_platform.adapters.a2a` translate wire
    formats to :class:`A2aTask` and call this port. The port never
    sees JSON dicts.
    """

    @abc.abstractmethod
    def invoke(self, *, actor: Mapping[str, Any], task: A2aTask) -> A2aTaskResult:
        """Process an inbound A2A task.

        Implementations enforce the central policy, capability gating,
        and redaction. They MUST raise one of the typed
        :class:`A2aError` subclasses on refusal.
        """

    @abc.abstractmethod
    def supported_spec_version(self) -> A2aSpecVersion:
        """Return the pinned A2A spec version the adapter accepts."""


class AgentCardPort(abc.ABC):
    """Read-only Agent Card generation.

    Implementation MUST redact secret-shaped values from the card and
    MUST raise :class:`A2aNotFound` when the inbound feature flag is
    disabled.
    """

    @abc.abstractmethod
    def build_agent_card(self) -> AgentCard:
        """Build the current Agent Card from capability discovery data."""

    @abc.abstractmethod
    def is_published(self) -> bool:
        """Return True iff the Agent Card route is currently served."""


class ReverseDelegationPort(abc.ABC):
    """Deterministic reverse-delegation decision port.

    The orchestrator calls :meth:`evaluate` with the resolved context
    and the configured :class:`ExternalAgentPort` candidates. The
    policy returns a deterministic :class:`ReverseDelegationDecision`;
    it never calls a language model.
    """

    @abc.abstractmethod
    def evaluate(
        self,
        *,
        actor: Mapping[str, Any],
        task: ReverseDelegationTask,
        candidates: Sequence[ExternalAgentMetadata],
        egress_decision: Mapping[str, Any],
        capabilities: Mapping[str, Any],
    ) -> "ReverseDelegationEvaluation":
        """Run the policy and return the resolved decision."""


@dataclass(frozen=True)
class ReverseDelegationEvaluation:
    decision: ReverseDelegationDecision
    selected_identity: Optional[str] = None
    reason: str = ""

    def as_dict(self) -> dict:
        return {
            "decision": self.decision.value,
            "selectedIdentity": self.selected_identity,
            "reason": self.reason,
        }


class ExternalAgentPort(abc.ABC):
    """One port implementation per supported external agent identity.

    Implementations wrap the agent's officially supported interface
    (A2A, CLI, or API). The orchestrator selects by
    :class:`ExternalAgentMetadata.identity`, not by class name.
    """

    @abc.abstractmethod
    def metadata(self) -> ExternalAgentMetadata:
        """Return the metadata the registry uses to advertise the agent."""

    @abc.abstractmethod
    def submit(self, task: ReverseDelegationTask) -> ReverseDelegationResult:
        """Submit a bounded delegation to the external agent.

        Implementations MUST respect the inbound redaction pipeline
        and the outbound egress classifier that the higher layer has
        already consulted.
        """

    @abc.abstractmethod
    def health(self) -> Mapping[str, Any]:
        """Return a small structured health descriptor."""
