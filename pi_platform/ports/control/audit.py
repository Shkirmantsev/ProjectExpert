"""Phase 7 §59.13 Audit Log vs Operational Log port.

The Audit Log and the Operational Log are two strictly
separated streams. Secret values and unnecessary source
contents MUST never be written into audit records.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional


__all__ = [
    "AuditLogPort",
    "AuditRecord",
    "InvalidAuditRecordError",
    "OperationalLogPort",
    "OperationalRecord",
]


class AuditOperationalSinkCollision(RuntimeError):
    """Raised when the configured audit sink path matches
    the configured operational sink path or when the two
    streams share a writer instance.
    """

    def __init__(self, *, reason: str) -> None:
        self.reason = reason
        super().__init__(f"audit-operational-sink-collision: {reason}")


@dataclass(frozen=True)
class AuditRecord:
    """§59.13 audit record schema."""

    timestamp: str
    correlation_id: str
    project_version: str
    actor_type: str
    actor_id: str
    plugin_agent_id: str
    operation: str
    resource: str
    policy_decision: str
    result: str
    duration_ms: int

    def as_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "correlationId": self.correlation_id,
            "projectVersion": self.project_version,
            "actorType": self.actor_type,
            "actorId": self.actor_id,
            "pluginAgentId": self.plugin_agent_id,
            "operation": self.operation,
            "resource": self.resource,
            "policyDecision": self.policy_decision,
            "result": self.result,
            "durationMs": self.duration_ms,
        }


@dataclass(frozen=True)
class OperationalRecord:
    """Operational log record (diagnostics / errors /
    performance / health).
    """

    timestamp: str
    level: str  # "info" | "warn" | "error" | "debug"
    component: str
    message: str
    correlation_id: str = ""
    duration_ms: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)


class InvalidAuditRecordError(RuntimeError):
    """Raised when an audit record omits a documented §59.13
    field.
    """

    def __init__(self, *, missing_field: str) -> None:
        self.missing_field = missing_field
        super().__init__(
            f"invalid-audit-record: missing field {missing_field!r}"
        )


class SecretLeakageError(RuntimeError):
    """Raised when the audit writer detects a raw secret value
    in the record payload. The writer aborts the write.
    """


class AuditLogPort(abc.ABC):
    """§59.13 Audit Log port."""

    @abc.abstractmethod
    def record(self, record: AuditRecord) -> None: ...

    @abc.abstractmethod
    def query(self, *,
              since: Optional[str] = None,
              until: Optional[str] = None,
              correlation_id: Optional[str] = None
              ) -> Iterable[AuditRecord]: ...

    @abc.abstractmethod
    def flush(self) -> str: ...

    @abc.abstractmethod
    def serialise(self) -> str: ...


class OperationalLogPort(abc.ABC):
    """§59.13 Operational Log port (diagnostics / errors /
    performance / health).
    """

    @abc.abstractmethod
    def record(self, record: OperationalRecord) -> None: ...

    @abc.abstractmethod
    def query(self, *,
              since: Optional[str] = None,
              until: Optional[str] = None,
              level: Optional[str] = None
              ) -> Iterable[OperationalRecord]: ...

    @abc.abstractmethod
    def flush(self) -> str: ...

    @abc.abstractmethod
    def serialise(self) -> str: ...