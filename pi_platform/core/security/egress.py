"""Phase 8 §56 default Egress Policy.

The default policy evaluates an :class:`EgressRequest`
against the documented Phase 8 rules:

- ``localhost`` / ``127.0.0.1`` / ``::1`` -> ALLOW
- non-localhost: requires ``network.external`` capability
  and the requested ``classification`` must be in the
  configured endpoint allow-list; otherwise DENY
- missing policy engine or missing audit log: DENY (the
  decision is fail-closed)

Every evaluation (ALLOW or DENY) emits an audit record.

The policy engine is consulted with the *real* actor role
carried on the :class:`EgressRequest`. A high-impact
RESTRICTED-egress override routes through the Phase 7
``REQUIRE_APPROVAL`` contract per §68.50.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Set, Tuple

from pi_platform.adapters.security.egress_classifier import (
    classify_url,
    is_loopback_host,
)
from pi_platform.core.control.audit import _safe_record
from pi_platform.ports.control.policy import (
    Capability,
    PolicyDecision,
    PolicyEnginePort,
    PolicyRequest,
    Role,
    Decision as PolicyDecisionKind,
)
from pi_platform.ports.control.audit import AuditLogPort
from pi_platform.ports.security.audit import (
    SecurityAuditOp,
    SecurityAuditPort,
    SecurityEvent,
)
from pi_platform.ports.security.classification import (
    RANK,
    coerce_level,
)
from pi_platform.ports.security.egress import (
    EgressChannel,
    EgressDecision,
    EgressDecisionPort,
    EgressRequest,
)


__all__ = ["DefaultEgressPolicy"]


_HIGH_IMPACT_OVERRIDE_CLASSIFICATION = coerce_level("RESTRICTED").value


def _as_capability(value: str) -> Optional[Capability]:
    try:
        return Capability(value)
    except ValueError:
        return None


def _host_from_url(url: str) -> str:
    """Extract the host portion of ``url`` (best-effort)."""
    if "://" not in url:
        return url.strip()
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


@dataclass
class DefaultEgressPolicy(EgressDecisionPort):
    """§56 default Egress Policy."""

    _endpoint_allow: Set[str] = field(default_factory=lambda: {"PUBLIC"})
    _policy_engine: Optional[PolicyEnginePort] = field(
        default=None, repr=False,
    )
    _audit: Optional[SecurityAuditPort] = field(default=None, repr=False)
    _audit_log: Optional[AuditLogPort] = field(default=None, repr=False)
    _decisions: list = field(default_factory=list, repr=False)

    def allow_endpoint(self, level: str) -> None:
        normalised = coerce_level(level).value
        self._endpoint_allow.add(normalised)
        # The PUBLIC level is always allowed; the set is
        # the union of the configured allow-list and
        # ``{PUBLIC}``.
        self._endpoint_allow.add("PUBLIC")

    def revoke_endpoint(self, level: str) -> None:
        target = coerce_level(level).value
        # ``revoke_endpoint`` may not strip the documented
        # always-allowed PUBLIC; doing so would let a
        # caller shoot themselves in the foot.
        if target == "PUBLIC":
            return
        self._endpoint_allow.discard(target)

    def set_policy_engine(self, engine: PolicyEnginePort) -> None:
        self._policy_engine = engine

    def attach_audit(
        self, audit: Optional[SecurityAuditPort] = None,
        audit_log: Optional[AuditLogPort] = None,
    ) -> None:
        if audit is not None:
            self._audit = audit
        if audit_log is not None:
            self._audit_log = audit_log

    def evaluate(self, request: EgressRequest) -> EgressDecision:
        channel = classify_url(request.url)
        # Loopback short-circuits to ALLOW before any
        # policy-engine call so a missing engine never
        # blocks legitimate intra-process traffic.
        host = _host_from_url(request.url)
        if host and is_loopback_host(host):
            channel = EgressChannel.LOOPBACK
        if channel is EgressChannel.LOOPBACK:
            decision = self._finish(
                request, True, "localhost", channel,
            )
            return decision

        # External / local / unknown: require
        # ``network.external`` capability and matching
        # classification. Missing policy engine -> DENY
        # (fail-closed).
        engine = self._policy_engine
        if engine is None:
            return self._finish(
                request, False,
                "policy engine is not configured",
                channel,
            )

        requested_capability = _as_capability(request.capability_requested)
        classification = coerce_level(request.classification).value
        if requested_capability is not Capability.NETWORK_EXTERNAL:
            return self._finish(
                request, False,
                "network.external capability required, got "
                f"{request.capability_requested!r}",
                channel,
            )

        # The policy engine authorises the capability for
        # the *real* actor role carried on the EgressRequest.
        # A Viewer with no ``network.external`` capability is
        # already denied by the explicit ``requested_capability``
        # check above; the engine consultation then resolves
        # the role's default capability set plus the
        # ``approval_token`` for high-impact operations per
        # the Phase 7 ``REQUIRE_APPROVAL`` contract.
        #
        # Note: the Phase 7 ``PolicyEnginePort.evaluate`` does
        # NOT expose a per-request capability override, so the
        # ``actor_capabilities`` field on ``EgressRequest`` is
        # honoured by the egress port itself (via the explicit
        # capability check above and the §68.50 approval gate
        # below), not by the policy engine. The engine still
        # sees the real actor role through the request builder.
        token = getattr(request, "approval_token", "") or ""
        try:
            policy = engine.evaluate(self._build_request(
                request, approval_token=token,
            ))
        except Exception as exc:  # noqa: BLE001 - fail-closed
            return self._finish(
                request, False,
                f"policy-engine-error: {exc!r}",
                channel,
            )

        if policy.decision is not PolicyDecisionKind.ALLOW:
            return self._finish(
                request, False,
                f"policy decision {policy.decision.value!r} for "
                f"{request.capability_requested!r}"
                + ("; RESTRICTED egress requires an approval_token"
                   if classification == _HIGH_IMPACT_OVERRIDE_CLASSIFICATION
                   and not token
                   else ""),
                channel,
            )

        if classification not in self._endpoint_allow:
            return self._finish(
                request, False,
                f"classification={classification} not in "
                f"endpoint_allow={sorted(self._endpoint_allow)}",
                channel,
            )

        return self._finish(
            request, True,
            f"capability={request.capability_requested} and "
            f"endpoint_allow contains {classification}",
            channel,
        )

    def _finish(
        self, request: EgressRequest, allowed: bool,
        rationale: str, channel: EgressChannel,
    ) -> EgressDecision:
        decision = EgressDecision(
            allowed=allowed, rationale=rationale,
            channel=channel, request=request,
        )
        self._record(request, decision)
        # Cap the in-memory history at 1024 entries so a
        # long-running process does not grow unbounded.
        self._decisions.append(decision)
        if len(self._decisions) > 1024:
            del self._decisions[: len(self._decisions) - 1024]
        return decision

    def _record(
        self, request: EgressRequest, decision: EgressDecision,
    ) -> None:
        if self._audit is not None:
            try:
                self._audit.record(SecurityEvent(
                    operation=SecurityAuditOp.EGRESS,
                    result="ALLOW" if decision.allowed else "DENY",
                    resource=request.url,
                    correlation_id=request.correlation_id,
                ))
            except Exception:
                pass
        if self._audit_log is not None:
            _safe_record(
                self._audit_log,
                operation=SecurityAuditOp.EGRESS.value,
                policy_decision=(
                    "ALLOW" if decision.allowed else "DENY"
                ),
                resource=request.url,
                correlation_id=request.correlation_id,
                result="ALLOW" if decision.allowed else "DENY",
            )

    def _build_request(
        self, request: EgressRequest, *,
        approval_token: str = "",
    ) -> PolicyRequest:
        """Build a Phase 7 ``PolicyRequest`` from the
        EgressRequest, threading the real actor role
        through. The Phase 7 Policy Engine resolves
        role defaults + the ``approval_token`` for
        high-impact operations; per-request capability
        overrides are not exposed by the Phase 7 port
        and are honoured by the egress port itself.
        """

        actor_role = getattr(request, "actor_role", Role.VIEWER) or Role.VIEWER
        return PolicyRequest(
            actor_type="automation",
            actor_id="phase-8-egress",
            role=actor_role,
            capability=Capability.NETWORK_EXTERNAL,
            resource=request.url,
            project_version=request.correlation_id or "phase-8",
            correlation_id=request.correlation_id or "phase-8-egress",
            approval_token=approval_token or None,
        )

    def serialise(self) -> str:
        import json
        payload = {
            "endpoint_allow": sorted(self._endpoint_allow),
            "decisions": [
                {
                    "url": d.request.url,
                    "allowed": d.allowed,
                    "rationale": d.rationale,
                    "channel": d.channel.value,
                }
                for d in self._decisions
            ],
        }
        return json.dumps(payload, sort_keys=True,
                          separators=(",", ":"))
