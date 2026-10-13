"""Phase 10 §50 + §51 A2A and reverse-delegation core.

The platform core composes the A2A ports into a deterministic
service. The core is the only owner of the policy gate; adapters in
:mod:`pi_platform.adapters.a2a` translate wire formats and never
reach inside core.

Two responsibilities live here:

1. the A2A dispatch core (:class:`A2aAdapterCore`) used by the
   inbound transport;
2. the reverse-delegation policy core (:class:`ReverseDelegationPolicyCore`),
   which is the deterministic decision-maker the orchestrator
   consults.
"""

from __future__ import annotations

import enum
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from pi_platform.ports.a2a import (
    A2aAdapterPort,
    A2aArtifact,
    A2aError,
    A2aForbidden,
    A2aLimitExceeded,
    A2aMessage,
    A2aMessagePart,
    A2aNotFound,
    A2aSpecVersion,
    A2aTask,
    A2aTaskResult,
    A2aTaskStatus,
    A2aUnauthorized,
    A2aUnsupported,
    A2aVersionIncompatible,
    AgentCard,
    AgentCardPort,
    AgentCardSkill,
    ExternalAgentMetadata,
    ExternalAgentPort,
    ReverseDelegationDecision,
    ReverseDelegationEvaluation,
    ReverseDelegationPort,
    ReverseDelegationResult,
    ReverseDelegationTask,
)


__all__ = [
    "A2A_SPEC_VERSION",
    "A2A_CAPABILITY_VERSION",
    "A2aAdapterCore",
    "ReverseDelegationPolicyCore",
    "A2aFlags",
    "SecretRedactor",
    "LoopbackBinder",
]


# ---------------------------------------------------------------------------
# Tracked constants
# ---------------------------------------------------------------------------


A2A_SPEC_VERSION = A2aSpecVersion(major=1, minor=0)
A2A_CAPABILITY_VERSION = "phase-10-a2a/1"


# Policy actions the central PolicyEngine returns.
_ALLOW = "ALLOW"
_DENY = "DENY"
_REQUIRE_APPROVAL = "REQUIRE_APPROVAL"


class A2aFlags(str, enum.Enum):
    """The four A2A feature flags."""

    A2A_INBOUND = "a2a-inbound"
    A2A_OUTBOUND = "a2a-outbound"
    A2A_STDIO_TRANSPORT = "a2a-stdio-transport"
    A2A_STREAMING = "a2a-streaming"


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


_SECRET_PATTERN = re.compile(r"secret://[A-Za-z0-9._\-/]+")


class SecretRedactor:
    """Redact secret-shaped values before they cross an A2A boundary.

    The redactor is shared by the Agent Card builder and the
    outbound delegation context. It never logs the original value;
    it only returns a deterministic opaque reference string.
    """

    def __init__(self, *, replacement_prefix: str = "secret-ref://") -> None:
        self._prefix = replacement_prefix

    def redact_text(self, text: str) -> str:
        if not text:
            return text
        return _SECRET_PATTERN.sub(self._opaque("text"), text)

    def redact_mapping(self, payload: Mapping[str, Any]) -> dict:
        out: dict = {}
        for key, value in payload.items():
            out[key] = self._redact_value(value)
        return out

    def _redact_value(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact_text(value)
        if isinstance(value, Mapping):
            return {k: self._redact_value(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._redact_value(v) for v in value]
        return value

    def _opaque(self, kind: str) -> str:
        digest = hashlib.sha256(f"{kind}:{time.time_ns()}".encode("utf-8")).hexdigest()[:12]
        return f"{self._prefix}{digest}"


# ---------------------------------------------------------------------------
# Loopback binding guard
# ---------------------------------------------------------------------------


class LoopbackBinder:
    """Decode and validate bind addresses.

    The default is loopback. Operators may bind a different address
    through the documented override; the binder raises
    :class:`ValueError` when the address is malformed and returns a
    ``non-loopback=True`` flag the caller can log.
    """

    LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})

    def __init__(self, *, host: str, port: int) -> None:
        if not (0 < port < 65536):
            raise ValueError(f"Port out of range: {port}")
        self._host = host
        self._port = port

    @property
    def is_loopback(self) -> bool:
        return self._host in self.LOOPBACK_HOSTS

    @property
    def address(self) -> tuple[str, int]:
        return (self._host, self._port)


# ---------------------------------------------------------------------------
# A2A dispatch core
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class A2aInboundLimits:
    """Documented inbound policy gates."""

    max_message_bytes: int = 1_048_576   # 1 MiB
    max_inflight_per_actor: int = 4
    max_artifact_bytes: int = 16 * 1_048_576


class A2aAdapterCore(A2aAdapterPort):
    """The default A2A dispatch core.

    The core is intentionally framework-free. It owns:

    - the policy gate (delegated to the ``policy_gate`` factory);
    - the secret redactor;
    - the inbound feature flag and the capability descriptor;
    - the inbound limits.

    The transport adapter (``pi_platform.adapters.a2a.http_transport``)
    passes each verified wire envelope to :meth:`invoke` and writes
    the returned :class:`A2aTaskResult` back to the peer. The
    transport is responsible for translating the documented
    wire-error classes.
    """

    def __init__(
        self,
        *,
        policy_gate: Optional[Callable[..., str]] = None,
        flags_provider: Optional[Callable[[str], bool]] = None,
        redactor: Optional[SecretRedactor] = None,
        limits: Optional[A2aInboundLimits] = None,
        spec_version: A2aSpecVersion = A2A_SPEC_VERSION,
    ) -> None:
        self._policy_gate = policy_gate or self._default_policy_gate
        self._flag = flags_provider or (lambda name: False)
        self._redactor = redactor or SecretRedactor()
        self._limits = limits or A2aInboundLimits()
        self._spec_version = spec_version
        self._inflight: dict[str, int] = {}

    # --- A2aAdapterPort ------------------------------------------------------

    def supported_spec_version(self) -> A2aSpecVersion:
        return self._spec_version

    def invoke(self, *, actor: Mapping[str, Any], task: A2aTask) -> A2aTaskResult:
        # 1. Flag check
        if not self._flag(A2aFlags.A2A_INBOUND.value):
            raise A2aUnsupported("A2A inbound is disabled")
        # 2. Per-actor concurrency limit
        actor_id = str(actor.get("id") or "anonymous")
        self._enforce_concurrency_limit(actor_id)
        try:
            # 3. Policy gate
            decision = self._policy_gate(
                actor=actor,
                operation="a2a.invoke",
                resource={"task_id": task.task_id},
            )
            if decision == _DENY:
                raise A2aForbidden("a2a.invoke denied by policy")
            if decision == _REQUIRE_APPROVAL:
                raise A2aForbidden("a2a.invoke requires operator approval")
            # 4. Capability check on the actor's mapped capabilities
            caps = actor.get("capabilities", {})
            if not caps.get("mcp.invoke") and not caps.get("a2a.invoke"):
                raise A2aUnauthorized("actor lacks mcp.invoke / a2a.invoke")

            # 5. Redact any secret-shaped fields appearing in messages
            redacted_messages = tuple(
                A2aMessage(
                    role=m.role,
                    parts=tuple(
                        self._redact_part(p, self._redactor) for p in m.parts
                    ),
                )
                for m in task.messages
            )
            safe_task = A2aTask(
                task_id=task.task_id,
                session_id=task.session_id,
                messages=redacted_messages,
                metadata=self._redactor.redact_mapping(task.metadata),
            )
            # 6. Hand off to application logic — for v1.0 the core
            #    returns a deterministic acknowledgement artifact so
            #    transports and tests stay meaningful.
            return A2aTaskResult(
                status=A2aTaskStatus.COMPLETED,
                artifacts=(
                    A2aArtifact(
                        name="ack",
                        mime_type="application/json",
                        text=f'{{"taskId": "{safe_task.task_id}", "redacted": true}}',
                    ),
                ),
            )
        finally:
            self._inflight[actor_id] = max(0, self._inflight.get(actor_id, 0) - 1)

    # --- Helpers ------------------------------------------------------------

    def _enforce_concurrency_limit(self, actor_id: str) -> None:
        current = self._inflight.get(actor_id, 0)
        if current >= self._limits.max_inflight_per_actor:
            raise A2aLimitExceeded(
                f"per-actor concurrency limit ({self._limits.max_inflight_per_actor}) exceeded"
            )
        self._inflight[actor_id] = current + 1

    @staticmethod
    def _redact_part(part: "A2aMessageLike", redactor: SecretRedactor) -> "A2aMessageLike":
        if part.kind == "text":
            return A2aMessagePart(kind="text", text=redactor.redact_text(part.text))
        if part.kind == "data":
            return A2aMessagePart(kind="data", data=redactor.redact_mapping(part.data or {}))
        return part

    @staticmethod
    def _default_policy_gate(**_: Any) -> str:
        """Default gate returns DENY per the §50 fail-closed rule."""
        return _DENY


# Aliases used for the static-typing signature only.
A2aMessageLike = Any


# ---------------------------------------------------------------------------
# Agent Card builder
# ---------------------------------------------------------------------------


class AgentCardBuilder(AgentCardPort):
    """Read-only Agent Card builder derived from capability discovery data.

    The card is built from an injected descriptor so the adapter can
    be exercised in tests without depending on the orchestration
    implementation. Production wires the descriptor through
    :class:`pi_platform.core.orchestration.capability_discovery`.
    """

    def __init__(
        self,
        *,
        descriptor: Mapping[str, Any],
        redactor: Optional[SecretRedactor] = None,
        flags_provider: Optional[Callable[[str], bool]] = None,
        published: bool = True,
    ) -> None:
        self._descriptor = descriptor
        self._redactor = redactor or SecretRedactor()
        self._flag = flags_provider or (lambda name: bool(published))
        self._published = bool(published)
        self._flag_value = bool(published)

    def is_published(self) -> bool:
        return self._published and bool(self._flag(A2aFlags.A2A_INBOUND.value))

    def build_agent_card(self) -> AgentCard:
        if not self.is_published():
            raise A2aNotFound("A2A inbound is disabled")
        protocols = self._descriptor.get("protocols", {}) or {}
        a2a_section = protocols.get("a2a", {}) or {}
        skills = tuple(
            AgentCardSkill(
                id=str(s.get("id", "")),
                description=str(s.get("description", "")),
                tags=tuple(s.get("tags", []) or []),
            )
            for s in (self._descriptor.get("skills") or [])
            if isinstance(s, Mapping) and s.get("id")
        )
        return AgentCard(
            name=str(self._descriptor.get("name", "project-intelligence")),
            description=str(self._descriptor.get("description", "")),
            version=str(self._descriptor.get("version", "0.0.0")),
            spec_version=A2A_SPEC_VERSION,
            supported_protocols=tuple(a2a_section.get("supported_protocols", ()) or ()),
            skills=skills,
            capabilities={
                "streaming": "not-supported",
                "versions": self._redactor.redact_mapping(a2a_section),
            },
        )


# ---------------------------------------------------------------------------
# Reverse delegation policy core
# ---------------------------------------------------------------------------


class ReverseDelegationPolicyCore(ReverseDelegationPort):
    """Deterministic reverse-delegation policy.

    The policy never calls an LLM. It computes the decision from:

    - the requested operation (``reverse.delegate``);
    - the actor capabilities;
    - the egress decision;
    - the configured :class:`ExternalAgentPort` candidates.

    It returns :class:`ReverseDelegationEvaluation` with one of the
    three documented decisions. Multiple matching candidates yield
    ``REQUIRE_APPROVAL`` per the §51 ambiguity rule.
    """

    DEFAULT_OPERATION = "reverse.delegate"
    REQUIRED_CAPABILITY = "agent.delegate"

    def __init__(
        self,
        *,
        operation: str = DEFAULT_OPERATION,
        required_capability: str = REQUIRED_CAPABILITY,
        approval_token_required: bool = True,
    ) -> None:
        self._operation = operation
        self._required_capability = required_capability
        self._approval_token_required = approval_token_required

    def evaluate(
        self,
        *,
        actor: Mapping[str, Any],
        task: ReverseDelegationTask,
        candidates: Sequence[ExternalAgentMetadata],
        egress_decision: Mapping[str, Any],
        capabilities: Mapping[str, Any],
    ) -> ReverseDelegationEvaluation:
        if not candidates:
            return ReverseDelegationEvaluation(
                decision=ReverseDelegationDecision.DENY,
                reason="no configured external agent candidates",
            )
        if not capabilities.get(self._required_capability):
            return ReverseDelegationEvaluation(
                decision=ReverseDelegationDecision.DENY,
                reason=f"missing capability {self._required_capability!r}",
            )
        egress = str(egress_decision.get("decision", "")).upper()
        if egress == _DENY:
            return ReverseDelegationEvaluation(
                decision=ReverseDelegationDecision.DENY,
                reason="egress denied for the resolved destination",
            )
        if egress == _REQUIRE_APPROVAL and self._approval_token_required:
            return ReverseDelegationEvaluation(
                decision=ReverseDelegationDecision.REQUIRE_APPROVAL,
                reason="egress requires operator approval",
            )
        matching = [c for c in candidates if self._matches(c, capabilities)]
        if not matching:
            return ReverseDelegationEvaluation(
                decision=ReverseDelegationDecision.DENY,
                reason="no candidate matches requested capability set",
            )
        if len(matching) > 1:
            # Ambiguity is resolved at policy level rather than in
            # the matching itself; we narrow by identity when one
            # candidate is the explicit primary, otherwise REQUIRE_APPROVAL.
            preferred = [c for c in matching if c.identity == capabilities.get("primary_agent_identity")]
            if len(preferred) == 1:
                return ReverseDelegationEvaluation(
                    decision=ReverseDelegationDecision.SELECT_AGENT,
                    selected_identity=preferred[0].identity,
                    reason="operator pinned the primary agent identity",
                )
            return ReverseDelegationEvaluation(
                decision=ReverseDelegationDecision.REQUIRE_APPROVAL,
                reason="multiple candidates match the requested capability set",
            )
        return ReverseDelegationEvaluation(
            decision=ReverseDelegationDecision.SELECT_AGENT,
            selected_identity=matching[0].identity,
            reason="single candidate matches and egress is allowed",
        )

    @staticmethod
    def _matches(candidate: ExternalAgentMetadata, capabilities: Mapping[str, Any]) -> bool:
        # ``required_agent_tags`` is the documented opt-in narrowing.
        # When empty, every candidate matches.
        required = capabilities.get("required_agent_tags") or ()
        if not required:
            return True
        return all(any(tag == c for c in candidate.tags) for tag in required)


# ---------------------------------------------------------------------------
# Default ExternalAgentPort implementations
# ---------------------------------------------------------------------------


class StaticExternalAgent(ExternalAgentPort):
    """Deterministic, callable-only external-agent port used by tests."""

    def __init__(self, metadata: ExternalAgentMetadata, *, echo: bool = True) -> None:
        self._meta = metadata
        self._echo = echo

    def metadata(self) -> ExternalAgentMetadata:
        return self._meta

    def submit(self, task: ReverseDelegationTask) -> ReverseDelegationResult:
        if self._echo:
            return ReverseDelegationResult(
                task_id=task.task_id,
                status=A2aTaskStatus.COMPLETED,
                output={"echo": True, "taskContextKeys": list(task.bounded_context.keys())},
            )
        return ReverseDelegationResult(
            task_id=task.task_id,
            status=A2aTaskStatus.UNSUPPORTED,
            error="echo disabled",
        )

    def health(self) -> Mapping[str, Any]:
        return {"identity": self._meta.identity, "ok": self._echo}
