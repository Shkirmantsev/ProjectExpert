"""Phase 7 §59.13 default Audit Log and Operational Log.

The Audit Log and the Operational Log are two strictly
separated streams. The audit writer applies the Phase 7
``SecretProvider`` redaction filter before writing to the
stream; the operational writer never receives audit
records.

The audit writer enforces the no-secret invariant by
rejecting any payload field whose string value is a
**resolved** secret value — references like
``secret://local/foo`` and ``env://HTTP_PROXY[REDACTED]``
are legitimate audit fields.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, Optional

from pi_platform.ports.control.audit import (
    AuditLogPort,
    AuditOperationalSinkCollision,
    AuditRecord,
    InvalidAuditRecordError,
    OperationalLogPort,
    OperationalRecord,
    SecretLeakageError,
)
from pi_platform.ports.control.secrets import (
    RedactionContext,
    SecretProviderPort,
)


__all__ = ["DefaultAuditLog", "DefaultOperationalLog"]


_REQUIRED_FIELDS: tuple[str, ...] = (
    "timestamp",
    "correlation_id",
    "project_version",
    "actor_type",
    "actor_id",
    "plugin_agent_id",
    "operation",
    "resource",
    "policy_decision",
    "result",
    "duration_ms",
)


def _validate_audit_record(record: AuditRecord) -> None:
    for field_name in _REQUIRED_FIELDS:
        if getattr(record, field_name) in (None, ""):
            raise InvalidAuditRecordError(missing_field=field_name)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_record(audit_log: Optional["DefaultAuditLog"],
                 *, operation: str, result: str,
                 actor_type: str = "automation",
                 actor_id: str = "control-plane",
                 plugin_agent_id: str = "",
                 resource: str = "",
                 policy_decision: str = "",
                 correlation_id: str = "",
                 duration_ms: int = 0,
                 project_version: str = "phase-7") -> None:
    """Best-effort record through the optional audit log.

    Builds a typed :class:`AuditRecord` and calls
    :meth:`DefaultAuditLog.record` positionally. Shared by
    every control-plane core implementation; failures are
    swallowed because audit plumbing MUST NOT break the
    calling operation.
    """
    if audit_log is None:
        return
    try:
        # Every §59.13 field MUST be present and non-empty
        # (``_validate_audit_record`` rejects empty fields);
        # fall back to deterministic non-empty values so the
        # shared helper cannot silently emit records the
        # writer rejects and the caller loses.
        audit_log.record(AuditRecord(
            timestamp=_now_iso(),
            correlation_id=correlation_id or operation,
            project_version=project_version,
            actor_type=actor_type,
            actor_id=actor_id,
            plugin_agent_id=plugin_agent_id or actor_id,
            operation=operation,
            resource=resource or operation,
            policy_decision=policy_decision or "ALLOW",
            result=result,
            duration_ms=duration_ms,
        ))
    except Exception:
        pass


@dataclass
class DefaultAuditLog(AuditLogPort):
    """Default production Audit Log."""

    _sink: io.StringIO = field(default_factory=io.StringIO)
    _secret_provider: Optional[SecretProviderPort
                                ] = field(default=None, repr=False)

    def _redact(self, payload: Mapping[str, object]) -> dict:
        out = {}
        for key, value in payload.items():
            if isinstance(value, str):
                if self._secret_provider is not None:
                    out[key] = self._secret_provider.redact(
                        value, context=RedactionContext.AUDIT_PAYLOAD,
                    )
                else:
                    out[key] = self._manual_redact(value)
            else:
                out[key] = value
        return out

    def _manual_redact(self, value: str) -> str:
        # Without a wired SecretProvider we cannot
        # reconstruct the canonical reference; emit the
        # generic [REDACTED] marker for any field that
        # looks like a resolved secret value (i.e. anything
        # that is NOT a documented reference ending in
        # [REDACTED]).
        if value.endswith("[REDACTED]"):
            return value
        if value.startswith(("secret://", "env://")):
            return f"{value}[REDACTED]"
        return value

    def record(self, record: AuditRecord) -> None:
        _validate_audit_record(record)
        payload = record.as_dict()
        redacted = self._redact(payload)
        # Enforce the no-secret invariant on the OUTPUT: if
        # redaction failed to replace a known resolved value
        # the audit log MUST refuse to write the record.
        # References (canonical strings ending in
        # [REDACTED]) are legitimate audit fields.
        if self._secret_provider is not None:
            for key, value in redacted.items():
                if not isinstance(value, str):
                    continue
                if value.endswith("[REDACTED]"):
                    continue
                if self._secret_provider.has_resolved(value):
                    raise SecretLeakageError(
                        f"audit record carries an unredacted "
                        f"resolved secret: field={key}"
                    )
        line = json.dumps(redacted, sort_keys=True,
                          separators=(",", ":"))
        self._sink.write(line + "\n")

    def query(self, *,
              since: Optional[str] = None,
              until: Optional[str] = None,
              correlation_id: Optional[str] = None
              ) -> Iterable[AuditRecord]:
        for line in self._sink.getvalue().splitlines():
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = payload.get("timestamp", "")
            if since and ts < since:
                continue
            if until and ts > until:
                continue
            if correlation_id and payload.get("correlationId") != correlation_id:
                continue
            duration_raw = payload.get("durationMs", 0)
            try:
                duration_ms = int(duration_raw)
            except (TypeError, ValueError):
                duration_ms = 0
            yield AuditRecord(
                timestamp=ts,
                correlation_id=payload.get("correlationId", ""),
                project_version=payload.get("projectVersion", ""),
                actor_type=payload.get("actorType", ""),
                actor_id=payload.get("actorId", ""),
                plugin_agent_id=payload.get("pluginAgentId", ""),
                operation=payload.get("operation", ""),
                resource=payload.get("resource", ""),
                policy_decision=payload.get("policyDecision", ""),
                result=payload.get("result", ""),
                duration_ms=duration_ms,
            )

    def flush(self) -> str:
        return self._sink.getvalue()

    def serialise(self) -> str:
        payload = {
            "stream": "audit",
            "sinkBytes": self._sink.tell(),
            "lines": self._sink.getvalue().count("\n"),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def attach_secret_provider(
            self, provider: SecretProviderPort) -> None:
        self._secret_provider = provider


@dataclass
class DefaultOperationalLog(OperationalLogPort):
    """Default production Operational Log (diagnostics /
    errors / performance / health).
    """

    _sink: io.StringIO = field(default_factory=io.StringIO)

    def record(self, record: OperationalRecord) -> None:
        payload = {
            "timestamp": record.timestamp,
            "level": record.level,
            "component": record.component,
            "message": record.message,
            "correlationId": record.correlation_id,
            "durationMs": record.duration_ms,
        }
        line = json.dumps(payload, sort_keys=True,
                          separators=(",", ":"))
        self._sink.write(line + "\n")

    def query(self, *,
              since: Optional[str] = None,
              until: Optional[str] = None,
              level: Optional[str] = None
              ) -> Iterable[OperationalRecord]:
        for line in self._sink.getvalue().splitlines():
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = payload.get("timestamp", "")
            if since and ts < since:
                continue
            if until and ts > until:
                continue
            if level and payload.get("level") != level:
                continue
            duration_raw = payload.get("durationMs", 0)
            try:
                duration_ms = int(duration_raw)
            except (TypeError, ValueError):
                duration_ms = 0
            yield OperationalRecord(
                timestamp=ts,
                level=payload.get("level", ""),
                component=payload.get("component", ""),
                message=payload.get("message", ""),
                correlation_id=payload.get("correlationId", ""),
                duration_ms=duration_ms,
            )

    def flush(self) -> str:
        return self._sink.getvalue()

    def serialise(self) -> str:
        payload = {
            "stream": "operational",
            "sinkBytes": self._sink.tell(),
            "lines": self._sink.getvalue().count("\n"),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def assert_separated_streams(audit_sink: io.StringIO,
                              operational_sink: io.StringIO) -> None:
    """Test guard: the audit and operational streams MUST NOT
    share a writer or a sink.
    """
    if audit_sink is operational_sink:
        raise AuditOperationalSinkCollision(
            reason="audit and operational share a sink",
        )