"""Phase 7 §59.4, §59.5, §59.11, §59.12 default policy engine.

The default engine resolves the role defaults from §59.5
and the documented read-only coding agent capability set
from §59.8. Per-actor capability overrides take precedence
over the role default.

The engine is stateless and thread-safe. Every decision is
recorded in the audit log through the
:class:`AuditLogPort` when one is wired in; the wiring is
optional so focused regression tests do not need to wire an
audit sink.
"""

from __future__ import annotations

import json
import secrets as _secrets
from dataclasses import dataclass, field
from typing import Iterable, Optional

from pi_platform.core.control.audit import _safe_record
from pi_platform.ports.control.policy import (
    ApprovalRequired,
    Capability,
    DEFAULT_ROLE_CAPABILITIES,
    Decision,
    DeniedError,
    PolicyDecision,
    PolicyEnginePort,
    PolicyRequest,
    Role,
    UnknownCapabilityError,
)


__all__ = ["DefaultPolicyEngine"]


# The documented §59.4 vocabulary is the Capability
# enumeration itself. Role defaults are convenience
# initialisers and MUST NOT shrink the vocabulary:
# ``filesystem.read`` is documented vocabulary even though
# no role default grants it.
_KNOWN_CAPABILITIES: frozenset[Capability] = frozenset(Capability)


def _is_known(capability: Capability) -> bool:
    return capability in _KNOWN_CAPABILITIES


@dataclass
class DefaultPolicyEngine(PolicyEnginePort):
    """§59.11 default policy engine."""

    _overrides: dict[str, frozenset[Capability]] = field(default_factory=dict)
    _audit_hook: Optional[object] = field(default=None, repr=False)

    def evaluate(self, request: PolicyRequest) -> PolicyDecision:
        if not _is_known(request.capability):
            raise UnknownCapabilityError(
                f"unknown-capability: capability="
                f"{request.capability.value!r}"
            )
        decision = self._decide(request)
        self._audit(
            operation="policy.evaluate",
            policy_decision=decision.decision.value,
            resource=request.resource,
            correlation_id=request.correlation_id,
            result=decision.decision.value,
        )
        return decision

    def attach_audit_log(self, audit_log: Optional[object]) -> None:
        """Wire an optional audit log (the §59.12 contract);
        every evaluation is then recorded best-effort
        through it without affecting the decision.
        """
        self._audit_hook = audit_log

    def _audit(self, *, operation: str, policy_decision: str,
               resource: str,
               correlation_id: str, result: str) -> None:
        _safe_record(
            self._audit_hook,
            operation=operation,
            policy_decision=policy_decision,
            resource=resource,
            correlation_id=correlation_id,
            result=result,
        )

    def _decide(self, request: PolicyRequest) -> PolicyDecision:
        granted = self._granted_capabilities(request.actor_id,
                                              request.role)
        # High-impact capabilities require an approval token
        # even when the role default grants them.
        requires_approval = request.capability in {
            Capability.KNOWLEDGE_MATERIALIZE,
            Capability.GIT_WRITE,
            Capability.NETWORK_EXTERNAL,
            Capability.SECRET_RESOLVE,
            Capability.MCP_ADMIN,
        }

        if request.capability not in granted:
            # The role does not grant the capability at all;
            # REQUIRE_APPROVAL only applies when the role
            # grants it but a high-impact action needs an
            # explicit approval token. Capabilities outside
            # the granted set are DENY.
            return PolicyDecision(
                decision=Decision.DENY,
                capability=request.capability,
                resource=request.resource,
                policy_decision_rationale=(
                    f"role={request.role.value} does not grant "
                    f"{request.capability.value}"
                ),
            )

        if requires_approval and request.approval_token:
            return PolicyDecision(
                decision=Decision.ALLOW,
                capability=request.capability,
                resource=request.resource,
                policy_decision_rationale=(
                    f"role={request.role.value} + valid approval token "
                    f"for {request.capability.value}"
                ),
            )

        if requires_approval:
            approval_id = "approval-" + _secrets.token_hex(8)
            return PolicyDecision(
                decision=Decision.REQUIRE_APPROVAL,
                capability=request.capability,
                resource=request.resource,
                policy_decision_rationale=(
                    f"role={request.role.value} requires approval "
                    f"for {request.capability.value}"
                ),
                approval_request_id=approval_id,
            )

        return PolicyDecision(
            decision=Decision.ALLOW,
            capability=request.capability,
            resource=request.resource,
            policy_decision_rationale=(
                f"role={request.role.value} grants "
                f"{request.capability.value}"
            ),
        )

    def authorize(self, request: PolicyRequest) -> None:
        decision = self.evaluate(request)
        if decision.decision is Decision.ALLOW:
            return
        if decision.decision is Decision.DENY:
            raise DeniedError(
                f"policy-denied: capability={request.capability.value} "
                f"resource={request.resource!r}; "
                f"{decision.policy_decision_rationale}"
            )
        raise ApprovalRequired(
            capability=request.capability,
            resource=request.resource,
            approval_request_id=decision.approval_request_id,
            rationale=decision.policy_decision_rationale,
        )

    def capabilities_for(self, role: Role) -> tuple[Capability, ...]:
        return DEFAULT_ROLE_CAPABILITIES[role]

    def override(self, actor_id: str,
                 capabilities: Iterable[Capability]) -> None:
        self._overrides[actor_id] = frozenset(capabilities)

    def serialise(self) -> str:
        payload = {
            "version": "0.7.0",
            "roles": {
                role.value: [c.value for c in caps]
                for role, caps in DEFAULT_ROLE_CAPABILITIES.items()
            },
            "overrides": {
                actor_id: sorted(c.value for c in caps)
                for actor_id, caps in sorted(self._overrides.items())
            },
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))

    def _granted_capabilities(self, actor_id: str,
                              role: Role) -> frozenset[Capability]:
        if actor_id in self._overrides:
            return self._overrides[actor_id]
        return frozenset(DEFAULT_ROLE_CAPABILITIES[role])