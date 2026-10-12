"""Phase 8 §56 Enterprise Boundary port.

The boundary is the composition root that wires the four
Phase 8 ports (classification, source permission, egress,
redaction, secret detection) around the Phase 7 Secret /
Policy / Audit foundation. The boundary owns no business
logic of its own; it composes the five ports and exposes
the documented default-policy helpers.
"""

from __future__ import annotations

import abc

from pi_platform.ports.control.policy import Role
from pi_platform.ports.security.classification import ClassificationLevel
from pi_platform.ports.security.detection import SecretFinding
from pi_platform.ports.security.egress import EgressDecision, EgressRequest
from pi_platform.ports.security.permission import SourcePermissionDecision
from pi_platform.ports.security.redaction import RedactionResult
from pi_platform.ports.control.secrets import RedactionContext


__all__ = [
    "EnterpriseBoundaryPort",
    "EnterpriseBoundaryError",
]


class EnterpriseBoundaryError(RuntimeError):
    """Raised only by the boundary when the composed ports
    cannot be initialised; runtime errors per-port remain
    their own typed exceptions.
    """


class EnterpriseBoundaryPort(abc.ABC):
    """§56 Enterprise Boundary composition root."""

    @abc.abstractmethod
    def classify(
        self, document_id: str, raw_level: str, source_id: str = "",
    ) -> ClassificationLevel:
        """Return the resolved classification level."""

    @abc.abstractmethod
    def source_permission(
        self, *, source_id: str, classification: str,
        actor_role: Role, actor_capabilities: Tuple[str, ...] = (),
    ) -> SourcePermissionDecision:
        """Return the source-permission decision."""

    @abc.abstractmethod
    def scan_secrets(
        self, value: str, *, field: str = "value",
    ) -> Tuple[SecretFinding, ...]:
        """Run the secret detector and return findings."""

    @abc.abstractmethod
    def evaluate_egress(
        self, request: EgressRequest,
    ) -> EgressDecision:
        """Evaluate the outbound call through the egress
        port and return the documented
        :class:`EgressDecision`.
        """

    @abc.abstractmethod
    def redact(
        self, value: str, *, channel: RedactionContext,
        classification: str, actor_role: Role,
        actor_capabilities: Tuple[str, ...] = (),
    ) -> RedactionResult:
        """Run the documented two-step pipeline and return
        the :class:`RedactionResult`.
        """

    @abc.abstractmethod
    def serialise(self) -> str:
        """Byte-stable JSON snapshot of every composed
        port's documented state.
        """
