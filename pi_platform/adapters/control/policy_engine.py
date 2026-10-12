"""Phase 7 §59.11 default policy engine factory.

The factory wires the :class:`DefaultPolicyEngine` with
an optional audit log. Focused regression tests build a
bare engine; production callers wire the audit log to the
Phase 7 :class:`AuditLog`.
"""

from __future__ import annotations

from typing import Optional

from pi_platform.core.control.policy import DefaultPolicyEngine


__all__ = ["build_default_policy_engine"]


def build_default_policy_engine(*, audit_log: Optional[object] = None
                                 ) -> DefaultPolicyEngine:
    """Build the default policy engine with optional audit
    wiring.
    """
    engine = DefaultPolicyEngine()
    if audit_log is not None:
        engine.attach_audit_log(audit_log)
    return engine