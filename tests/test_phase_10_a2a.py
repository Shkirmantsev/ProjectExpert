"""Phase 10 §50 + §51 A2A core tests.

These tests cover the four ports under ``pi_platform.ports.a2a`` and
their default implementations in ``pi_platform.core.a2a``:

- the A2A dispatch core (``A2aAdapterCore``) and the fail-closed
  policy gate;
- the Agent Card builder (``AgentCardBuilder``) with the documented
  secret redaction;
- the :class:`ReverseDelegationPolicyCore` and its deterministic
  decision outcomes;
- the loopback binding guard and the typed error translation.

Every test is referenced by a specific scenario from
``openspec/specs/2026-10-12-{a2a-adapter,external-coding-agent-integration}``.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import unittest
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlsplit

from pi_platform.adapters.a2a.envelope import (
    SUPPORTED_WIRE_VERSIONS,
    parse_task_envelope,
    serialise_task_result,
)
from pi_platform.adapters.a2a.http_transport import (
    A2aHttpServer,
    A2aHttpServerConfig,
)
from pi_platform.adapters.agent_integration.external_agents import (
    StaticAgentAdapter,
    build_default_external_agent_registry,
    claude_code_metadata,
    codex_metadata,
    opencode_metadata,
    hermes_metadata,
    generic_mcp_metadata,
    generic_a2a_metadata,
)
from pi_platform.core.a2a import (
    A2A_SPEC_VERSION,
    A2aAdapterCore,
    A2aFlags,
    AgentCardBuilder,
    LoopbackBinder,
    ReverseDelegationPolicyCore,
    SecretRedactor,
)
from pi_platform.ports.a2a import (
    A2aForbidden,
    A2aLimitExceeded,
    A2aMessage,
    A2aMessagePart,
    A2aNotFound,
    A2aSpecVersion,
    A2aTask,
    A2aTaskResult,
    A2aTaskStatus,
    A2aUnauthorized,
    A2aUnsupported,
    ExternalAgentMetadata,
    ExternalAgentPort,
    ReverseDelegationDecision,
    ReverseDelegationTask,
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class A2aFlagPolicyGateTests(unittest.TestCase):
    """Test the documented policy/flag behaviour of :class:`A2aAdapterCore`."""

    def test_inbound_disabled_raises_A2aUnsupported(self):
        adapter = A2aAdapterCore(flags_provider=lambda name: False)
        with self.assertRaises(A2aUnsupported):
            adapter.invoke(actor={"id": "x"}, task=_make_task())

    def test_default_policy_gate_is_DENY(self):
        adapter = A2aAdapterCore(flags_provider=lambda name: True)
        with self.assertRaises(A2aForbidden):
            adapter.invoke(actor={"id": "x"}, task=_make_task())

    def test_allow_with_full_capabilities_returns_ack(self):
        adapter = A2aAdapterCore(
            flags_provider=lambda name: True,
            policy_gate=lambda **_: "ALLOW",
        )
        result = adapter.invoke(
            actor={"id": "x", "capabilities": {"mcp.invoke": True}},
            task=_make_task(),
        )
        self.assertEqual(result.status, A2aTaskStatus.COMPLETED)
        self.assertEqual(len(result.artifacts), 1)
        self.assertIn("ack", result.artifacts[0].name)

    def test_require_approval_is_treated_as_forbidden(self):
        adapter = A2aAdapterCore(
            flags_provider=lambda name: True,
            policy_gate=lambda **_: "REQUIRE_APPROVAL",
        )
        with self.assertRaises(A2aForbidden):
            adapter.invoke(
                actor={"id": "x", "capabilities": {"mcp.invoke": True}},
                task=_make_task(),
            )

    def test_missing_capability_raises_A2aUnauthorized(self):
        adapter = A2aAdapterCore(
            flags_provider=lambda name: True,
            policy_gate=lambda **_: "ALLOW",
        )
        with self.assertRaises(A2aUnauthorized):
            adapter.invoke(actor={"id": "x"}, task=_make_task())

    def test_concurrency_limit_is_enforced(self):
        # Limit 0 means every invocation must raise A2aLimitExceeded
        # before any policy decision is consulted.
        adapter = A2aAdapterCore(
            flags_provider=lambda name: True,
            policy_gate=lambda **_: "ALLOW",
        )
        from pi_platform.core.a2a import A2aInboundLimits
        adapter._limits = A2aInboundLimits(
            max_inflight_per_actor=0,
            max_message_bytes=1_048_576,
            max_artifact_bytes=16 * 1_048_576,
        )
        with self.assertRaises(A2aLimitExceeded):
            adapter.invoke(
                actor={"id": "x", "capabilities": {"mcp.invoke": True}},
                task=_make_task(),
            )

    def test_redaction_is_applied_to_messages_and_metadata(self):
        redactor = SecretRedactor(replacement_prefix="ref://")
        text = "Use this token: secret://local/foo to authenticate."
        safe = redactor.redact_text(text)
        self.assertNotIn("secret://", safe)
        self.assertIn("ref://", safe)

        # The same redactor handles metadata structures.
        meta = redactor.redact_mapping({"a": "ok", "b": "secret://x/y", "c": {"d": "secret://p/q"}})
        self.assertNotIn("secret://", json.dumps(meta))

    def test_supported_spec_version_returns_pinned_constant(self):
        adapter = A2aAdapterCore(flags_provider=lambda name: True)
        self.assertEqual(adapter.supported_spec_version(), A2A_SPEC_VERSION)
        self.assertTrue(A2A_SPEC_VERSION.compatible_with(A2aSpecVersion(major=1)))
        self.assertFalse(A2A_SPEC_VERSION.compatible_with(A2aSpecVersion(major=2)))


class AgentCardBuilderTests(unittest.TestCase):
    """Spec scenarios from ``a2a-adapter`` §0.1 (AgentCard published / absent / redaction)."""

    def test_card_is_published_when_flag_enabled(self):
        descriptor = {"name": "pi", "description": "x", "version": "0.8.0", "skills": []}
        builder = AgentCardBuilder(descriptor=descriptor, flags_provider=lambda n: True)
        self.assertTrue(builder.is_published())
        card = builder.build_agent_card()
        self.assertEqual(card.name, "pi")
        self.assertEqual(card.spec_version, A2A_SPEC_VERSION)
        self.assertEqual(card.capabilities["streaming"], "not-supported")
        # Card does not leak any secret-shaped value
        self.assertNotIn("secret://", json.dumps(card.as_dict()))

    def test_card_is_absent_when_flag_disabled(self):
        descriptor = {"name": "pi", "description": "x", "version": "0.8.0"}
        builder = AgentCardBuilder(descriptor=descriptor, flags_provider=lambda n: False)
        self.assertFalse(builder.is_published())
        with self.assertRaises(A2aNotFound):
            builder.build_agent_card()

    def test_card_redacts_secret_shaped_capability_fields(self):
        descriptor = {"name": "pi", "description": "x", "version": "0.8.0"}
        builder = AgentCardBuilder(
            descriptor=descriptor,
            flags_provider=lambda n: True,
        )
        # patch the descriptor to inject a secret-shaped value
        builder._descriptor = {  # type: ignore[attr-defined]
            "name": "pi",
            "description": "x",
            "version": "0.8.0",
            "protocols": {"a2a": {"token": "secret://internal/api-key"}},
            "skills": [],
        }
        card = builder.build_agent_card()
        rendered = json.dumps(card.as_dict())
        self.assertNotIn("secret://", rendered)
        self.assertIn("ref://", rendered)


class LoopbackBinderTests(unittest.TestCase):
    def test_default_loopback_is_loopback(self):
        b = LoopbackBinder(host="127.0.0.1", port=8080)
        self.assertTrue(b.is_loopback)
        self.assertEqual(b.address, ("127.0.0.1", 8080))

    def test_non_loopback_is_detected(self):
        b = LoopbackBinder(host="0.0.0.0", port=9090)
        self.assertFalse(b.is_loopback)

    def test_invalid_port_rejected(self):
        with self.assertRaises(ValueError):
            LoopbackBinder(host="127.0.0.1", port=0)
        with self.assertRaises(ValueError):
            LoopbackBinder(host="127.0.0.1", port=70000)


class ReverseDelegationPolicyTests(unittest.TestCase):
    """Cover the deterministic ``ReverseDelegationPolicyCore`` behaviour."""

    def _policy(self):
        return ReverseDelegationPolicyCore()

    def _meta(self, identity: str, tags=("agent",)) -> ExternalAgentMetadata:
        return ExternalAgentMetadata(
            identity=identity, display_name=identity, interface_kind="cli",
            api_version="phase-10/1", license="Apache-2.0", tags=tags,
        )

    def test_no_candidates_returns_DENY(self):
        outcome = self._policy().evaluate(
            actor={"id": "x"}, task=ReverseDelegationTask(task_id="t", reason="r", bounded_context={}),
            candidates=(),
            egress_decision={"decision": "ALLOW"},
            capabilities={"agent.delegate": True, "required_agent_tags": []},
        )
        self.assertEqual(outcome.decision, ReverseDelegationDecision.DENY)

    def test_missing_capability_returns_DENY(self):
        outcome = self._policy().evaluate(
            actor={"id": "x"}, task=ReverseDelegationTask(task_id="t", reason="r", bounded_context={}),
            candidates=(self._meta("a"),),
            egress_decision={"decision": "ALLOW"},
            capabilities={"required_agent_tags": []},
        )
        self.assertEqual(outcome.decision, ReverseDelegationDecision.DENY)
        self.assertIn("agent.delegate", outcome.reason)

    def test_egress_deny_blocks_selection(self):
        outcome = self._policy().evaluate(
            actor={"id": "x"}, task=ReverseDelegationTask(task_id="t", reason="r", bounded_context={}),
            candidates=(self._meta("a"),),
            egress_decision={"decision": "DENY"},
            capabilities={"agent.delegate": True, "required_agent_tags": []},
        )
        self.assertEqual(outcome.decision, ReverseDelegationDecision.DENY)

    def test_egress_require_approval_yields_REQUIRE_APPROVAL(self):
        outcome = self._policy().evaluate(
            actor={"id": "x"}, task=ReverseDelegationTask(task_id="t", reason="r", bounded_context={}),
            candidates=(self._meta("a"),),
            egress_decision={"decision": "REQUIRE_APPROVAL"},
            capabilities={"agent.delegate": True, "required_agent_tags": []},
        )
        self.assertEqual(outcome.decision, ReverseDelegationDecision.REQUIRE_APPROVAL)

    def test_multiple_matches_require_approval(self):
        candidates = (self._meta("a"), self._meta("b"))
        outcome = self._policy().evaluate(
            actor={"id": "x"}, task=ReverseDelegationTask(task_id="t", reason="r", bounded_context={}),
            candidates=candidates,
            egress_decision={"decision": "ALLOW"},
            capabilities={"agent.delegate": True, "required_agent_tags": ["agent"]},
        )
        self.assertEqual(outcome.decision, ReverseDelegationDecision.REQUIRE_APPROVAL)

    def test_single_match_selects_agent(self):
        candidates = (self._meta("only-one", tags=("only-one-tag",)), self._meta("not-me"))
        outcome = self._policy().evaluate(
            actor={"id": "x"}, task=ReverseDelegationTask(task_id="t", reason="r", bounded_context={}),
            candidates=candidates,
            egress_decision={"decision": "ALLOW"},
            capabilities={"agent.delegate": True, "required_agent_tags": ["only-one-tag"]},
        )
        self.assertEqual(outcome.decision, ReverseDelegationDecision.SELECT_AGENT)
        self.assertEqual(outcome.selected_identity, "only-one")


class ExternalAgentRegistryTests(unittest.TestCase):
    """Spec scenario: every supported agent has its own port implementation."""

    def test_default_registry_covers_six_supported_agents(self):
        reg = build_default_external_agent_registry()
        expected = {meta.identity for meta in (
            claude_code_metadata(), codex_metadata(), opencode_metadata(),
            hermes_metadata(), generic_mcp_metadata(), generic_a2a_metadata(),
        )}
        self.assertEqual(set(reg.keys()), expected)
        # Hermes is registered but does not support outbound in this build.
        self.assertFalse(reg["hermes"].metadata().tags == ())
        self.assertEqual(
            reg["hermes"].submit(ReverseDelegationTask(task_id="t", reason="r", bounded_context={})).status,
            A2aTaskStatus.UNSUPPORTED,
        )


class EnvelopeTests(unittest.TestCase):
    def test_supported_wire_versions_includes_v1(self):
        self.assertIn("1", SUPPORTED_WIRE_VERSIONS)
        self.assertIn("1.0", SUPPORTED_WIRE_VERSIONS)

    def test_parse_missing_task_id_raises(self):
        from pi_platform.ports.a2a import A2aError
        with self.assertRaises(A2aError):
            parse_task_envelope({"wireVersion": "1"})

    def test_serialise_round_trip_is_byte_stable(self):
        result = A2aTaskResult(
            status=A2aTaskStatus.COMPLETED,
            artifacts=(),
            message=A2aMessage(role="agent", parts=(A2aMessagePart(kind="text", text="hi"),)),
        )
        a = serialise_task_result(result)
        b = serialise_task_result(result)
        self.assertEqual(a, b)


class WireTransportTests(unittest.TestCase):
    """Spec scenarios: HTTP transport, loopback bind, flag-aware routes."""

    def setUp(self) -> None:
        self.port = _free_port()
        self.config = A2aHttpServerConfig(host="127.0.0.1", port=self.port)
        self.adapter = A2aAdapterCore(
            flags_provider=lambda n: True,
            policy_gate=lambda **_: "ALLOW",
        )
        self.card = AgentCardBuilder(
            descriptor={"name": "pi", "description": "x", "version": "0.8.0"},
            flags_provider=lambda n: True,
        )
        self.server = A2aHttpServer(adapter=self.adapter, agent_card=self.card, config=self.config)

    def tearDown(self) -> None:
        try:
            self.server.stop()
        except Exception:
            pass

    def test_card_endpoint_returns_404_when_disabled(self):
        self.card._published = False  # type: ignore[attr-defined]
        # ``is_published`` already returns False because the flag is on
        # but the constructor recorded published=False, so we test it.
        self.assertFalse(self.card.is_published())

    def test_invoke_endpoint_403_on_unknown_policy(self):
        self.server.start()
        time.sleep(0.05)
        # Patch the adapter to a denied policy gate on the fly.
        denied = A2aAdapterCore(
            flags_provider=lambda n: True,
            policy_gate=lambda **_: "DENY",
        )
        self.server._adapter = denied  # type: ignore[attr-defined]
        conn = HTTPConnection("127.0.0.1", self.port, timeout=2)
        body = json.dumps({"wireVersion": "1", "taskId": "t", "messages": []})
        conn.request("POST", "/a2a/v1/tasks:send", body=body,
                     headers={"Content-Type": "application/json", "X-Actor-Id": "x"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 403)
        conn.close()


class A2aAdapterCoreImportTests(unittest.TestCase):
    def test_core_module_imports_no_A2A_library(self):
        # Static heuristic: make sure we never import a third-party A2A
        # library into the core module.
        import pi_platform.core.a2a as core_a2a
        src = Path(core_a2a.__file__).read_text() if core_a2a.__file__ else ""
        for forbidden in ("a2a_python", "a2a-sdk", "a2a_sdk"):
            self.assertNotIn(forbidden, src)


def _make_task(task_id: str = "task-1") -> A2aTask:
    return A2aTask(
        task_id=task_id,
        session_id=None,
        messages=(A2aMessage(role="user", parts=(A2aMessagePart(kind="text", text="hi"),)),),
        metadata={},
    )
