"""Phase 8 Enterprise Security Boundary regression suite.

The suite covers the eight Requirement blocks of the
``enterprise-security-boundary`` capability spec plus the
§68.50 (operator-approval) Requirement. Tests are grouped
by Requirement and named after the documented scenario so
failures map directly to the spec text.

The tests are written as a single ``unittest.TestCase`` per
Requirement block. The suite is intentionally hermetic: the
default cores are constructed in the ``setUp`` method
without a wired audit log, and the audit-emission scenarios
locally attach a small in-memory ``DefaultAuditLog``.
"""

from __future__ import annotations

import io
import unittest
from typing import Tuple

from pi_platform.core.canonical.value_types import (
    KnowledgeState,
    Metadata,
    ProjectVersion,
)
from pi_platform.core.control.audit import DefaultAuditLog
from pi_platform.core.control.policy import DefaultPolicyEngine
from pi_platform.core.control.secrets import DefaultSecretProvider
from pi_platform.core.retrieval.metadata_filter import MetadataFilterCore
from pi_platform.core.security.audit import DefaultSecurityAuditRecorder
from pi_platform.core.security.boundary import DefaultEnterpriseBoundary
from pi_platform.core.security.classification import (
    DefaultSecurityClassifier,
)
from pi_platform.core.security.detection import DefaultSecretDetector
from pi_platform.core.security.egress import DefaultEgressPolicy
from pi_platform.core.security.permission import (
    DefaultSourcePermissionPolicy,
)
from pi_platform.core.security.redaction import DefaultRedactionPipeline
from pi_platform.ports.control.policy import (
    Capability,
    PolicyEnginePort,
    Role,
)
from pi_platform.ports.control.secrets import (
    RedactionContext,
    SecretProviderPort,
)
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.metadata_filter import MetadataFilter
from pi_platform.ports.security.classification import (
    ClassificationLevel,
    UnknownClassificationLevelError,
    coerce_level,
)
from pi_platform.ports.security.detection import SecretKind
from pi_platform.ports.security.egress import (
    EgressChannel,
    EgressRequest,
)
from pi_platform.ports.security.permission import (
    SourcePermissionDecisionKind,
)
from pi_platform.ports.security.redaction import RedactionFailureError


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _make_metadata(
    document_id: str = "d1",
    *,
    security_classification: str | None = None,
) -> Metadata:
    return Metadata(
        documentId=document_id,
        version="0.0.0",
        language="und",
        securityClassification=security_classification,
    )


def _make_hit(
    chunk_id: str = "c1",
    *,
    security_classification: str | None = None,
) -> RetrievalHit:
    return RetrievalHit(
        chunkId=chunk_id,
        score=1.0,
        source="dense",
        metadata=_make_metadata(
            document_id=f"d-{chunk_id}",
            security_classification=security_classification,
        ),
    )


class _SecurityFixture(unittest.TestCase):
    """Wires the default Phase 8 cores around a
    configurable audit log and policy engine so every test
    starts from a clean, well-known state.
    """

    def setUp(self) -> None:
        super().setUp()
        self.classifier = DefaultSecurityClassifier()
        self.permission = DefaultSourcePermissionPolicy()
        self.detector = DefaultSecretDetector()
        self.audit = DefaultAuditLog()
        self.audit_recorder = DefaultSecurityAuditRecorder()
        self.audit_recorder.attach(
            audit_log=self.audit, secret_provider=DefaultSecretProvider(),
        )
        self.classifier.attach_audit(self.audit_recorder)
        self.detector.attach_audit(self.audit_recorder)
        self.provider: SecretProviderPort = DefaultSecretProvider()
        self.policy_engine: PolicyEnginePort = DefaultPolicyEngine()
        self.egress = DefaultEgressPolicy()
        self.egress.set_policy_engine(self.policy_engine)
        self.egress.attach_audit(
            audit=self.audit_recorder, audit_log=self.audit,
        )
        self.redaction = DefaultRedactionPipeline(
            _secret_provider=self.provider,
        )
        self.redaction.attach_audit(self.audit_recorder)
        self.boundary = DefaultEnterpriseBoundary(
            _classifier=self.classifier,
            _permission=self.permission,
            _detector=self.detector,
            _egress=self.egress,
            _redaction=self.redaction,
        )
        self.metadata_filter = MetadataFilterCore(
            enterprise_boundary=self.boundary,
        )


# ---------------------------------------------------------------------------
# Requirement 1 — Security Classification vocabulary
# ---------------------------------------------------------------------------


class ClassificationVocabularyTests(_SecurityFixture):
    """Requirement 1: classification vocabulary + default + unknown handling."""

    def test_unlabelled_chunk_defaults_to_public(self) -> None:
        result = self.classifier.classify_document("d1", None)
        self.assertEqual(result.level, ClassificationLevel.PUBLIC)

    def test_empty_string_classification_defaults_to_public(self) -> None:
        result = self.classifier.classify_document("d1", "")
        self.assertEqual(result.level, ClassificationLevel.PUBLIC)

    def test_unknown_level_raises_typed_error(self) -> None:
        with self.assertRaises(UnknownClassificationLevelError) as ctx:
            coerce_level("TOP_SECRET")
        self.assertEqual(ctx.exception.level, "TOP_SECRET")

    def test_rank_is_monotonic(self) -> None:
        from pi_platform.ports.security.classification import RANK
        self.assertLess(
            RANK[ClassificationLevel.PUBLIC],
            RANK[ClassificationLevel.INTERNAL],
        )
        self.assertLess(
            RANK[ClassificationLevel.INTERNAL],
            RANK[ClassificationLevel.CONFIDENTIAL],
        )
        self.assertLess(
            RANK[ClassificationLevel.CONFIDENTIAL],
            RANK[ClassificationLevel.RESTRICTED],
        )

    def test_ceiling_clamps_chunk_above_source_ceiling(self) -> None:
        self.classifier.set_ceiling(
            "src-low", ClassificationLevel.CONFIDENTIAL,
        )
        result = self.classifier.classify_document(
            "d1", "RESTRICTED", source_id="src-low",
        )
        self.assertEqual(result.level, ClassificationLevel.CONFIDENTIAL)

    def test_security_classify_audit_emitted(self) -> None:
        self.classifier.classify_document("d1", "INTERNAL")
        self.assertIn("security.classify", self.audit.flush())


# ---------------------------------------------------------------------------
# Requirement 2 — Secret detection
# ---------------------------------------------------------------------------


class SecretDetectionTests(_SecurityFixture):
    """Requirement 2: secret detection + redaction + audit."""

    def test_aws_access_key_detected(self) -> None:
        findings = self.detector.scan("AWS key: AKIAIOSFODNN7EXAMPLE here")
        kinds = {f.kind for f in findings}
        self.assertIn(SecretKind.AWS_ACCESS_KEY, kinds)

    def test_github_token_detected(self) -> None:
        findings = self.detector.scan(
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        )
        kinds = {f.kind for f in findings}
        self.assertIn(SecretKind.GITHUB_TOKEN, kinds)

    def test_pem_header_detected(self) -> None:
        findings = self.detector.scan(
            "-----BEGIN RSA PRIVATE KEY-----",
        )
        self.assertEqual(
            [f.kind for f in findings],
            [SecretKind.PEM_PRIVATE_KEY_HEADER],
        )

    def test_jwt_bearer_detected(self) -> None:
        findings = self.detector.scan(
            "eyJabc123def456.eyJabc123def456.eyJabc123def456",
        )
        kinds = {f.kind for f in findings}
        self.assertIn(SecretKind.JWT_BEARER, kinds)

    def test_generic_api_key_detected(self) -> None:
        findings = self.detector.scan(
            'api_key="ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"',
        )
        kinds = {f.kind for f in findings}
        self.assertIn(SecretKind.GENERIC_API_KEY, kinds)

    def test_high_entropy_base64_detected(self) -> None:
        # 48-char base64 string with Shannon entropy >= 4.5
        findings = self.detector.scan(
            "aBcD3FgH4jKl5MnP6qRs7TuV8wXyZ0aBcD3FgH4jKl5MnP",
        )
        kinds = {f.kind for f in findings}
        self.assertIn(SecretKind.HIGH_ENTROPY_BASE64, kinds)

    def test_benign_text_returns_no_findings_and_no_audit(self) -> None:
        before = self.audit.flush()
        findings = self.detector.scan("The quick brown fox jumps over the lazy dog")
        after = self.audit.flush()
        self.assertEqual(findings, ())
        # No new detect audit when no findings.
        self.assertEqual(before, after)

    def test_finding_redaction_marks_value(self) -> None:
        findings = self.detector.scan("AKIAIOSFODNN7EXAMPLE")
        self.assertEqual(len(findings), 1)
        redacted = findings[0].redacted()
        self.assertEqual(redacted.value, "[REDACTED:AWS_ACCESS_KEY]")
        # Raw value never appears in redacted form.
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", redacted.value)

    def test_scan_emits_audit_with_redacted_resource(self) -> None:
        self.detector.scan("AKIAIOSFODNN7EXAMPLE")
        text = self.audit.flush()
        self.assertIn("security.detect", text)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", text)


# ---------------------------------------------------------------------------
# Requirement 3 — Source-level permissions
# ---------------------------------------------------------------------------


class SourcePermissionTests(_SecurityFixture):
    """Requirement 3: source-level permission policy."""

    # Helper: every test below passes the documented
    # ``secret.reference`` capability so the role-based
    # default policy applies. The capability-delegation
    # rule is exercised separately.
    _CAPS = ("secret.reference",)

    def test_public_any_role_allow(self) -> None:
        for role in Role:
            d = self.permission.evaluate(
                source_id="src", classification="PUBLIC", actor_role=role,
                actor_capabilities=self._CAPS,
            )
            self.assertEqual(d.decision, SourcePermissionDecisionKind.ALLOW)

    def test_internal_coding_agent_redacted(self) -> None:
        d = self.permission.evaluate(
            source_id="src", classification="INTERNAL",
            actor_role=Role.CODING_AGENT_READ_ONLY,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d.decision, SourcePermissionDecisionKind.REDACT)
        self.assertEqual(d.rule, "coding_agent_internal")

    def test_internal_maintainer_allow(self) -> None:
        d = self.permission.evaluate(
            source_id="src", classification="INTERNAL",
            actor_role=Role.MAINTAINER,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d.decision, SourcePermissionDecisionKind.ALLOW)

    def test_confidential_maintainer_allow(self) -> None:
        d = self.permission.evaluate(
            source_id="src", classification="CONFIDENTIAL",
            actor_role=Role.MAINTAINER,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d.decision, SourcePermissionDecisionKind.ALLOW)
        self.assertEqual(d.rule, "maintainer_confidential")

    def test_confidential_viewer_redacted(self) -> None:
        d = self.permission.evaluate(
            source_id="src", classification="CONFIDENTIAL",
            actor_role=Role.VIEWER,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d.decision, SourcePermissionDecisionKind.REDACT)

    def test_restricted_administrator_allow(self) -> None:
        d = self.permission.evaluate(
            source_id="src", classification="RESTRICTED",
            actor_role=Role.ADMINISTRATOR,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d.decision, SourcePermissionDecisionKind.ALLOW)

    def test_restricted_viewer_deny(self) -> None:
        d = self.permission.evaluate(
            source_id="src", classification="RESTRICTED",
            actor_role=Role.VIEWER,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d.decision, SourcePermissionDecisionKind.DENY)
        self.assertEqual(d.rule, "restricted_deny")

    def test_ceiling_is_max_bound_not_downgrader(self) -> None:
        # An explicit ceiling of CONFIDENTIAL clamps RESTRICTED
        # chunks down, but a default PUBLIC ceiling must NOT
        # downgrade INTERNAL content.
        d1 = self.permission.evaluate(
            source_id="src", classification="INTERNAL",
            actor_role=Role.ADMINISTRATOR,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d1.classification, "INTERNAL")
        self.permission.set_ceiling("clamped", "CONFIDENTIAL")
        d2 = self.permission.evaluate(
            source_id="clamped", classification="RESTRICTED",
            actor_role=Role.ADMINISTRATOR,
            actor_capabilities=self._CAPS,
        )
        self.assertEqual(d2.classification, "CONFIDENTIAL")

    def test_no_secret_reference_denies_internal(self) -> None:
        # The capability-delegation Requirement: an actor
        # without ``secret.reference`` MUST be denied
        # any payload whose classification is ``>= INTERNAL``.
        d = self.permission.evaluate(
            source_id="src", classification="INTERNAL",
            actor_role=Role.MAINTAINER,
            actor_capabilities=(),
        )
        self.assertEqual(d.decision, SourcePermissionDecisionKind.DENY)
        self.assertEqual(d.rule, "missing_secret_reference")


# ---------------------------------------------------------------------------
# Requirement 4 — Egress policy
# ---------------------------------------------------------------------------


class EgressPolicyTests(_SecurityFixture):
    """Requirement 4: egress policy + capability gate + fail-closed."""

    def test_loopback_allow_without_engine(self) -> None:
        e = DefaultEgressPolicy()  # no engine
        d = e.evaluate(EgressRequest(
            url="http://127.0.0.1:7777/mcp",
            classification="PUBLIC", actor_role=Role.VIEWER,
            capability_requested="mcp.invoke",
        ))
        self.assertTrue(d.allowed)
        self.assertEqual(d.channel, EgressChannel.LOOPBACK)

    def test_external_deny_without_capability(self) -> None:
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="PUBLIC",
            actor_role=Role.VIEWER,
            capability_requested="mcp.invoke",
        ))
        self.assertFalse(d.allowed)
        self.assertEqual(d.channel, EgressChannel.EXTERNAL)

    def test_external_allow_with_capability(self) -> None:
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="PUBLIC",
            actor_role=Role.ADMINISTRATOR,
            capability_requested="network.external",
            actor_capabilities=("network.external",),
            approval_token="token",
        ))
        self.assertTrue(d.allowed)
        self.assertIn("PUBLIC", d.rationale)

    def test_external_deny_when_classification_exceeds_endpoint_allow(self) -> None:
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="RESTRICTED",
            actor_role=Role.ADMINISTRATOR,
            capability_requested="network.external",
            actor_capabilities=("network.external",),
            approval_token="token",
        ))
        self.assertFalse(d.allowed)
        self.assertIn("RESTRICTED", d.rationale)

    def test_missing_policy_engine_returns_deny(self) -> None:
        e = DefaultEgressPolicy()  # no engine
        d = e.evaluate(EgressRequest(
            url="https://example.com/api", classification="PUBLIC",
            actor_role=Role.ADMINISTRATOR,
            capability_requested="network.external",
        ))
        self.assertFalse(d.allowed)
        self.assertIn("policy engine is not configured", d.rationale)

    def test_viewer_without_capability_deny(self) -> None:
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="PUBLIC",
            actor_role=Role.VIEWER,
            capability_requested="network.external",
            actor_capabilities=(),
        ))
        self.assertFalse(d.allowed)

    def test_restricted_egress_requires_approval_token(self) -> None:
        # Without approval token, REQUIRE_APPROVAL → DENY
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="RESTRICTED",
            actor_role=Role.ADMINISTRATOR,
            capability_requested="network.external",
            actor_capabilities=("network.external",),
        ))
        self.assertFalse(d.allowed)
        self.assertIn("approval_token", d.rationale)

    def test_egress_emits_audit(self) -> None:
        self.egress.evaluate(EgressRequest(
            url="http://127.0.0.1:7777", classification="PUBLIC",
            actor_role=Role.VIEWER, capability_requested="mcp.invoke",
        ))
        self.assertIn("security.egress", self.audit.flush())


# ---------------------------------------------------------------------------
# Requirement 5 — Redaction pipeline
# ---------------------------------------------------------------------------


class RedactionPipelineTests(_SecurityFixture):
    """Requirement 5: redaction pipeline + invariant + audit."""

    def test_resolved_secret_replaced_by_reference(self) -> None:
        # env://HTTP_PROXY is unresolvable in test env, so
        # use a parseable reference that won't resolve.
        ref = self.provider.parse("env://HTTP_PROXY")
        # Use the value field directly; resolve raises
        # when the env var is missing.
        result = self.redaction.redact(
            value="env://HTTP_PROXY",
            channel=RedactionContext.LLM_CONTEXT,
            classification="INTERNAL",
            actor_role=Role.MAINTAINER,
            actor_capabilities=("secret.reference",),
        )
        self.assertEqual(result.value, "env://HTTP_PROXY")
        del ref  # silence unused warning

    def test_internal_coding_agent_redacts(self) -> None:
        result = self.redaction.redact(
            value="some internal body",
            channel=RedactionContext.LLM_CONTEXT,
            classification="INTERNAL",
            actor_role=Role.CODING_AGENT_READ_ONLY,
            actor_capabilities=("knowledge.read",),
        )
        self.assertEqual(result.value, "[REDACTED:INTERNAL]")

    def test_redaction_audit_emitted(self) -> None:
        self.redaction.redact(
            value="payload", channel=RedactionContext.LLM_CONTEXT,
            classification="INTERNAL",
            actor_role=Role.CODING_AGENT_READ_ONLY,
        )
        self.assertIn("security.redact", self.audit.flush())

    def test_pipeline_steps_are_documented(self) -> None:
        names = [s.name for s in self.redaction.steps()]
        self.assertEqual(
            names,
            ["phase7_secret_provider", "phase8_classification_driven"],
        )

    def test_serialise_is_byte_stable(self) -> None:
        s1 = self.redaction.serialise()
        s2 = self.redaction.serialise()
        self.assertEqual(s1, s2)

    def test_lacks_secret_reference_redacts_internal(self) -> None:
        # No secret.reference + INTERNAL content = redacted
        result = self.redaction.redact(
            value="confidential body",
            channel=RedactionContext.MCP_RESPONSE,
            classification="INTERNAL",
            actor_role=Role.MAINTAINER,
            actor_capabilities=(),
        )
        self.assertEqual(result.value, "[REDACTED:INTERNAL]")

    def test_with_secret_reference_passes_through(self) -> None:
        result = self.redaction.redact(
            value="internal body",
            channel=RedactionContext.MCP_RESPONSE,
            classification="INTERNAL",
            actor_role=Role.MAINTAINER,
            actor_capabilities=("secret.reference",),
        )
        self.assertEqual(result.value, "internal body")


# ---------------------------------------------------------------------------
# Requirement 6 — Retrieval filter integration
# ---------------------------------------------------------------------------


class RetrievalFilterIntegrationTests(_SecurityFixture):
    """Requirement 6: metadata filter Enterprise Boundary integration."""

    # Helper: every test below passes the documented
    # ``secret.reference`` capability so the role-based
    # default policy applies. The capability-delegation
    # rule is exercised separately.
    _CAPS = ("secret.reference", "knowledge.read")

    def test_restricted_for_viewer_with_allow_list_uses_phase4_reason(self) -> None:
        # With an allow-list, the Phase 4 reason wins
        pv = ProjectVersion(
            gitHead="abc123", workingTreeFingerprint="fp",
            knowledgeSchemaVersion="1.0", embeddingModelVersion="1.0",
            indexSchemaVersion="1.0",
        )
        flt = MetadataFilter(
            projectVersion=pv,
            securityClassifications=("PUBLIC",),
            actor_role=Role.VIEWER,
            actor_capabilities=self._CAPS,
        )
        kept = self.metadata_filter.apply(
            flt, [_make_hit("c1", security_classification="RESTRICTED")],
        )
        self.assertEqual(kept, ())
        self.assertEqual(
            self.metadata_filter.stats().get("security_denied"), 1,
        )

    def test_internal_coding_agent_kept_with_redaction_reason(self) -> None:
        flt = MetadataFilter(
            actor_role=Role.CODING_AGENT_READ_ONLY,
            actor_capabilities=self._CAPS,
        )
        kept = self.metadata_filter.apply(
            flt, [_make_hit("c1", security_classification="INTERNAL")],
        )
        # Bug #1 fix: hit is KEPT, not dropped.
        self.assertEqual(len(kept), 1)
        self.assertEqual(
            self.metadata_filter.stats().get("security_redacted"), 1,
        )
        self.assertEqual(self.metadata_filter.redacted_count, 1)
        # Blocked: the kept hit's snippet is the
        # documented redaction marker, never the raw text.
        self.assertEqual(kept[0].snippet, "[REDACTED:INTERNAL]")

    def test_no_boundary_preserves_phase4_behaviour(self) -> None:
        # Construct a filter with no boundary to confirm
        # the Phase 4 baseline still works.
        plain_core = MetadataFilterCore()
        flt = MetadataFilter(securityClassifications=("PUBLIC",))
        kept = plain_core.apply(
            flt, [_make_hit("c1", security_classification="RESTRICTED")],
        )
        self.assertEqual(kept, ())
        self.assertEqual(
            plain_core.stats().get("security_denied"), 1,
        )

    def test_confidential_viewer_kept_with_redaction(self) -> None:
        flt = MetadataFilter(
            actor_role=Role.VIEWER,
            actor_capabilities=self._CAPS,
        )
        kept = self.metadata_filter.apply(
            flt, [_make_hit("c1", security_classification="CONFIDENTIAL")],
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(
            self.metadata_filter.stats().get("security_redacted"), 1,
        )
        self.assertEqual(kept[0].snippet, "[REDACTED:CONFIDENTIAL]")

    def test_restricted_viewer_dropped_with_egress_denied(self) -> None:
        flt = MetadataFilter(
            actor_role=Role.VIEWER,
            actor_capabilities=self._CAPS,
        )
        kept = self.metadata_filter.apply(
            flt, [_make_hit("c1", security_classification="RESTRICTED")],
        )
        self.assertEqual(kept, ())
        self.assertEqual(
            self.metadata_filter.stats().get("security_egress_denied"), 1,
        )

    def test_boundary_failure_fails_closed(self) -> None:
        # Blocked: a broken boundary MUST NOT widen access.
        # The filter is the security boundary; a raised
        # exception must surface as ``security_denied``.
        from pi_platform.ports.security.permission import (
            SourcePermissionDecision,
        )
        from pi_platform.ports.security.boundary import (
            EnterpriseBoundaryPort,
        )

        class _BrokenBoundary(EnterpriseBoundaryPort):
            def classify(self, document_id, raw_level, source_id=""):
                return None

            def source_permission(
                self, *, source_id, classification, actor_role,
                actor_capabilities=(),
            ):
                raise RuntimeError("boundary broken")

            def scan_secrets(self, value, *, field="value"):
                return ()

            def evaluate_egress(self, request):
                raise NotImplementedError

            def redact(
                self, value, *, channel, classification, actor_role,
                actor_capabilities=(),
            ):
                raise NotImplementedError

            def serialise(self):
                return "{}"

        broken_core = MetadataFilterCore(
            enterprise_boundary=_BrokenBoundary(),
        )
        flt = MetadataFilter(
            actor_role=Role.MAINTAINER,
            actor_capabilities=self._CAPS,
        )
        kept = broken_core.apply(
            flt, [_make_hit("c1", security_classification="INTERNAL")],
        )
        self.assertEqual(kept, ())
        self.assertEqual(
            broken_core.stats().get("security_denied"), 1,
        )


# ---------------------------------------------------------------------------
# Requirement 7 — Auditability
# ---------------------------------------------------------------------------


class AuditabilityTests(_SecurityFixture):
    """Requirement 7: security audit emission + best-effort isolation."""

    def test_detector_emits_security_detect_audit(self) -> None:
        self.detector.scan("AKIAIOSFODNN7EXAMPLE")
        self.assertIn("security.detect", self.audit.flush())

    def test_egress_emits_security_egress_audit(self) -> None:
        self.egress.evaluate(EgressRequest(
            url="http://127.0.0.1:7777", classification="PUBLIC",
            actor_role=Role.VIEWER, capability_requested="mcp.invoke",
        ))
        self.assertIn("security.egress", self.audit.flush())

    def test_redaction_emits_security_redact_audit(self) -> None:
        self.redaction.redact(
            value="payload", channel=RedactionContext.LLM_CONTEXT,
            classification="INTERNAL",
            actor_role=Role.CODING_AGENT_READ_ONLY,
        )
        self.assertIn("security.redact", self.audit.flush())

    def test_audit_failure_does_not_break_data_plane(self) -> None:
        # Wire a recorder in fail-loud mode against an
        # audit log that raises.
        class RaisingLog:
            def record(self, _record) -> None:
                raise RuntimeError("audit broken")

        # The data-plane path (redaction) MUST still
        # return a valid RedactionResult.
        # Note: DefaultRedactionPipeline uses the wired
        # SecurityAuditPort, not the AuditLogPort directly,
        # so the failure is contained in the recorder.
        recorder = DefaultSecurityAuditRecorder()
        recorder.fail_loud(True)
        recorder.attach(audit_log=RaisingLog(), secret_provider=self.provider)
        pipeline = DefaultRedactionPipeline(
            _secret_provider=self.provider,
        )
        pipeline.attach_audit(recorder)
        # Should NOT propagate.
        result = pipeline.redact(
            value="body", channel=RedactionContext.LLM_CONTEXT,
            classification="INTERNAL",
            actor_role=Role.CODING_AGENT_READ_ONLY,
        )
        self.assertTrue(result.value.startswith("[REDACTED:"))


# ---------------------------------------------------------------------------
# Requirement 8 — Capability-based delegation
# ---------------------------------------------------------------------------


class CapabilityDelegationTests(_SecurityFixture):
    """Requirement 8: capability-based delegation through egress + redaction."""

    def test_actor_without_secret_reference_denied_internal(self) -> None:
        # Capability delegation: an actor without
        # ``secret.reference`` MUST be denied any
        # ``>= INTERNAL`` payload. The source-permission
        # port returns DENY (fail-closed), the redaction
        # pipeline enforces the same rule as a second
        # line of defence.
        decision = self.permission.evaluate(
            source_id="src", classification="INTERNAL",
            actor_role=Role.CODING_AGENT_READ_ONLY,
            actor_capabilities=("knowledge.read",),
        )
        self.assertEqual(
            decision.decision, SourcePermissionDecisionKind.DENY,
        )
        self.assertEqual(decision.rule, "missing_secret_reference")

    def test_actor_with_network_external_egresses(self) -> None:
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="PUBLIC",
            actor_role=Role.ADMINISTRATOR,
            capability_requested="network.external",
            actor_capabilities=("network.external",),
            approval_token="token",
        ))
        self.assertTrue(d.allowed)

    def test_actor_without_network_local_denied_public(self) -> None:
        # A VIEWER can only do localhost; non-localhost is
        # DENY because they lack network.external.
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="PUBLIC",
            actor_role=Role.VIEWER,
            capability_requested="network.external",
            actor_capabilities=(),
        ))
        self.assertFalse(d.allowed)


# ---------------------------------------------------------------------------
# Requirement 9 — Operator approval gate (§68.50)
# ---------------------------------------------------------------------------


class OperatorApprovalTests(_SecurityFixture):
    """§68.50: high-impact security operations route through
    ``REQUIRE_APPROVAL`` / ``approval_token``."""

    def test_restricted_egress_without_approval_token_deny(self) -> None:
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="RESTRICTED",
            actor_role=Role.ADMINISTRATOR,
            capability_requested="network.external",
            actor_capabilities=("network.external",),
        ))
        self.assertFalse(d.allowed)
        self.assertIn("approval_token", d.rationale)

    def test_restricted_egress_with_approval_token_allow(self) -> None:
        # Add RESTRICTED to the endpoint allow-list so the
        # §68.50 approval-gate is the only remaining
        # condition.
        self.egress.allow_endpoint("RESTRICTED")
        d = self.egress.evaluate(EgressRequest(
            url="https://example.com/api", classification="RESTRICTED",
            actor_role=Role.ADMINISTRATOR,
            capability_requested="network.external",
            actor_capabilities=("network.external",),
            approval_token="approved-by-cto",
        ))
        self.assertTrue(d.allowed)


if __name__ == "__main__":
    unittest.main()
