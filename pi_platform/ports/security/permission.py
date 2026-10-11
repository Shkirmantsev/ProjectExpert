"""Phase 8 §56 Source-Level Permission port.

The port maps every ``(source_id, target_consumer_role)``
pair to one of three decisions: ``ALLOW``, ``REDACT`` or
``DENY``. The default policy is documented in the
``enterprise-security-boundary`` capability spec.
"""

from __future__ import annotations

import abc
import enum
import json
from dataclasses import dataclass
from typing import Tuple

from pi_platform.ports.control.policy import Role


__all__ = [
    "SourcePermissionDecisionKind",
    "SourcePermissionDecision",
    "SourcePermissionPort",
    "SourcePermissionError",
]


class SourcePermissionDecisionKind(str, enum.Enum):
    """§56 source-permission decision vocabulary."""

    ALLOW = "ALLOW"
    REDACT = "REDACT"
    DENY = "DENY"


@dataclass(frozen=True)
class SourcePermissionDecision:
    """The structured result of a source-permission check.

    Attributes:
        decision: the resolved decision.
        rule: the matching rule identifier (e.g.
            ``"coding_agent_internal"``); empty string when
            the default rule matches.
        rationale: human-readable rationale string.
        classification: the classification ceiling of the
            source being checked.
    """

    decision: SourcePermissionDecisionKind
    classification: str
    rule: str = ""
    rationale: str = ""

    def is_allowed(self) -> bool:
        return self.decision is SourcePermissionDecisionKind.ALLOW

    def is_redacted(self) -> bool:
        return self.decision is SourcePermissionDecisionKind.REDACT

    def is_denied(self) -> bool:
        return self.decision is SourcePermissionDecisionKind.DENY


class SourcePermissionError(RuntimeError):
    """Raised when the source-permission port cannot be
    consulted (e.g. source_id not registered).
    """


class SourcePermissionPort(abc.ABC):
    """§56 Source-Level Permission port."""

    @abc.abstractmethod
    def evaluate(
        self, *, source_id: str, classification: str,
        actor_role: Role, actor_capabilities: tuple = (),
    ) -> SourcePermissionDecision:
        """Return the source-permission decision for the
        given triple. Implementations MUST honour the
        documented default policy.

        ``actor_capabilities`` carries the caller's granted
        capability set (per the §59.4 vocabulary). An
        actor without ``secret.reference`` reaching
        ``>= INTERNAL`` content MUST be ``DENY`` per the
        capability-delegation Requirement.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def ceiling_for(self, source_id: str) -> str:
        """Return the configured classification ceiling for
        ``source_id``; default ``"PUBLIC"`` when unknown.
        """
        raise NotImplementedError

    def serialise(self) -> str:
        """Byte-stable JSON serialisation."""

        payload = {
            "decisions": [d.value for d in SourcePermissionDecisionKind],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
