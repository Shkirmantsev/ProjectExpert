"""Trusted approval boundary.

The boundary issues HMAC-signed approval tokens and verifies them
against an operator signing key. It is the trusted local/operator
gate that :class:`MaterialiseService` and the Phase 6 MCP write
tools must consult before any durable change. The boundary is
intentionally minimal: issue, verify, fail closed. Authorisation
policy (``ALLOW`` / ``DENY`` / ``REQUIRE_APPROVAL``) remains with
:class:`PolicyDecisionPort`; this module is the **authenticity and
scope** gate only.

Design choices:

* ``HmacTrustedApprovalBoundary`` uses HMAC-SHA-256 against an
  operator key supplied at construction time. Tokens are
  ``<payload-b64>.<signature-b64>`` where ``payload`` is a compact
  JSON document describing the grant (``action``, ``repo_root``,
  ``change_ids``, ``iat``, ``nbf``, ``exp``, ``issuer``).
* ``ClosedTrustedApprovalBoundary`` rejects every token. It is the
  default for production deployments until an operator key is
  configured — the platform fails closed.
* The boundary rejects the ``DENY`` policy decision explicitly by
  raising :class:`ApprovalRejected` with ``reason="policy_denied"``
  even before any token work; this closes the gap where the prior
  ``MaterialiseService`` skipped the DENY case and proceeded.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

from ...ports import (
    ApprovalGrant,
    ApprovalRejected,
    ApprovalRequest,
    PolicyDecision,
    PolicyDecisionPort,
    TrustedApprovalBoundary,
)

__all__ = [
    "HmacTrustedApprovalBoundary",
    "ClosedTrustedApprovalBoundary",
]


log = logging.getLogger(__name__)


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    pad = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + pad)


class HmacTrustedApprovalBoundary(TrustedApprovalBoundary):
    """HMAC-SHA-256 trusted approval boundary.

    The operator signing key is supplied at construction time. The
    boundary refuses to operate without one (``key=None`` ⇒
    ``ApprovalRejected("no_issuer_key")`` for every token and every
    issue call). A process-wide key may be inherited from the
    ``PI_OPERATOR_APPROVAL_KEY`` environment variable when no key is
    passed explicitly; the platform CLI must refuse to start in
    production without it (the default :class:`MaterialiseService`
    wiring still defaults to :class:`ClosedTrustedApprovalBoundary`).
    """

    def __init__(self, *,
                 key: Optional[bytes] = None,
                 clock=None):
        resolved = key
        if resolved is None:
            env = os.environ.get("PI_OPERATOR_APPROVAL_KEY")
            if env:
                resolved = env.encode("utf-8")
        self._key = resolved
        # ``clock`` is a unit test seam for deterministic timestamps.
        self._clock = clock or time.time

    def has_key(self) -> bool:
        return self._key is not None

    def issue(self, request: ApprovalRequest, *, ttl_seconds: int = 300,
              issuer: str = "operator") -> str:
        if self._key is None:
            raise ApprovalRejected(
                "no_issuer_key",
                "no operator signing key configured; cannot issue approval",
            )
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        now = int(self._clock())
        issued = request.issued_at or now
        payload = {
            "action": request.action,
            "repoRoot": request.repo_root,
            "changeIds": list(request.change_ids),
            "iat": issued,
            "nbf": issued,
            "exp": issued + ttl_seconds,
            "issuer": issuer,
        }
        payload_bytes = json.dumps(payload, sort_keys=True,
                                  separators=(",", ":")).encode("utf-8")
        signature = hmac.new(self._key, payload_bytes,
                            hashlib.sha256).digest()
        return f"{_b64encode(payload_bytes)}.{_b64encode(signature)}"

    def verify(self, request: ApprovalRequest,
               token: Optional[str]) -> ApprovalGrant:
        if token is None or token == "":
            raise ApprovalRejected("missing_token")
        if self._key is None:
            raise ApprovalRejected(
                "no_issuer_key",
                "no operator signing key configured; cannot verify approval",
            )
        try:
            payload_text, signature_text = token.split(".", 1)
        except ValueError as exc:
            raise ApprovalRejected(
                "malformed_token", f"token missing payload/signature: {exc}",
            ) from None
        try:
            payload_bytes = _b64decode(payload_text)
            signature = _b64decode(signature_text)
        except Exception as exc:
            raise ApprovalRejected(
                "malformed_token", f"token decoding failed: {exc}",
            ) from None
        expected = hmac.new(self._key, payload_bytes,
                           hashlib.sha256).digest()
        if not hmac.compare_digest(expected, signature):
            raise ApprovalRejected("forged_signature")
        try:
            payload = json.loads(payload_bytes)
        except Exception as exc:
            raise ApprovalRejected(
                "malformed_token", f"payload is not valid JSON: {exc}",
            ) from None
        if payload.get("action") != request.action:
            raise ApprovalRejected("wrong_action")
        if payload.get("repoRoot") != request.repo_root:
            raise ApprovalRejected("wrong_repository")
        grant_change_ids = tuple(payload.get("changeIds") or ())
        # Allow empty grant (i.e. "any change ids in scope") to satisfy
        # any change request — but a populated grant must be a superset
        # of the requested change ids, never a subset that would bind
        # the call to fewer changes than it actually attempts.
        request_change_ids = tuple(request.change_ids)
        if grant_change_ids and not set(request_change_ids).issubset(
                set(grant_change_ids)):
            raise ApprovalRejected("change_superset_mismatch")
        now = int(self._clock())
        if now < int(payload.get("nbf", 0)):
            raise ApprovalRejected("not_yet_valid")
        if now >= int(payload.get("exp", 0)):
            raise ApprovalRejected("expired")
        grant = ApprovalGrant(
            request=request,
            not_before=int(payload["nbf"]),
            not_after=int(payload["exp"]),
            issuer=str(payload.get("issuer", "")),
        )
        log.debug(
            "approval verified: action=%s repo=%s issuer=%s exp=%s",
            request.action, request.repo_root, grant.issuer, grant.not_after,
        )
        return grant


class ClosedTrustedApprovalBoundary(TrustedApprovalBoundary):
    """Default-closed boundary.

    No token is ever accepted. Used when the operator key has not
    been configured; the platform fails closed. Every verify() call
    raises :class:`ApprovalRejected` with ``reason="missing_token"``;
    every issue() call raises :class:`ApprovalRejected` with
    ``reason="no_issuer_key"``.
    """

    def issue(self, request: ApprovalRequest, *, ttl_seconds: int = 300,
              issuer: str = "operator") -> str:
        raise ApprovalRejected(
            "no_issuer_key",
            "trusted approval boundary is closed; configure an "
            "operator signing key (PI_OPERATOR_APPROVAL_KEY) or "
            "wire HmacTrustedApprovalBoundary with a key",
        )

    def verify(self, request: ApprovalRequest,
               token: Optional[str]) -> ApprovalGrant:
        if token is None or token == "":
            raise ApprovalRejected(
                "missing_token",
                "approval boundary is closed; supply a token issued "
                "by a trusted operator",
            )
        raise ApprovalRejected(
            "missing_token",
            "approval boundary is closed; cannot verify caller tokens",
        )


def deny_if_denied(policy: PolicyDecisionPort, action: str) -> None:
    """Reject :data:`PolicyDecision.DENY` unconditionally.

    :class:`MaterialiseService` and the Phase 6 write tools call this
    helper before any approval work so the DENY case is handled even
    when no approval token is presented. Closes the gap where the prior
    implementation only checked REQUIRE_APPROVAL.
    """
    decision = policy.decide(action)
    if decision is PolicyDecision.DENY:
        raise ApprovalRejected(
            "policy_denied", f"policy denied action {action!r}",
        )
    return None