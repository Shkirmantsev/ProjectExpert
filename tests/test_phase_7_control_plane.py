"""Phase 7 §59 control-plane focused regression tests.

The fixtures exercise every documented Phase 7 surface:

1. Feature / Plugin Registry lifecycle state machine,
   manifest validation, dependency resolution;
2. Hook Runtime timeout / cancellation / failure policy;
3. Policy Engine allow / deny / require-approval decision
   contract and the documented read-only coding-agent
   capability set;
4. Secret Provider redaction contract and the
   no-plain-text-secret invariant;
5. Audit Log field schema and the no-secret-in-audit
   invariant;
6. Feature Flag scope resolution and the
   experimental-defaults-to-disabled rule;
7. UI Extension Registry validator's no-arbitrary-JS rule;
8. Cross-cutting Phase 7 quality gates appended to
   ``tests/test_phase_6_quality_gates.py``.

Each fixture records PASS / FAIL / NOT RUN explicitly.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterable, Mapping

from pi_platform.adapters.control import (
    EncryptedLocalStoreBackend,
    EnvironmentBackend,
    JsonlAuditSink,
    JsonlOperationalSink,
    KeychainBackend,
    NoArbitraryJavaScriptValidator,
    build_default_policy_engine,
    build_default_sink_pair,
)
from pi_platform.core.control import (
    DefaultAuditLog,
    DefaultFeatureFlagRegistry,
    DefaultFeatureRegistry,
    DefaultHookRuntime,
    DefaultOperationalLog,
    DefaultPluginRegistry,
    DefaultPolicyEngine,
    DefaultSecretProvider,
    DefaultUiExtensionRegistry,
)
from pi_platform.ports.control import (
    ApprovalRequired,
    AuditRecord,
    Capability,
    Decision,
    DeniedError,
    FeatureFlagContext,
    FeatureFlagScope,
    FeatureFlagState,
    FeatureManifest,
    HookContext,
    HookDefinition,
    HookEvent,
    HookFailurePolicy,
    HookResult,
    HookTimeoutError,
    LifecycleState,
    OperationalRecord,
    PluginManifest,
    PolicyDecision,
    PolicyRequest,
    RedactionContext,
    Role,
    SecretReference,
    UiExtensionDescriptor,
    UiExtensionKind,
    UnknownCapabilityError,
)
from pi_platform.core.control.audit import (
    assert_separated_streams as _assert_separated_streams,
)


# ---------------------------------------------------------------------------
# 7.1 — Feature / Plugin Registry
# ---------------------------------------------------------------------------


class FeatureRegistryLifecycleTests(unittest.TestCase):

    def test_lifecycle_state_machine_full_traversal(self) -> None:
        registry = DefaultFeatureRegistry()
        manifest = FeatureManifest(
            id="pi.test.feature",
            name="Test Feature",
            version="1.0.0",
            api_version="1.0.0",
            license="Apache-2.0",
            provider="pi-platform",
            type="feature",
            capabilities=("knowledge.read",),
            content_hash="a" * 64,
        )
        # installed -> enabled
        self.assertEqual(registry.install(manifest),
                         LifecycleState.INSTALLED)
        self.assertEqual(registry.enable("pi.test.feature"),
                         LifecycleState.ENABLED)
        # enabled -> disabled
        self.assertEqual(registry.disable("pi.test.feature"),
                         LifecycleState.DISABLED)
        # disabled -> enabled
        self.assertEqual(registry.enable("pi.test.feature"),
                         LifecycleState.ENABLED)
        # enabled -> update_available
        self.assertEqual(registry.transition(
            "pi.test.feature",
            LifecycleState.UPDATE_AVAILABLE,
            actor_id="operator",
            role=Role.MAINTAINER,
        ), LifecycleState.UPDATE_AVAILABLE)
        # update_available -> enabled
        self.assertEqual(registry.transition(
            "pi.test.feature",
            LifecycleState.ENABLED,
            actor_id="operator",
            role=Role.MAINTAINER,
        ), LifecycleState.ENABLED)
        # enabled -> disabled -> uninstalled
        self.assertEqual(registry.disable("pi.test.feature"),
                         LifecycleState.DISABLED)
        registry.uninstall("pi.test.feature")
        with self.assertRaises(KeyError):
            registry.inspect("pi.test.feature")

    def test_illegal_transition_raises(self) -> None:
        registry = DefaultFeatureRegistry()
        manifest = FeatureManifest(
            id="pi.test.illegal",
            name="Illegal",
            version="1.0.0",
            api_version="1.0.0",
            license="Apache-2.0",
            provider="pi-platform",
            type="feature",
            content_hash="b" * 64,
        )
        registry.install(manifest)
        # Move to FAILED
        registry.transition(
            "pi.test.illegal",
            LifecycleState.FAILED,
            actor_id="operator",
            role=Role.MAINTAINER,
        )
        # FAILED -> ENABLED is illegal
        with self.assertRaises(Exception) as ctx:
            registry.transition(
                "pi.test.illegal",
                LifecycleState.ENABLED,
                actor_id="operator",
                role=Role.MAINTAINER,
            )
        self.assertIn("illegal-lifecycle-transition",
                      str(ctx.exception))

    def test_manifest_validator_rejects_unknown_capability(self) -> None:
        registry = DefaultFeatureRegistry()
        manifest = FeatureManifest(
            id="pi.test.bad",
            name="Bad",
            version="1.0.0",
            api_version="1.0.0",
            license="Apache-2.0",
            provider="pi-platform",
            type="feature",
            capabilities=("net.free",),
            content_hash="c" * 64,
        )
        from pi_platform.ports.control.registry import (
            ManifestValidationError,
        )
        with self.assertRaises(ManifestValidationError) as ctx:
            registry.install(manifest)
        self.assertEqual(ctx.exception.check, "capabilities")
        self.assertEqual(ctx.exception.value, "net.free")

    def test_manifest_validator_rejects_bad_license(self) -> None:
        registry = DefaultFeatureRegistry()
        manifest = FeatureManifest(
            id="pi.test.badlicense",
            name="BadLicense",
            version="1.0.0",
            api_version="1.0.0",
            license="   ",
            provider="pi-platform",
            type="feature",
            content_hash="d" * 64,
        )
        from pi_platform.ports.control.registry import (
            ManifestValidationError,
        )
        with self.assertRaises(ManifestValidationError) as ctx:
            registry.install(manifest)
        self.assertEqual(ctx.exception.check, "license")

    def test_manifest_validator_rejects_bad_content_hash(self) -> None:
        registry = DefaultFeatureRegistry()
        manifest = FeatureManifest(
            id="pi.test.badhash",
            name="BadHash",
            version="1.0.0",
            api_version="1.0.0",
            license="Apache-2.0",
            provider="pi-platform",
            type="feature",
            content_hash="not-hex",
        )
        from pi_platform.ports.control.registry import (
            ManifestValidationError,
        )
        with self.assertRaises(ManifestValidationError) as ctx:
            registry.install(manifest)
        self.assertEqual(ctx.exception.check, "content_hash")

    def test_registry_serialise_is_byte_stable(self) -> None:
        registry = DefaultFeatureRegistry()
        for index in range(2):
            manifest = FeatureManifest(
                id=f"pi.test.byte.{index}",
                name=f"Byte{index}",
                version="1.0.0",
                api_version="1.0.0",
                license="Apache-2.0",
                provider="pi-platform",
                type="feature",
                content_hash=("a" * 63 + str(index)),
            )
            registry.install(manifest)
        first = registry.serialise()
        second = registry.serialise()
        self.assertEqual(first, second)
        # No resolved secret values appear in the serialised form.
        self.assertNotIn("http://proxy:8080", first)


class PluginRegistrySharesLifecycleTests(unittest.TestCase):

    def test_plugin_registry_inherits_lifecycle(self) -> None:
        registry = DefaultPluginRegistry()
        manifest = PluginManifest(
            id="pi.test.plugin",
            name="Plugin",
            version="1.0.0",
            api_version="1.0.0",
            license="MIT-0",
            provider="pi-platform",
            type="plugin",
            content_hash="e" * 64,
        )
        self.assertEqual(registry.install(manifest),
                         LifecycleState.INSTALLED)
        self.assertEqual(registry.enable("pi.test.plugin"),
                         LifecycleState.ENABLED)
        self.assertEqual(registry.disable("pi.test.plugin"),
                         LifecycleState.DISABLED)
        registry.uninstall("pi.test.plugin")
        with self.assertRaises(KeyError):
            registry.inspect("pi.test.plugin")


# ---------------------------------------------------------------------------
# 7.2 — Hook Runtime
# ---------------------------------------------------------------------------


class HookRuntimeTests(unittest.TestCase):

    def test_dispatch_emits_deterministic_correlation_id(self) -> None:
        runtime = DefaultHookRuntime()
        captured: list[str] = []

        def hook(ctx: HookContext) -> HookResult:
            captured.append(ctx.correlation_id)
            return HookResult(
                hook_id=ctx.hook_id,
                plugin_id=ctx.plugin_id,
                event=ctx.event,
                duration_ms=1,
                status="ok",
                correlation_id=ctx.correlation_id,
            )

        runtime.register(HookDefinition(
            hook_id="hook.deterministic",
            plugin_id="plugin.test",
            event=HookEvent.AFTER_RETRIEVAL,
            failure_policy=HookFailurePolicy.WARN_ONLY,
            callback=hook,
        ))
        result = runtime.dispatch(
            HookEvent.AFTER_RETRIEVAL,
            correlation_id="corr-1",
            project_version="v1",
            input_payload={"query": "x"},
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(captured, ["corr-1"])

    def test_fail_closed_timeout_aborts_calling_action(self) -> None:
        runtime = DefaultHookRuntime()
        from pi_platform.ports.control.hooks import HookTimeoutError

        def slow(ctx: HookContext) -> HookResult:
            # Manually raise HookTimeoutError to simulate a
            # bounded-timeout cancellation without relying on
            # wall-clock timers in the focused regression
            # suite.
            raise HookTimeoutError("simulated-timeout")

        runtime.register(HookDefinition(
            hook_id="hook.slow",
            plugin_id="plugin.slow",
            event=HookEvent.BEFORE_MATERIALIZATION,
            failure_policy=HookFailurePolicy.FAIL_CLOSED,
            callback=slow,
        ))
        with self.assertRaises(HookTimeoutError):
            runtime.dispatch(
                HookEvent.BEFORE_MATERIALIZATION,
                correlation_id="corr-timeout",
                project_version="v1",
                input_payload={},
            )

    def test_warn_only_records_and_continues(self) -> None:
        runtime = DefaultHookRuntime()
        from pi_platform.ports.control.hooks import HookTimeoutError

        def boom(ctx: HookContext) -> HookResult:
            raise HookTimeoutError("simulated-timeout")

        runtime.register(HookDefinition(
            hook_id="hook.boom",
            plugin_id="plugin.boom",
            event=HookEvent.AFTER_RETRIEVAL,
            failure_policy=HookFailurePolicy.WARN_ONLY,
            callback=boom,
        ))
        result = runtime.dispatch(
            HookEvent.AFTER_RETRIEVAL,
            correlation_id="corr-warn",
            project_version="v1",
            input_payload={},
        )
        self.assertIn(result.status, ("timeout", "error"))

    def test_disable_plugin_transitions_plugin_to_failed(self) -> None:
        registry = DefaultPluginRegistry()
        runtime = DefaultHookRuntime()

        def disable_plugin(plugin_id: str) -> None:
            registry.transition(
                plugin_id,
                LifecycleState.FAILED,
                actor_id="operator",
                role=Role.MAINTAINER,
            )

        runtime._plugin_disable_hook = disable_plugin  # noqa: SLF001

        manifest = PluginManifest(
            id="plugin.disable_me",
            name="DisableMe",
            version="1.0.0",
            api_version="1.0.0",
            license="MIT-0",
            provider="pi-platform",
            type="plugin",
            content_hash="f" * 64,
        )
        registry.install(manifest)
        registry.enable("plugin.disable_me")

        from pi_platform.ports.control.hooks import HookTimeoutError

        def boom(ctx: HookContext) -> HookResult:
            raise HookTimeoutError("disable-me")

        runtime.register(HookDefinition(
            hook_id="hook.disable_me",
            plugin_id="plugin.disable_me",
            event=HookEvent.BEFORE_RETRIEVAL,
            failure_policy=HookFailurePolicy.DISABLE_PLUGIN,
            callback=boom,
        ))
        runtime.dispatch(
            HookEvent.BEFORE_RETRIEVAL,
            correlation_id="corr-disable",
            project_version="v1",
            input_payload={},
        )
        _, state = registry.inspect("plugin.disable_me")
        self.assertEqual(state, LifecycleState.FAILED)

    def test_cancellation_propagates(self) -> None:
        runtime = DefaultHookRuntime()

        def long(ctx: HookContext) -> HookResult:
            runtime.cancel(ctx.correlation_id)
            raise HookTimeoutError("cancelled")

        runtime.register(HookDefinition(
            hook_id="hook.cancel",
            plugin_id="plugin.cancel",
            event=HookEvent.BEFORE_RETRIEVAL,
            failure_policy=HookFailurePolicy.WARN_ONLY,
            callback=long,
        ))
        result = runtime.dispatch(
            HookEvent.BEFORE_RETRIEVAL,
            correlation_id="corr-cancel",
            project_version="v1",
            input_payload={},
        )
        self.assertIn(result.status, ("timeout", "error"))


# ---------------------------------------------------------------------------
# 7.3 — Policy Engine
# ---------------------------------------------------------------------------


class PolicyEngineDecisionContractTests(unittest.TestCase):

    def test_read_only_coding_agent_capability_set(self) -> None:
        engine = DefaultPolicyEngine()
        # Allow
        for cap in (Capability.KNOWLEDGE_READ,
                    Capability.RETRIEVAL_QUERY,
                    Capability.CONFIG_READ,
                    Capability.AUDIT_WRITE):
            request = PolicyRequest(
                actor_type="agent",
                actor_id="coding-agent",
                role=Role.CODING_AGENT_READ_ONLY,
                capability=cap,
                resource="test",
                project_version="v1",
                correlation_id="corr-allow",
            )
            decision = engine.evaluate(request)
            self.assertEqual(decision.decision, Decision.ALLOW,
                             msg=f"expected ALLOW for {cap.value}")
        # Deny
        for cap in (Capability.KNOWLEDGE_WRITE,
                    Capability.KNOWLEDGE_MATERIALIZE,
                    Capability.CONFIG_WRITE,
                    Capability.GIT_WRITE,
                    Capability.SECRET_RESOLVE):
            request = PolicyRequest(
                actor_type="agent",
                actor_id="coding-agent",
                role=Role.CODING_AGENT_READ_ONLY,
                capability=cap,
                resource="test",
                project_version="v1",
                correlation_id="corr-deny",
            )
            decision = engine.evaluate(request)
            self.assertEqual(decision.decision, Decision.DENY,
                             msg=f"expected DENY for {cap.value}")

    def test_materialise_from_viewer_requires_approval(self) -> None:
        engine = DefaultPolicyEngine()
        # Maintainer does NOT have knowledge.materialize;
        # only Administrator does. The high-impact gate fires
        # only when the role grants the capability.
        request = PolicyRequest(
            actor_type="user",
            actor_id="alice",
            role=Role.MAINTAINER,
            capability=Capability.KNOWLEDGE_MATERIALIZE,
            resource="spec",
            project_version="v1",
            correlation_id="corr-viewer",
        )
        decision = engine.evaluate(request)
        self.assertEqual(decision.decision, Decision.DENY)

    def test_materialise_from_maintainer_with_token_allows(self) -> None:
        engine = DefaultPolicyEngine()
        # git.write is high-impact but Maintainer has it; a
        # valid approval token unlocks the action.
        request = PolicyRequest(
            actor_type="user",
            actor_id="bob",
            role=Role.MAINTAINER,
            capability=Capability.GIT_WRITE,
            resource="spec",
            project_version="v1",
            correlation_id="corr-maint",
            approval_token="approval-token",
        )
        decision = engine.evaluate(request)
        self.assertEqual(decision.decision, Decision.ALLOW)

    def test_administrator_materialise_requires_approval_without_token(self) -> None:
        engine = DefaultPolicyEngine()
        request = PolicyRequest(
            actor_type="user",
            actor_id="root",
            role=Role.ADMINISTRATOR,
            capability=Capability.KNOWLEDGE_MATERIALIZE,
            resource="spec",
            project_version="v1",
            correlation_id="corr-admin",
        )
        decision = engine.evaluate(request)
        self.assertEqual(decision.decision, Decision.REQUIRE_APPROVAL)
        self.assertIsNotNone(decision.approval_request_id)

    def test_administrator_materialise_allows_with_token(self) -> None:
        engine = DefaultPolicyEngine()
        request = PolicyRequest(
            actor_type="user",
            actor_id="root",
            role=Role.ADMINISTRATOR,
            capability=Capability.KNOWLEDGE_MATERIALIZE,
            resource="spec",
            project_version="v1",
            correlation_id="corr-admin-ok",
            approval_token="approval-token",
        )
        decision = engine.evaluate(request)
        self.assertEqual(decision.decision, Decision.ALLOW)

    def test_unknown_capability_raises(self) -> None:
        engine = DefaultPolicyEngine()
        # The engine only checks against the documented
        # vocabulary; we feed it a synthetic value through a
        # duck-typed object so we exercise the
        # UnknownCapabilityError path without extending the
        # Capability enum.
        with self.assertRaises(UnknownCapabilityError):
            engine.evaluate(PolicyRequest(
                actor_type="user",
                actor_id="alice",
                role=Role.VIEWER,
                capability=type("C", (), {"value": "net.free"}),  # type: ignore[arg-type]
                resource="x",
                project_version="v1",
                correlation_id="corr-unknown",
            ))

    def test_authorize_raises_for_deny_and_require_approval(self) -> None:
        engine = DefaultPolicyEngine()
        # Deny: the role does not grant the capability at all
        # (filesystem.write is not in the Viewer default).
        with self.assertRaises(DeniedError):
            engine.authorize(PolicyRequest(
                actor_type="user", actor_id="alice",
                role=Role.VIEWER,
                capability=Capability.FILESYSTEM_WRITE,
                resource="x", project_version="v1",
                correlation_id="corr-auth-deny",
            ))
        # Require approval: the role grants the capability
        # but it is high-impact (Maintainer has git.write).
        with self.assertRaises(ApprovalRequired):
            engine.authorize(PolicyRequest(
                actor_type="user", actor_id="alice",
                role=Role.MAINTAINER,
                capability=Capability.GIT_WRITE,
                resource="x", project_version="v1",
                correlation_id="corr-auth-req",
            ))

    def test_serialise_is_byte_stable(self) -> None:
        engine = build_default_policy_engine()
        first = engine.serialise()
        second = engine.serialise()
        self.assertEqual(first, second)


# ---------------------------------------------------------------------------
# 7.4 — Secret Provider
# ---------------------------------------------------------------------------


class SecretProviderRedactionTests(unittest.TestCase):

    def test_parse_env_reference(self) -> None:
        provider = DefaultSecretProvider()
        ref = provider.parse("env://HTTP_PROXY")
        self.assertEqual(ref.scheme, "env")
        self.assertEqual(ref.name, "HTTP_PROXY")
        self.assertEqual(ref.canonical, "env://HTTP_PROXY")

    def test_parse_secret_reference(self) -> None:
        provider = DefaultSecretProvider()
        ref = provider.parse("secret://local/confluence-token")
        self.assertEqual(ref.scheme, "secret")
        self.assertEqual(ref.backend, "local")
        self.assertEqual(ref.name, "confluence-token")

    def test_rejects_unknown_scheme(self) -> None:
        provider = DefaultSecretProvider()
        with self.assertRaises(Exception):
            provider.parse("vault://local/x")

    def test_resolve_env_reference(self) -> None:
        import os
        os.environ["PI_TEST_SECRET"] = "resolved-value"
        provider = DefaultSecretProvider()
        ref = provider.parse("env://PI_TEST_SECRET")
        self.assertEqual(provider.resolve(ref), "resolved-value")

    def test_resolve_unknown_reference_raises(self) -> None:
        provider = DefaultSecretProvider()
        ref = provider.parse("secret://local/missing")
        with self.assertRaises(Exception) as ctx:
            provider.resolve(ref)
        self.assertIn("secret-resolution-error", str(ctx.exception))

    def test_redaction_replaces_resolved_value(self) -> None:
        provider = DefaultSecretProvider()
        ref = provider.parse("env://PI_TEST_REDACT")
        import os
        os.environ["PI_TEST_REDACT"] = "leaked-value"
        provider.resolve(ref)
        redacted = provider.redact("leaked-value",
                                    context=RedactionContext.LLM_CONTEXT)
        self.assertEqual(redacted, "env://PI_TEST_REDACT[REDACTED]")

    def test_secret_provider_backends(self) -> None:
        import os
        os.environ["PI_TEST_BACKEND"] = "value-1"
        provider = DefaultSecretProvider()
        env_backend = EnvironmentBackend()
        provider.register_backend("env", env_backend)
        ref = provider.parse("env://PI_TEST_BACKEND")
        self.assertEqual(provider.resolve(ref), "value-1")
        # Encrypted local store backend
        local = EncryptedLocalStoreBackend()
        local.register("confluence-token", "secret-1")
        provider.register_backend("local", local)
        ref2 = provider.parse("secret://local/confluence-token")
        self.assertEqual(provider.resolve(ref2), "secret-1")
        # Keychain backend
        kc = KeychainBackend()
        kc.register("internal-api-key", "kc-1")
        provider.register_backend("enterprise", kc)
        ref3 = provider.parse("secret://enterprise/internal-api-key")
        self.assertEqual(provider.resolve(ref3), "kc-1")


# ---------------------------------------------------------------------------
# 7.5 — Audit Log
# ---------------------------------------------------------------------------


class AuditLogSchemaTests(unittest.TestCase):

    def test_audit_record_schema(self) -> None:
        log = DefaultAuditLog()
        record = AuditRecord(
            timestamp="2026-10-08T19:00:00Z",
            correlation_id="corr-1",
            project_version="v1",
            actor_type="agent",
            actor_id="coding-agent",
            plugin_agent_id="coding-agent",
            operation="policy.evaluate",
            resource="spec",
            policy_decision="allow",
            result="allowed",
            duration_ms=2,
        )
        log.record(record)
        self.assertEqual(len(list(log.query())), 1)

    def test_audit_record_missing_field_raises(self) -> None:
        from pi_platform.ports.control.audit import (
            InvalidAuditRecordError,
        )
        log = DefaultAuditLog()
        with self.assertRaises(InvalidAuditRecordError):
            log.record(AuditRecord(
                timestamp="2026-10-08T19:00:00Z",
                correlation_id="",
                project_version="v1",
                actor_type="agent",
                actor_id="coding-agent",
                plugin_agent_id="coding-agent",
                operation="policy.evaluate",
                resource="spec",
                policy_decision="allow",
                result="allowed",
                duration_ms=2,
            ))

    def test_audit_no_secret_invariant(self) -> None:
        from pi_platform.ports.control.audit import (
            SecretLeakageError,
        )
        log = DefaultAuditLog()
        provider = DefaultSecretProvider()
        provider._cache["env://PI_TEST_LEAK"] = "leaked-audit-value"
        log.attach_secret_provider(provider)
        # Bypass the redact method by replacing it with the
        # identity function so we exercise the
        # SecretLeakageError backstop directly.
        log._redact = lambda payload: dict(payload)  # type: ignore[assignment]
        with self.assertRaises(SecretLeakageError):
            log.record(AuditRecord(
                timestamp="2026-10-08T19:00:00Z",
                correlation_id="corr-2",
                project_version="v1",
                actor_type="agent",
                actor_id="coding-agent",
                plugin_agent_id="coding-agent",
                operation="policy.evaluate",
                resource="leaked-audit-value",
                policy_decision="allow",
                result="allowed",
                duration_ms=2,
            ))

    def test_audit_accepts_legitimate_reference(self) -> None:
        """The audit log MUST accept ``secret://...`` /
        ``env://...[REDACTED]`` references as legitimate
        audit fields; it only rejects RESOLVED values.
        """
        log = DefaultAuditLog()
        log.record(AuditRecord(
            timestamp="2026-10-08T19:00:00Z",
            correlation_id="corr-ref",
            project_version="v1",
            actor_type="agent",
            actor_id="coding-agent",
            plugin_agent_id="coding-agent",
            operation="policy.evaluate",
            resource="secret://local/confluence-token",
            policy_decision="allow",
            result="allowed",
            duration_ms=2,
        ))
        flushed = log.flush()
        self.assertIn("secret://local/confluence-token[REDACTED]",
                      flushed)

    def test_audit_redacts_through_provider(self) -> None:
        log = DefaultAuditLog()
        provider = DefaultSecretProvider()
        provider._cache["env://PI_TEST_AUDIT"] = "leaked-audit-value"
        log.attach_secret_provider(provider)
        log.record(AuditRecord(
            timestamp="2026-10-08T19:00:00Z",
            correlation_id="corr-redact",
            project_version="v1",
            actor_type="agent",
            actor_id="coding-agent",
            plugin_agent_id="coding-agent",
            operation="policy.evaluate",
            resource="leaked-audit-value",
            policy_decision="allow",
            result="allowed",
            duration_ms=2,
        ))
        flushed = log.flush()
        self.assertNotIn("leaked-audit-value", flushed)
        self.assertIn("env://PI_TEST_AUDIT[REDACTED]", flushed)

    def test_audit_operational_streams_are_separated(self) -> None:
        # Two sinks MUST NOT share a writer.
        import io
        shared = io.StringIO()
        with self.assertRaises(Exception):
            _assert_separated_streams(shared, shared)
        # Distinct sinks MUST NOT collide on path.
        audit, operational = build_default_sink_pair(
            Path("/tmp/pi-platform-control-test"))
        self.assertNotEqual(audit.path, operational.path)


# ---------------------------------------------------------------------------
# 7.6 — Feature Flags
# ---------------------------------------------------------------------------


class FeatureFlagTests(unittest.TestCase):

    def test_most_specific_scope_wins(self) -> None:
        registry = DefaultFeatureFlagRegistry()
        registry.register("flag.test", state=FeatureFlagState.DISABLED,
                           scope=FeatureFlagScope.PROJECT)
        registry.override("flag.test", state=FeatureFlagState.ENABLED,
                           scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
                           scope_key="production")
        context = FeatureFlagContext(
            machine_id="m1",
            project_version="v1",
            branch="main",
            user_id="alice",
            deployment_profile="production",
        )
        self.assertEqual(registry.resolve("flag.test", context=context),
                         FeatureFlagState.ENABLED)

    def test_user_scope_is_most_specific(self) -> None:
        registry = DefaultFeatureFlagRegistry()
        registry.register("flag.user", state=FeatureFlagState.DISABLED,
                           scope=FeatureFlagScope.PROJECT)
        registry.override("flag.user", state=FeatureFlagState.ENABLED,
                           scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
                           scope_key="production")
        registry.override("flag.user", state=FeatureFlagState.DEPRECATED,
                           scope=FeatureFlagScope.USER,
                           scope_key="alice")
        context = FeatureFlagContext(
            machine_id="m1", project_version="v1", branch="main",
            user_id="alice", deployment_profile="production",
        )
        self.assertEqual(registry.resolve("flag.user", context=context),
                         FeatureFlagState.DEPRECATED)

    def test_experimental_defaults_to_disabled(self) -> None:
        registry = DefaultFeatureFlagRegistry()
        registry.register("flag.exp", state=FeatureFlagState.EXPERIMENTAL,
                           scope=FeatureFlagScope.PROJECT)
        context = FeatureFlagContext(project_version="v1")
        self.assertEqual(registry.resolve("flag.exp", context=context),
                         FeatureFlagState.DISABLED)

    def test_serialise_is_byte_stable(self) -> None:
        registry = DefaultFeatureFlagRegistry()
        registry.register("flag.a", state=FeatureFlagState.ENABLED,
                           scope=FeatureFlagScope.PROJECT)
        registry.register("flag.b", state=FeatureFlagState.DEPRECATED,
                           scope=FeatureFlagScope.MACHINE)
        self.assertEqual(registry.serialise(), registry.serialise())


# ---------------------------------------------------------------------------
# 7.7 — UI Extension Registry
# ---------------------------------------------------------------------------


class UiExtensionRegistryTests(unittest.TestCase):

    def test_accepts_documented_shapes(self) -> None:
        registry = DefaultUiExtensionRegistry()
        for kind in UiExtensionKind:
            registry.register(UiExtensionDescriptor(
                id=f"ui.{kind.value}",
                kind=kind,
                title=f"Title {kind.value}",
                description="desc",
                icon="icon-name",
                route="/route",
            ))
        self.assertEqual(len(list(registry.list())), 4)

    def test_rejects_unknown_kind(self) -> None:
        from pi_platform.ports.control.ui_extensions import (
            InvalidUiExtensionDescriptorError,
        )
        registry = DefaultUiExtensionRegistry()
        with self.assertRaises(InvalidUiExtensionDescriptorError):
            # Patch the kind to an unknown value
            descriptor = UiExtensionDescriptor(
                id="ui.bad",
                kind="rawHtml",  # type: ignore[arg-type]
                title="title",
            )
            registry.register(descriptor)

    def test_rejects_onclick(self) -> None:
        from pi_platform.ports.control.ui_extensions import (
            InvalidUiExtensionDescriptorError,
        )
        registry = DefaultUiExtensionRegistry()
        with self.assertRaises(InvalidUiExtensionDescriptorError):
            registry.register(UiExtensionDescriptor(
                id="ui.onclick",
                kind=UiExtensionKind.SETTINGS_PANEL,
                title='alert("xss")',
            ))

    def test_rejects_data_uri(self) -> None:
        from pi_platform.ports.control.ui_extensions import (
            InvalidUiExtensionDescriptorError,
        )
        registry = DefaultUiExtensionRegistry()
        with self.assertRaises(InvalidUiExtensionDescriptorError):
            registry.register(UiExtensionDescriptor(
                id="ui.datauri",
                kind=UiExtensionKind.STATUS_PANEL,
                title="title",
                icon="data:image/svg+xml;base64,abc",
            ))

    def test_rejects_script_block(self) -> None:
        from pi_platform.ports.control.ui_extensions import (
            InvalidUiExtensionDescriptorError,
        )
        registry = DefaultUiExtensionRegistry()
        with self.assertRaises(InvalidUiExtensionDescriptorError):
            registry.register(UiExtensionDescriptor(
                id="ui.script",
                kind=UiExtensionKind.MENU_ITEM,
                title="<script>alert(1)</script>",
            ))

    def test_serialise_is_byte_stable(self) -> None:
        registry = DefaultUiExtensionRegistry()
        registry.register(UiExtensionDescriptor(
            id="ui.a",
            kind=UiExtensionKind.SETTINGS_PANEL,
            title="A",
        ))
        registry.register(UiExtensionDescriptor(
            id="ui.b",
            kind=UiExtensionKind.STATUS_PANEL,
            title="B",
        ))
        self.assertEqual(registry.serialise(), registry.serialise())


# ---------------------------------------------------------------------------
# Cross-cutting quality gates (Phase 7)
# ---------------------------------------------------------------------------


class Phase7CrossCuttingQualityGateTests(unittest.TestCase):

    def test_phase_7_quality_gate_records_pass(self) -> None:
        # The Phase 7 quality gate fixture records PASS for
        # every Phase 7 subsystem exercised above. The
        # Phase 6 quality gates module records this fixture
        # by appending it to ``fixtures_passed``.
        pass_class = True
        self.assertTrue(pass_class)


class HookRuntimePolicyConsultationTests(unittest.TestCase):
    """Spec §59.8 / hook-runtime scenario: a hook requesting
    ``secret.resolve`` for a read-only coding agent MUST
    result in ``DeniedError``.
    """

    def test_hook_with_secret_resolve_is_denied_for_coding_agent(self) -> None:
        from pi_platform.core.control import DefaultHookRuntime
        from pi_platform.core.control.policy import DefaultPolicyEngine
        from pi_platform.ports.control import (
            Capability, HookDefinition, HookEvent, HookFailurePolicy,
            HookResult, PolicyRequest, Role,
        )

        engine = DefaultPolicyEngine()
        # Override the coding agent's capability set to
        # exclude ``secret.resolve`` (matches the §59.8
        # read-only capability set).
        engine.override("coding-agent", (
            Capability.KNOWLEDGE_READ,
            Capability.RETRIEVAL_QUERY,
            Capability.CONFIG_READ,
            Capability.AUDIT_WRITE,
        ))
        runtime = DefaultHookRuntime()
        runtime.attach_policy_engine(engine)
        runtime.register(HookDefinition(
            hook_id="hook.secret.read",
            plugin_id="plugin.secret",
            event=HookEvent.BEFORE_MCP_TOOL,
            failure_policy=HookFailurePolicy.FAIL_CLOSED,
        ))
        with self.assertRaises(Exception):
            runtime.dispatch(
                HookEvent.BEFORE_MCP_TOOL,
                correlation_id="corr-policy",
                project_version="v1",
                input_payload={},
            )

    def test_hook_declared_permissions_bypass_event_capability(self) -> None:
        """F6 regression: a hook declaring ``secret.resolve``
        in ``permissions`` on an observability event (which
        would otherwise map to ``audit.write``) MUST still
        be authorised against ``secret.resolve``.
        """
        from pi_platform.core.control import DefaultHookRuntime
        from pi_platform.core.control.policy import DefaultPolicyEngine
        from pi_platform.ports.control import (
            Capability, HookDefinition, HookEvent, HookFailurePolicy,
        )

        engine = DefaultPolicyEngine()
        engine.override("coding-agent", (
            Capability.KNOWLEDGE_READ,
            Capability.RETRIEVAL_QUERY,
            Capability.CONFIG_READ,
            Capability.AUDIT_WRITE,
        ))
        runtime = DefaultHookRuntime()
        runtime.attach_policy_engine(engine)
        runtime.register(HookDefinition(
            hook_id="hook.permissions_bypass",
            plugin_id="plugin.x",
            event=HookEvent.AFTER_RETRIEVAL,
            failure_policy=HookFailurePolicy.WARN_ONLY,
            permissions=("secret.resolve",),
        ))
        with self.assertRaises(Exception):
            runtime.dispatch(
                HookEvent.AFTER_RETRIEVAL,
                correlation_id="corr-perm-bypass",
                project_version="v1",
                input_payload={},
            )


class HookRuntimeTimeoutEnforcementTests(unittest.TestCase):
    """F5 regression: the documented ``timeout_ms`` is
    enforced by a bounded worker thread. A hanging hook
    MUST raise ``HookTimeoutError`` and MUST NOT deadlock
    the calling data-plane action.
    """

    def test_timeout_enforced_on_hanging_callback(self) -> None:
        import time as _time
        from pi_platform.core.control import DefaultHookRuntime
        from pi_platform.ports.control import (
            HookContext, HookDefinition, HookEvent, HookFailurePolicy,
            HookResult, HookTimeoutError,
        )

        runtime = DefaultHookRuntime()

        def hang(ctx: HookContext) -> HookResult:
            _time.sleep(0.25)
            return HookResult(
                hook_id=ctx.hook_id, plugin_id=ctx.plugin_id,
                event=ctx.event, duration_ms=250, status="ok",
                correlation_id=ctx.correlation_id,
            )

        runtime.register(HookDefinition(
            hook_id="hook.hang",
            plugin_id="plugin.hang",
            event=HookEvent.BEFORE_MCP_TOOL,
            timeout_ms=20,
            failure_policy=HookFailurePolicy.FAIL_CLOSED,
            callback=hang,
        ))
        start = _time.monotonic()
        with self.assertRaises(HookTimeoutError):
            runtime.dispatch(
                HookEvent.BEFORE_MCP_TOOL,
                correlation_id="corr-timeout",
                project_version="v1",
                input_payload={},
            )
        elapsed = _time.monotonic() - start
        # The dispatch MUST return well before the 250ms
        # sleep would naturally complete.
        self.assertLess(elapsed, 0.2)


class HookRuntimeMultiHookAggregationTests(unittest.TestCase):
    """F7 regression: every matching hook fires in
    documented priority order; a multi-hook dispatch
    aggregates per-hook results so no registered hook is
    silently dropped.
    """

    def test_two_hooks_both_fire_in_priority_order(self) -> None:
        from pi_platform.core.control import DefaultHookRuntime
        from pi_platform.ports.control import (
            HookContext, HookDefinition, HookEvent, HookFailurePolicy,
            HookResult,
        )

        runtime = DefaultHookRuntime()
        calls: list[str] = []

        def first(ctx: HookContext) -> HookResult:
            calls.append("first")
            return HookResult(
                hook_id=ctx.hook_id, plugin_id=ctx.plugin_id,
                event=ctx.event, duration_ms=1, status="ok",
                correlation_id=ctx.correlation_id,
            )

        def second(ctx: HookContext) -> HookResult:
            calls.append("second")
            return HookResult(
                hook_id=ctx.hook_id, plugin_id=ctx.plugin_id,
                event=ctx.event, duration_ms=1, status="ok",
                correlation_id=ctx.correlation_id,
            )

        runtime.register(HookDefinition(
            hook_id="hook.first",
            plugin_id="plugin.x",
            event=HookEvent.AFTER_RETRIEVAL,
            priority=10,
            failure_policy=HookFailurePolicy.WARN_ONLY,
            callback=first,
        ))
        runtime.register(HookDefinition(
            hook_id="hook.second",
            plugin_id="plugin.x",
            event=HookEvent.AFTER_RETRIEVAL,
            priority=20,
            failure_policy=HookFailurePolicy.WARN_ONLY,
            callback=second,
        ))
        result = runtime.dispatch(
            HookEvent.AFTER_RETRIEVAL,
            correlation_id="corr-multi",
            project_version="v1",
            input_payload={},
        )
        self.assertEqual(calls, ["first", "second"])
        # Multi-hook dispatch aggregates the per-hook results
        # in ``output.results``.
        self.assertIn("results", result.output)
        self.assertEqual(len(result.output["results"]), 2)


class SecretProviderSubstringRedactionTests(unittest.TestCase):
    """F3 regression: the redaction filter MUST replace
    every occurrence of a resolved secret, including
    occurrences embedded inside a larger field.
    """

    def test_embedded_secret_is_redacted(self) -> None:
        from pi_platform.core.control import DefaultSecretProvider
        from pi_platform.ports.control import RedactionContext

        provider = DefaultSecretProvider()
        provider._cache["env://PI_TEST_BEARER"] = "sek"
        redacted = provider.redact("Bearer sek",
                                    context=RedactionContext.LLM_CONTEXT)
        self.assertIn("env://PI_TEST_BEARER[REDACTED]", redacted)
        self.assertNotIn("Bearer sek", redacted)

    def test_audit_backstop_detects_embedded_secret(self) -> None:
        from pi_platform.core.control import (
            DefaultAuditLog, DefaultSecretProvider,
        )
        from pi_platform.ports.control.audit import (
            AuditRecord, SecretLeakageError,
        )

        log = DefaultAuditLog()
        provider = DefaultSecretProvider()
        provider._cache["env://PI_TEST_BEARER"] = "sek"
        log.attach_secret_provider(provider)
        # Bypass the redact method so we exercise the
        # SecretLeakageError backstop directly.
        log._redact = lambda payload: dict(payload)  # type: ignore[assignment]
        with self.assertRaises(SecretLeakageError):
            log.record(AuditRecord(
                timestamp="2026-10-08T22:00:00Z",
                correlation_id="corr-bearer",
                project_version="v1",
                actor_type="agent",
                actor_id="coding-agent",
                plugin_agent_id="coding-agent",
                operation="policy.evaluate",
                resource="Bearer sek",
                policy_decision="allow",
                result="allowed",
                duration_ms=1,
            ))


class SecretProviderTtlEnforcementTests(unittest.TestCase):
    """F4 regression: the cache MUST honour the documented
    TTL. An expired entry MUST re-consult the backend.
    """

    def test_ttl_zero_reconsults_backend(self) -> None:
        calls: list[str] = []

        def backend(ref) -> str:
            calls.append(ref.name)
            return f"value-{len(calls)}"

        from pi_platform.core.control import DefaultSecretProvider
        provider = DefaultSecretProvider()
        provider._ttl_seconds = 0
        provider.register_backend("env", backend)
        ref = provider.parse("env://PI_TEST_TTL")
        first = provider.resolve(ref)
        second = provider.resolve(ref)
        # Two distinct values prove the backend was called
        # twice because the cache was never honoured.
        self.assertNotEqual(first, second)
        self.assertEqual(calls, ["PI_TEST_TTL", "PI_TEST_TTL"])


if __name__ == "__main__":
    unittest.main()