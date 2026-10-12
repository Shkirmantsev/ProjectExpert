"""Phase 8 §56 Egress Decision port.

The egress policy inspects every outbound network call
(MCP, A2A, REST, plugin) before it leaves the platform and
returns a typed ``EgressDecision``. The default policy is
documented in the ``enterprise-security-boundary``
capability spec.
"""

from __future__ import annotations

import abc
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

from pi_platform.ports.control.policy import Role


__all__ = [
    "EgressChannel",
    "EgressRequest",
    "EgressDecision",
    "EgressDecisionPort",
    "EgressDeniedError",
]


class EgressChannel(str, Enum):
    """§56 documented egress channels."""

    LOOPBACK = "loopback"
    LOCAL = "local"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EgressRequest:
    """A single outbound call evaluated by the egress port.

    Attributes:
        url: the destination URL (HTTP / HTTPS / WSS / ...).
        classification: the classification level of the
            payload being transmitted.
        actor_role: the calling actor role.
        capability_requested: the capability that the
            caller requests for the egress (matches the
            Phase 7 capability vocabulary).
        actor_capabilities: the caller's granted capability
            set; used by the egress port to consult the
            Phase 7 Policy Engine with the real actor
            context.
        approval_token: optional approval token for
            high-impact operations (RESTRICTED egress
            overrides per §68.50).
        correlation_id: optional deterministic correlation
            identifier used to chain policy / audit /
            redaction records.
        resource: opaque resource identifier (HTTP path,
            MCP tool name, ...).
    """

    url: str
    classification: str
    actor_role: Role
    capability_requested: str
    actor_capabilities: Tuple[str, ...] = ()
    approval_token: Optional[str] = None
    correlation_id: str = ""
    resource: str = ""


@dataclass(frozen=True)
class EgressDecision:
    """The structured result of an egress evaluation.

    Attributes:
        allowed: ``True`` when the egress is permitted.
        rationale: human-readable rationale string.
        channel: the resolved egress channel
            (:class:`EgressChannel`).
        request: the originating :class:`EgressRequest`.
    """

    allowed: bool
    rationale: str
    channel: EgressChannel
    request: EgressRequest


class EgressDeniedError(RuntimeError):
    """Raised by helpers that prefer exceptions over an
    inline check on the :class:`EgressDecision`.
    """

    def __init__(self, *, rationale: str, request: EgressRequest) -> None:
        self.rationale = rationale
        self.request = request
        super().__init__(
            f"egress-denied: rationale={rationale!r} "
            f"url={request.url!r} classification="
            f"{request.classification!r}"
        )


class EgressDecisionPort(abc.ABC):
    """§56 Egress Decision port."""

    @abc.abstractmethod
    def evaluate(self, request: EgressRequest) -> EgressDecision:
        """Evaluate the ``request`` and return the
        :class:`EgressDecision`. Implementations MUST
        honour the documented default policy and MUST be
        fail-closed (return ``DENY`` on policy-engine
        failure).
        """
        raise NotImplementedError

    def serialise(self) -> str:
        """Byte-stable JSON serialisation of the configured
        localhost set / decision history.
        """

        payload = {
            "channels": [c.value for c in EgressChannel],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
