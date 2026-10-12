"""Phase 8 §56 default Enterprise Boundary composition root.

The boundary owns no business logic of its own; it
composes the four Phase 8 ports
(classification / source permission / egress /
redaction / secret detection) around the Phase 7 Secret /
Policy / Audit foundation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, Tuple

from pi_platform.ports.control.policy import Role
from pi_platform.ports.control.secrets import RedactionContext
from pi_platform.ports.security.boundary import (
    EnterpriseBoundaryError,
    EnterpriseBoundaryPort,
)
from pi_platform.ports.security.classification import (
    ClassificationLevel,
    SecurityClassificationPort,
)
from pi_platform.ports.security.detection import (
    SecretDetectorPort,
    SecretFinding,
)
from pi_platform.ports.security.egress import (
    EgressDecision,
    EgressDecisionPort,
    EgressRequest,
)
from pi_platform.ports.security.permission import (
    SourcePermissionDecision,
    SourcePermissionPort,
)
from pi_platform.ports.security.redaction import (
    RedactionPipelinePort,
    RedactionResult,
)


__all__ = ["DefaultEnterpriseBoundary"]


@dataclass
class DefaultEnterpriseBoundary(EnterpriseBoundaryPort):
    """§56 default Enterprise Boundary composition root."""

    _classifier: SecurityClassificationPort
    _permission: SourcePermissionPort
    _detector: SecretDetectorPort
    _egress: EgressDecisionPort
    _redaction: RedactionPipelinePort

    def classify(
        self, document_id: str, raw_level: str, source_id: str = "",
    ) -> ClassificationLevel:
        return self._classifier.classify_document(
            document_id, raw_level, source_id,
        ).level

    def source_permission(
        self, *, source_id: str, classification: str,
        actor_role: Role, actor_capabilities: Tuple[str, ...] = (),
    ) -> SourcePermissionDecision:
        return self._permission.evaluate(
            source_id=source_id,
            classification=classification,
            actor_role=actor_role,
            actor_capabilities=actor_capabilities,
        )

    def scan_secrets(
        self, value: str, *, field: str = "value",
    ) -> Tuple[SecretFinding, ...]:
        return self._detector.scan(value, field=field)

    def evaluate_egress(
        self, request: EgressRequest,
    ) -> EgressDecision:
        return self._egress.evaluate(request)

    def redact(
        self, value: str, *, channel: RedactionContext,
        classification: str, actor_role: Role,
        actor_capabilities: Tuple[str, ...] = (),
    ) -> RedactionResult:
        return self._redaction.redact(
            value,
            channel=channel,
            classification=classification,
            actor_role=actor_role,
            actor_capabilities=actor_capabilities,
        )

    def serialise(self) -> str:
        payload = {
            "version": "phase-8.0",
            "classifier": self._classifier.serialise(),
            "permission": self._permission.serialise(),
            "detector": self._detector.serialise(),
            "egress": self._egress.serialise(),
            "redaction": self._redaction.serialise(),
        }
        return json.dumps(payload, sort_keys=True,
                          separators=(",", ":"))
