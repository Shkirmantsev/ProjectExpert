"""Phase 8 §56 default Security Audit recorder.

The recorder wraps the Phase 7 ``AuditLogPort`` with the
documented ``security.*`` operation vocabulary and the
Phase 7 redaction filter. Every emission is best-effort;
a failed Audit Log MUST NOT break the calling data-plane
path.

When no ``AuditLogPort`` is wired, the recorder still
accepts events; in-memory emission is a no-op so focused
regression tests do not need to wire an audit sink.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pi_platform.core.control.audit import _safe_record
from pi_platform.ports.control.audit import AuditLogPort
from pi_platform.ports.control.secrets import (
    RedactionContext,
    SecretProviderPort,
)
from pi_platform.ports.security.audit import (
    SecurityAuditError,
    SecurityAuditOp,
    SecurityAuditPort,
    SecurityEvent,
)


__all__ = ["DefaultSecurityAuditRecorder"]


@dataclass
class DefaultSecurityAuditRecorder(SecurityAuditPort):
    """§56 default Security Audit recorder."""

    _audit_log: Optional[AuditLogPort] = field(default=None, repr=False)
    _secret_provider: Optional[SecretProviderPort] = field(
        default=None, repr=False,
    )
    _fail_loud: bool = False

    def attach(
        self, audit_log: Optional[AuditLogPort] = None,
        secret_provider: Optional[SecretProviderPort] = None,
    ) -> None:
        if audit_log is not None:
            self._audit_log = audit_log
        if secret_provider is not None:
            self._secret_provider = secret_provider

    def fail_loud(self, enabled: bool) -> None:
        """Switch the recorder between swallow (default) and
        raise on Audit Log failures. Used by focused
        regression tests; production deployments keep the
        default swallow behaviour so the data plane is
        never broken by an audit plumbing error.
        """

        self._fail_loud = bool(enabled)

    def record(self, event: SecurityEvent) -> None:
        try:
            resource = self._redact(event.resource)
            if self._audit_log is not None:
                _safe_record(
                    self._audit_log,
                    operation=event.operation.value,
                    policy_decision=event.result,
                    resource=resource,
                    correlation_id=event.correlation_id,
                    result=event.result,
                )
        except Exception as exc:  # noqa: BLE001 - best-effort
            if self._fail_loud:
                raise SecurityAuditError(
                    f"audit emission failed: {exc!r}",
                ) from exc

    def _redact(self, value: str) -> str:
        """Route the resource through the wired Phase 7
        Secret Provider so resolved secret values cannot
        leak into the audit log.
        """

        if self._secret_provider is None:
            return value
        return self._secret_provider.redact(
            value, context=RedactionContext.AUDIT_PAYLOAD,
        )
