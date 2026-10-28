"""Acceptance tests for the dependency research over MCP and A2A.

The two transports are exercised against the **same** fixture and their
answers are compared semantically: the wire wrappers may differ, the
research result may not.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from pi_platform.adapters.research.composition import (
    build_dependency_research_service,
)
from pi_platform.core.a2a import (
    A2aAdapterCore,
    A2aForbidden,
    A2aMessage,
    A2aMessagePart,
    A2aTask,
    A2aUnsupported,
)
from pi_platform.core.research.records import ResearchStatus
from pi_platform.mcp.server import (
    DEFAULT_SERVER_IDENTITY,
    McpServer,
    ToolContext,
)
from pi_platform.ports.a2a import A2aTaskStatus

#: Sentinel for "no research service is wired".
_NOT_WIRED = object()

UV_LOCK = """\
version = 1
revision = 1
requires-python = ">=3.11"

[[package]]
name = "requests"
version = "2.32.3"
source = { registry = "https://pypi.org/simple" }
dependencies = [{ name = "certifi" }]

[[package]]
name = "certifi"
version = "2024.8.30"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "demo"
version = "0.1.0"
source = { editable = "." }
dependencies = [{ name = "requests" }]
"""

POM = """\
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>demo</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>com.google.guava</groupId>
      <artifactId>guava</artifactId>
      <version>33.2.1-jre</version>
    </dependency>
  </dependencies>
</project>
"""


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class ResearchFixture(unittest.TestCase):
    """A project with a Python lock and a Maven build."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "project"
        self.root.mkdir(parents=True)
        (self.root / "uv.lock").write_text(UV_LOCK, encoding="utf-8")
        (self.root / "pom.xml").write_text(POM, encoding="utf-8")
        self.service = build_dependency_research_service(project_root=self.root)

    def mcp_server(self, *, research=_NOT_WIRED) -> McpServer:
        context = ToolContext(
            readiness=MagicMock(is_ready=MagicMock(return_value=True),
                                snapshot=MagicMock()),
            capability_discovery=MagicMock(),
            orchestrator=MagicMock(),
            task_context_builder=MagicMock(),
            multi_stage_retrieval=MagicMock(),
            hybrid_retrieval=MagicMock(),
            context_assembler=MagicMock(),
            boundary=MagicMock(),
            version_policy=MagicMock(),
            server_identity=DEFAULT_SERVER_IDENTITY,
            repo_root=self.root,
            cache_root=self.root / ".cache",
            dependency_research=(self.service if research is _NOT_WIRED
                                 else research),
        )
        return McpServer(context=context)

    def a2a_adapter(self, *, research=_NOT_WIRED, enabled: bool = True,
                    policy: str = "ALLOW") -> A2aAdapterCore:
        return A2aAdapterCore(
            flags_provider=lambda name: enabled,
            policy_gate=lambda **_: policy,
            research=(self.service if research is _NOT_WIRED else research),
        )

    def research_task(self, operation: str, arguments: dict,
                      *, schema_version: int = 1) -> A2aTask:
        return A2aTask(
            task_id="task-research",
            session_id=None,
            messages=(A2aMessage(role="user", parts=(A2aMessagePart(
                kind="data",
                data={"schema_version": schema_version, "operation": operation,
                      "arguments": arguments}),)),),
            metadata={},
        )


# ---------------------------------------------------------------------------
# MCP
# ---------------------------------------------------------------------------


class McpDependencyResearchTests(ResearchFixture):
    def test_the_research_tools_are_advertised(self):
        server = self.mcp_server()
        for name in ("project.dependency_tree", "project.dependency_search",
                     "project.dependency_read", "project.dependency_acquire"):
            self.assertIn(name, server.tool_names)

    def test_the_tree_tool_returns_the_evidence_backed_graph(self):
        server = self.mcp_server()
        result = _run(server.call_tool("project.dependency_tree",
                                       {"ecosystem": "python"}))
        self.assertTrue(result["ok"])
        names = {node["package"]["name"] for node in result["research"]["nodes"]}
        self.assertEqual(names, {"demo", "requests", "certifi"})
        self.assertEqual(result["status"], "complete")

    def test_the_tree_tool_honours_the_limits_and_reports_truncation(self):
        server = self.mcp_server()
        result = _run(server.call_tool("project.dependency_tree",
                                       {"ecosystem": "python", "max_nodes": 2}))
        self.assertTrue(result["truncated"])
        self.assertTrue(result["cursor"])

    def test_the_search_tool_returns_symbol_cards(self):
        server = self.mcp_server()
        result = _run(server.call_tool("project.dependency_search",
                                       {"ecosystem": "python",
                                        "package_ref": "",
                                        "query": "nothing-matches"}))
        self.assertTrue(result["ok"])
        self.assertEqual(list(result["research"]["excerpts"]), [])

    def test_the_acquire_tool_is_refused_without_an_approved_source(self):
        server = self.mcp_server()
        result = _run(server.call_tool("project.dependency_acquire",
                                       {"ecosystem": "python", "name": "requests",
                                        "version": "2.32.3", "source_id": "pypi"}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "denied")

    def test_the_legacy_maven_lookup_answers_with_real_evidence(self):
        server = self.mcp_server()
        result = _run(server.call_tool("project.get_dependency", {
            "group": "com.google.guava", "artifact": "guava",
            "version": "33.2.1-jre"}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["dependency"]["status"], "complete")
        # The coordinate is declared by the build. Without a resolved
        # closure the answer says so instead of inventing a resolution.
        self.assertEqual(result["dependency"]["declaredVersions"],
                         ["33.2.1-jre"])
        self.assertEqual(result["dependency"]["resolvedVersions"], [])
        self.assertFalse(result["dependency"]["resolved"])
        self.assertNotIn("note", result["dependency"])

    def test_the_legacy_maven_lookup_says_when_the_coordinate_is_absent(self):
        server = self.mcp_server()
        result = _run(server.call_tool("project.get_dependency", {
            "group": "com.example", "artifact": "absent",
            "version": "1.0.0"}))
        self.assertFalse(result["ok"])
        self.assertEqual(result["dependency"]["status"], "unavailable")
        self.assertNotIn("note", result["dependency"])

    def test_without_a_research_service_the_tools_report_the_missing_capability(self):
        server = self.mcp_server(research=None)
        result = _run(server.call_tool("project.dependency_tree",
                                       {"ecosystem": "python"}))
        self.assertFalse(result["ok"])
        self.assertIn("not enabled", result["error"]["message"])


# ---------------------------------------------------------------------------
# A2A
# ---------------------------------------------------------------------------


class A2aDependencyResearchTests(ResearchFixture):
    def actor(self) -> dict:
        return {"id": "agent-1", "capabilities": {"a2a.invoke": True}}

    def test_a_research_envelope_returns_a_research_artifact(self):
        adapter = self.a2a_adapter()
        result = adapter.invoke(
            actor=self.actor(),
            task=self.research_task("dependency.tree", {"ecosystem": "python"}))
        self.assertEqual(result.status, A2aTaskStatus.COMPLETED)
        self.assertEqual(len(result.artifacts), 1)
        artifact = result.artifacts[0]
        self.assertEqual(artifact.name, "research")
        body = json.loads(artifact.text)
        self.assertEqual(body["operation"], "dependency.tree")
        names = {node["package"]["name"]
                 for node in body["result"]["nodes"]}
        self.assertEqual(names, {"demo", "requests", "certifi"})

    def test_an_unknown_research_operation_is_rejected_not_acknowledged(self):
        adapter = self.a2a_adapter()
        with self.assertRaises(A2aUnsupported):
            adapter.invoke(
                actor=self.actor(),
                task=self.research_task("dependency.teleport", {"ecosystem": "python"}))

    def test_an_unsupported_envelope_version_is_rejected(self):
        adapter = self.a2a_adapter()
        with self.assertRaises(A2aUnsupported):
            adapter.invoke(
                actor=self.actor(),
                task=self.research_task("dependency.tree", {"ecosystem": "python"},
                                        schema_version=99))

    def test_a_research_envelope_without_a_service_is_rejected(self):
        adapter = self.a2a_adapter(research=None)
        with self.assertRaises(A2aUnsupported):
            adapter.invoke(
                actor=self.actor(),
                task=self.research_task("dependency.tree", {"ecosystem": "python"}))

    def test_the_legacy_task_still_acknowledges(self):
        adapter = self.a2a_adapter()
        result = adapter.invoke(
            actor=self.actor(),
            task=A2aTask(task_id="legacy", session_id=None,
                         messages=(A2aMessage(role="user", parts=(
                             A2aMessagePart(kind="text", text="hi"),)),),
                         metadata={}))
        self.assertEqual(result.artifacts[0].name, "ack")

    def test_a_disabled_surface_rejects_the_research_request(self):
        adapter = self.a2a_adapter(enabled=False)
        with self.assertRaises(A2aUnsupported):
            adapter.invoke(
                actor=self.actor(),
                task=self.research_task("dependency.tree", {"ecosystem": "python"}))

    def test_a_denied_actor_rejects_the_research_request(self):
        adapter = self.a2a_adapter(policy="DENY")
        with self.assertRaises(A2aForbidden):
            adapter.invoke(
                actor=self.actor(),
                task=self.research_task("dependency.tree", {"ecosystem": "python"}))

    def test_an_unsupported_ecosystem_is_reported_not_acknowledged(self):
        adapter = self.a2a_adapter()
        with self.assertRaises(A2aUnsupported):
            adapter.invoke(
                actor=self.actor(),
                task=self.research_task("dependency.tree", {"ecosystem": "rust"}))


# ---------------------------------------------------------------------------
# Both transports
# ---------------------------------------------------------------------------


class CrossTransportTests(ResearchFixture):
    def test_both_transports_answer_the_same_question_with_the_same_evidence(self):
        server = self.mcp_server()
        adapter = self.a2a_adapter()
        mcp_result = _run(server.call_tool("project.dependency_tree",
                                           {"ecosystem": "python"}))
        a2a_result = adapter.invoke(
            actor={"id": "agent-1", "capabilities": {"a2a.invoke": True}},
            task=self.research_task("dependency.tree", {"ecosystem": "python"}))
        a2a_body = json.loads(a2a_result.artifacts[0].text)
        self.assertEqual(mcp_result["research"]["nodes"],
                         a2a_body["result"]["nodes"])
        self.assertEqual(mcp_result["research"]["edges"],
                         a2a_body["result"]["edges"])
        self.assertEqual(mcp_result["research"]["status"],
                         a2a_body["result"]["status"])

    def test_a_stale_cursor_is_rejected_by_both_transports(self):
        server = self.mcp_server()
        adapter = self.a2a_adapter()
        truncated = _run(server.call_tool("project.dependency_tree",
                                          {"ecosystem": "python", "max_nodes": 2}))
        self.assertTrue(truncated["truncated"])
        cursor = truncated["cursor"]
        stale = _run(server.call_tool("project.dependency_tree",
                                      {"ecosystem": "python", "max_nodes": 2,
                                       "max_depth": 3, "cursor": cursor}))
        self.assertFalse(stale["ok"])
        self.assertEqual(stale["error"]["type"], "StaleResearchCursor")
        with self.assertRaises(Exception):
            adapter.invoke(
                actor={"id": "agent-1", "capabilities": {"a2a.invoke": True}},
                task=self.research_task("dependency.tree", {
                    "ecosystem": "python", "max_nodes": 2, "max_depth": 3,
                    "cursor": cursor}))

    def test_an_excessive_budget_is_clamped_and_reported(self):
        server = self.mcp_server()
        result = _run(server.call_tool("project.dependency_tree",
                                       {"ecosystem": "python",
                                        "max_nodes": 100000,
                                        "max_depth": 1000}))
        limits = result["research"]["limits"]
        self.assertEqual(limits["maxNodes"], 1000)
        self.assertEqual(limits["maxDepth"], 20)

    def test_the_capability_discovery_reports_the_research_capability(self):
        from pi_platform.core.orchestration.capability_discovery import (
            DefaultCapabilityDiscovery,
        )

        descriptor = DefaultCapabilityDiscovery(
            dependency_research=self.service).describe().as_dict()
        block = descriptor["protocols"]["dependencyResearch"]
        self.assertTrue(block["enabled"])
        self.assertEqual(block["ecosystems"], ["java", "node", "python"])
        self.assertFalse(block["acquisitionEnabled"])

    def test_the_capability_discovery_hides_an_unwired_capability(self):
        from pi_platform.core.orchestration.capability_discovery import (
            DefaultCapabilityDiscovery,
        )

        descriptor = DefaultCapabilityDiscovery().describe().as_dict()
        self.assertNotIn("dependencyResearch", descriptor.get("protocols") or {})

    def test_the_capability_report_states_what_the_deployment_can_do(self):
        capabilities = self.service.capabilities()
        self.assertIn("python", capabilities["ecosystems"])
        self.assertFalse(capabilities["acquisition"]["enabled"])
        self.assertEqual(capabilities["ecosystems"]["node"]["parser"]["parser"],
                         "tree-sitter")


if __name__ == "__main__":
    unittest.main()
