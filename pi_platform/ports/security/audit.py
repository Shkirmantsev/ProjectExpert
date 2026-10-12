"""Phase 8 §56 Security Audit port.

The :class:`SecurityAuditPort` wraps the Phase 7
``AuditLogPort`` with the documented
``security.*`` operation vocabulary and the Phase 7
redaction filter. Every emission is best-effort; a failed
Audit Log MUST NOT break the calling data-plane path.
"""

from __future__ import annotations

import abc
import enum
import json
from dataclasses import dataclass
from typing import Tuple


__all__ = [
    "SecurityEvent",
    "SecurityAuditOp",
    "SecurityAuditPort",
    "SecurityAuditError",
]


class SecurityAuditOp(str, enum.Enum):
    """§56 documented security audit operations."""

    DETECT = "security.detect"
    CLASSIFY = "security.classify"
    EGRESS = "security.egress"
    REDACT = "security.redact"
    AUDIT = "security.audit"


@dataclass(frozen=True)
class SecurityEvent:
    """A single security audit event."""

    operation: SecurityAuditOp
    result: str
    resource: str
    correlation_id: str = ""
    actor_id: str = "control-plane"
    project_version: str = "phase-8"
    extra: Tuple[Tuple[str, str], ...] = ()


class SecurityAuditError(RuntimeError):
    """Raised only when a caller opts to fail loud on an
    Audit Log failure; the default recorder swallows the
    error so the data plane is never broken.
    """


class SecurityAuditPort(abc.ABC):
    """§56 Security Audit port."""

    @abc.abstractmethod
    def record(self, event: SecurityEvent) -> None:
        """Emit the event through the wired Audit Log.
        Implementations MUST redact payload values through
        the Phase 7 Secret Provider and MUST be
        best-effort.
        """
        raise NotImplementedError

    def serialise(self) -> str:
        """Byte-stable JSON serialisation."""
        payload = {
            "operations": [op.value for op in SecurityAuditOp],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
