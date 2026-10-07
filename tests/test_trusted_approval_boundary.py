"""Phase 6 prerequisite 1 — trusted approval boundary tests.

These tests are the contract for the trusted write boundary that
guards :class:`MaterialiseService.materialise_durable_changes`
(and, by extension, the Phase 6 ``project.materialize_knowledge``
and ``project.refresh_sources`` MCP tools). Each negative case is
the exact failure mode the v0.8 architecture §48 supply-chain
security invariants require: missing, forged, expired,
wrong-scope, wrong-action, and policy-DENY approvals must all
fail closed.

The tests are deterministic: a fixed HMAC key, an injected clock,
and the in-process ``HmacTrustedApprovalBoundary`` adapter keep
the verification reproducible across two consecutive runs.
"""

from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from pi_platform.core.sync import MaterialiseService
from pi_platform.core.sync.policy_stub import PolicyDecisionStub
from pi_platform.core.sync.trusted_approval import (
    ClosedTrustedApprovalBoundary,
    HmacTrustedApprovalBoundary,
)
from pi_platform.ports import (
    ApprovalRejected,
    ApprovalRequest,
    PolicyDecision,
)


__all__ = ["TrustedApprovalBoundaryTests", "MaterialiseBoundaryIntegrationTests"]


class _FixedClock:
    """Deterministic clock for token expiry tests."""

    def __init__(self, value: int = 1_700_000_000) -> None:
        self.value = value

    def __call__(self) -> int:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += seconds


class TrustedApprovalBoundaryTests(unittest.TestCase):
    """Unit tests for the HMAC trusted approval boundary itself."""

    KEY = b"deterministic-test-key-32-bytes-long"

    def setUp(self) -> None:
        self.clock = _FixedClock()
        self.boundary = HmacTrustedApprovalBoundary(
            key=self.KEY, clock=self.clock,
        )
        self.repo = "/tmp/example-project"
        self.request = ApprovalRequest(
            action="materialise", repo_root=self.repo,
            change_ids=("rc-1", "rc-2"),
        )

    def test_issue_then_verify_round_trip_succeeds(self) -> None:
        token = self.boundary.issue(self.request, ttl_seconds=60)
        grant = self.boundary.verify(self.request, token)
        self.assertEqual(grant.request.action, "materialise")
        self.assertEqual(grant.issuer, "operator")
        self.assertGreater(grant.not_after, grant.not_before)

    def test_verify_rejects_missing_token(self) -> None:
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(self.request, None)
        self.assertEqual(cm.exception.reason, "missing_token")

    def test_verify_rejects_empty_token(self) -> None:
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(self.request, "")
        self.assertEqual(cm.exception.reason, "missing_token")

    def test_verify_rejects_forged_signature(self) -> None:
        token = self.boundary.issue(self.request, ttl_seconds=60)
        payload, signature = token.split(".", 1)
        # Flip one byte in the signature by truncating it.
        forged = f"{payload}.{signature[:-1]}A"
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(self.request, forged)
        self.assertEqual(cm.exception.reason, "forged_signature")

    def test_verify_rejects_token_signed_with_different_key(self) -> None:
        other_boundary = HmacTrustedApprovalBoundary(
            key=b"completely-different-key-also-32-bytes", clock=self.clock,
        )
        token = other_boundary.issue(self.request, ttl_seconds=60)
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(self.request, token)
        self.assertEqual(cm.exception.reason, "forged_signature")

    def test_verify_rejects_expired_token(self) -> None:
        token = self.boundary.issue(self.request, ttl_seconds=30)
        self.clock.advance(31)
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(self.request, token)
        self.assertEqual(cm.exception.reason, "expired")

    def test_verify_rejects_token_not_yet_valid(self) -> None:
        # Issue a token with a future not_before by setting clock
        # far in the past at issue and then verify from clock=0.
        self.clock.value = 2_000_000_000
        token = self.boundary.issue(self.request, ttl_seconds=300)
        self.clock.value = 1_500_000_000  # before issue
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(self.request, token)
        self.assertEqual(cm.exception.reason, "not_yet_valid")

    def test_verify_rejects_wrong_action(self) -> None:
        token = self.boundary.issue(self.request, ttl_seconds=60)
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(
                ApprovalRequest(action="refresh_sources",
                               repo_root=self.repo),
                token,
            )
        self.assertEqual(cm.exception.reason, "wrong_action")

    def test_verify_rejects_wrong_repository(self) -> None:
        token = self.boundary.issue(self.request, ttl_seconds=60)
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(
                ApprovalRequest(action="materialise",
                               repo_root="/tmp/other-project"),
                token,
            )
        self.assertEqual(cm.exception.reason, "wrong_repository")

    def test_verify_rejects_change_superset_mismatch(self) -> None:
        # Grant covers only rc-1; request asks for rc-1 AND rc-2.
        token = self.boundary.issue(
            ApprovalRequest(action="materialise", repo_root=self.repo,
                            change_ids=("rc-1",)),
            ttl_seconds=60,
        )
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(
                ApprovalRequest(action="materialise", repo_root=self.repo,
                                change_ids=("rc-1", "rc-2")),
                token,
            )
        self.assertEqual(cm.exception.reason, "change_superset_mismatch")

    def test_verify_allows_empty_request_change_ids_with_populated_grant(self):
        # An empty change_id request ("no specific changes; I'll list
        # them after I get the token") must not bind the verifier to
        # a subset — it must be acceptable when the grant covers the
        # empty superset trivially.
        token = self.boundary.issue(self.request, ttl_seconds=60)
        grant = self.boundary.verify(
            ApprovalRequest(action="materialise", repo_root=self.repo),
            token,
        )
        self.assertEqual(grant.request.action, "materialise")

    def test_verify_rejects_malformed_token(self) -> None:
        with self.assertRaises(ApprovalRejected) as cm:
            self.boundary.verify(self.request, "not-a-valid-token")
        self.assertEqual(cm.exception.reason, "malformed_token")

    def test_boundary_without_key_rejects_everything(self) -> None:
        keyless = HmacTrustedApprovalBoundary(key=None, clock=self.clock)
        with self.assertRaises(ApprovalRejected) as cm:
            keyless.issue(self.request)
        self.assertEqual(cm.exception.reason, "no_issuer_key")
        with self.assertRaises(ApprovalRejected) as cm:
            keyless.verify(self.request, "any.token")
        self.assertEqual(cm.exception.reason, "no_issuer_key")

    def test_closed_boundary_rejects_everything(self) -> None:
        closed = ClosedTrustedApprovalBoundary()
        with self.assertRaises(ApprovalRejected) as cm:
            closed.issue(self.request)
        self.assertEqual(cm.exception.reason, "no_issuer_key")
        with self.assertRaises(ApprovalRejected) as cm:
            closed.verify(self.request, None)
        self.assertEqual(cm.exception.reason, "missing_token")
        with self.assertRaises(ApprovalRejected) as cm:
            closed.verify(self.request, "anything-at-all")
        self.assertEqual(cm.exception.reason, "missing_token")


class MaterialiseBoundaryIntegrationTests(unittest.TestCase):
    """Integration tests: MaterialiseService with the boundary."""

    KEY = b"integration-test-key-also-32-bytes!"

    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.clock = _FixedClock()
        self.boundary = HmacTrustedApprovalBoundary(
            key=self.KEY, clock=self.clock,
        )

    def _service(self, *, policy: PolicyDecisionStub | None = None
                 ) -> MaterialiseService:
        return MaterialiseService(
            policy=policy or PolicyDecisionStub(),
            boundary=self.boundary,
        )

    def _request(self, change_ids: tuple = ()) -> ApprovalRequest:
        return ApprovalRequest(
            action="materialise", repo_root=str(self.tmp),
            change_ids=change_ids,
        )

    def test_default_service_fails_closed_without_boundary(self) -> None:
        service = MaterialiseService()
        with self.assertRaises(ApprovalRejected) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token="anything",
            )
        self.assertEqual(cm.exception.reason, "missing_token")

    def test_policy_deny_is_rejected_unconditionally(self) -> None:
        denying_policy = PolicyDecisionStub(deny={"materialise"})
        service = self._service(policy=denying_policy)
        token = self.boundary.issue(self._request(), ttl_seconds=60)
        with self.assertRaises(ApprovalRejected) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token=token,
            )
        self.assertEqual(cm.exception.reason, "policy_denied")

    def test_missing_token_for_require_approval_raises_approval_required(
            self) -> None:
        service = self._service()
        with self.assertRaises(Exception) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token=None,
            )
        from pi_platform.ports import ApprovalRequired
        self.assertIsInstance(cm.exception, ApprovalRequired)

    def test_forged_token_is_rejected_at_materialise(self) -> None:
        service = self._service()
        token = self.boundary.issue(self._request(), ttl_seconds=60)
        forged = token[:-1] + ("A" if token[-1] != "A" else "B")
        with self.assertRaises(ApprovalRejected) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token=forged,
            )
        self.assertEqual(cm.exception.reason, "forged_signature")

    def test_expired_token_is_rejected_at_materialise(self) -> None:
        service = self._service()
        token = self.boundary.issue(self._request(), ttl_seconds=10)
        self.clock.advance(11)
        with self.assertRaises(ApprovalRejected) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token=token,
            )
        self.assertEqual(cm.exception.reason, "expired")

    def test_wrong_action_token_is_rejected_at_materialise(self) -> None:
        service = self._service()
        refresh_token = self.boundary.issue(
            ApprovalRequest(action="refresh_sources",
                            repo_root=str(self.tmp)),
            ttl_seconds=60,
        )
        with self.assertRaises(ApprovalRejected) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token=refresh_token,
            )
        self.assertEqual(cm.exception.reason, "wrong_action")

    def test_wrong_repo_token_is_rejected_at_materialise(self) -> None:
        service = self._service()
        other_repo_token = self.boundary.issue(
            ApprovalRequest(action="materialise",
                            repo_root="/tmp/somewhere-else"),
            ttl_seconds=60,
        )
        with self.assertRaises(ApprovalRejected) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token=other_repo_token,
            )
        self.assertEqual(cm.exception.reason, "wrong_repository")

    def test_change_superset_mismatch_is_rejected_at_materialise(self) -> None:
        service = self._service()
        narrow_token = self.boundary.issue(
            ApprovalRequest(action="materialise", repo_root=str(self.tmp),
                            change_ids=("rc-1",)),
            ttl_seconds=60,
        )
        # Present a non-empty change set the narrow grant does not
        # cover. The empty-changes no-op path is vacuously satisfied
        # by any grant and is exercised by the round-trip test above.
        from pi_platform.core.canonical import Source, RuntimeChange
        change = RuntimeChange(
            id="rc-extra", kind="chunk",
            payload={"id": "rc-extra", "kind": "chunk", "family": "md",
                     "text": "x"},
            source=Source(id="src", uri="file:///x", family="md",
                          contentHash="h"),
        )
        with self.assertRaises(ApprovalRejected) as cm:
            service.materialise_durable_changes(
                self.tmp, cache_root=self.tmp / "cache",
                approval_token=narrow_token,
                changes=[change],
            )
        self.assertEqual(cm.exception.reason, "change_superset_mismatch")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()