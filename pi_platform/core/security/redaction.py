"""Phase 8 §56 default Redaction Pipeline.

The pipeline runs the documented two ordered steps:

1. Phase 7 ``SecretProvider.redact`` (which replaces any
   resolved secret value with ``<ref>[REDACTED]``).
2. Classification-driven redaction: when the ``actor_role``
   is ``VIEWER`` or ``CODING_AGENT_READ_ONLY`` and the
   payload classification is ``>= INTERNAL``, the chunk
   body is replaced with ``[REDACTED:<LEVEL>]``. The
   redaction step is also triggered for actors without
   the ``secret.reference`` capability reaching
   ``>= INTERNAL`` content per the §56 capability
   delegation Requirement.

After the second step the pipeline asserts the
no-resolved-value invariant by calling
``SecretProvider.has_resolved``; a violation raises
:class:`RedactionFailureError`.

Every invocation emits an :class:`AuditRecord` through the
wired :class:`SecurityAuditPort`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, Tuple

from pi_platform.ports.control.policy import Role
from pi_platform.ports.control.secrets import (
    RedactionContext,
    SecretProviderPort,
)
from pi_platform.ports.security.audit import (
    SecurityAuditOp,
    SecurityAuditPort,
    SecurityEvent,
)
from pi_platform.ports.security.classification import (
    DEFAULT_LEVEL,
    RANK,
    coerce_level,
)
from pi_platform.ports.security.redaction import (
    RedactionFailureError,
    RedactionPipelinePort,
    RedactionResult,
    RedactionStep,
)


__all__ = ["DefaultRedactionPipeline"]


# Module-level constants avoid Python's name-mangling
# for double-underscore prefixed identifiers used inside
# @dataclass methods.
SECRET_PROVIDER_STEP = RedactionStep(
    name="phase7_secret_provider",
    description=(
        "Phase 7 Secret Provider redact(value, channel=...) "
        "replaces resolved secret values with their "
        "redacted reference form"
    ),
)
CLASSIFICATION_STEP = RedactionStep(
    name="phase8_classification_driven",
    description=(
        "Phase 8 classification-driven redaction replaces "
        "INTERNAL+ content reaching VIEWER / "
        "CODING_AGENT_READ_ONLY with [REDACTED:<LEVEL>]"
    ),
)


_RESTRICTED_CONSUMERS = (
    Role.VIEWER,
    Role.CODING_AGENT_READ_ONLY,
)


@dataclass
class DefaultRedactionPipeline(RedactionPipelinePort):
    """§56 default Redaction Pipeline."""

    _secret_provider: SecretProviderPort
    _audit: Optional[SecurityAuditPort] = field(default=None, repr=False)

    def attach_audit(self, audit: SecurityAuditPort) -> None:
        self._audit = audit

    def steps(self) -> Tuple[RedactionStep, ...]:
        return (SECRET_PROVIDER_STEP, CLASSIFICATION_STEP)

    def redact(
        self, value: str, *, channel: RedactionContext,
        classification: str, actor_role: Role,
        actor_capabilities: Tuple[str, ...] = (),
    ) -> RedactionResult:
        if value is None:
            value = ""

        # Step 1: Phase 7 Secret Provider redaction.
        redacted = self._secret_provider.redact(value, context=channel)

        # Step 2: classification-driven redaction. The
        # redaction step fires for the documented
        # VIEWER / CODING_AGENT_READ_ONLY consumers, and
        # also for any consumer that lacks the
        # ``secret.reference`` capability on
        # ``>= INTERNAL`` content (capability delegation
        # requirement).
        classification_level = coerce_level(classification)
        is_internal_or_above = (
            classification_level != DEFAULT_LEVEL
        )
        consumer_restricted = actor_role in _RESTRICTED_CONSUMERS
        lacks_secret_reference = (
            "secret.reference"
            not in set(actor_capabilities or ())
        )
        redact_classification = (
            is_internal_or_above
            and (consumer_restricted
                 or lacks_secret_reference)
        )
        target = redacted
        if redact_classification:
            target = f"[REDACTED:{classification_level.value}]"

        # No-resolved-value invariant. The provider
        # exposes ``has_resolved`` on the port since
        # Phase 8; the default returns ``False`` so the
        # invariant stays enforceable on every provider.
        if self._secret_provider.has_resolved(target):
            raise RedactionFailureError(
                reason="leak", value=target,
            )

        if self._audit is not None:
            try:
                self._audit.record(SecurityEvent(
                    operation=SecurityAuditOp.REDACT,
                    result="REDACTED" if redact_classification
                    else "PASSTHROUGH",
                    resource=f"classification={classification}",
                ))
            except Exception:
                # Audit emission MUST be best-effort.
                pass

        return RedactionResult(
            value=target,
            steps=self.steps(),
            audit_emitted=self._audit is not None,
        )

    def serialise(self) -> str:
        payload = {
            "version": "phase-8.0",
            "steps": [
                {"name": s.name, "description": s.description}
                for s in self.steps()
            ],
            "restricted_consumers": [r.value for r in _RESTRICTED_CONSUMERS],
        }
        return json.dumps(payload, sort_keys=True,
                          separators=(",", ":"))
