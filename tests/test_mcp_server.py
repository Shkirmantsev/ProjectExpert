"""Phase 6 task 85 — MCP server dispatch tests.

The tests exercise the deterministic dispatch table without
involving the official MCP SDK. The actual SDK session tests
(integration tests) are run with the venv that has the SDK
installed and gate on ``MCP_SDK_AVAILABLE``.
"""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from typing import Mapping
from unittest.mock import MagicMock

from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
from pi_platform.core.orchestration.capability_discovery import (
    DefaultCapabilityDiscovery,
)
from pi_platform.mcp.server import (
    DEFAULT_SERVER_IDENTITY,
    McpServer,
    McpServerError,
    SECTION_36_TOOLS,
    ToolContext,
)
from pi_platform.ports import HydrateReport, ReconcileReport, VersionIdentity


__all__ = ["McpServerDispatchTests"]


def _build_context(readiness_ready: bool = True) -> ToolContext:
    boundary = HmacTrustedApprovalBoundary(key=b"test")
    discovery = DefaultCapabilityDiscovery()
    orchestrator = MagicMock()
    builder = MagicMock()
    builder.build.return_value = MagicMock(taskId="t-1", goal="g",
                                           budgetTokens=100, items=())
    ms = MagicMock()
    ms.retrieve.return_value = MagicMock(
        hits=(), stageReports=(), budgetUsed=0,
    )
    hybrid = MagicMock()
    assembler = MagicMock()
    assembler.assemble.return_value = MagicMock(items=(), budget_tokens=100)
    gate = DefaultKnowledgeReadiness()
    if readiness_ready:
        gate.record_hydrate(HydrateReport(
            project_version=VersionIdentity(
                gitHead="abc", workingTreeFingerprint="f",
                knowledgeSchemaVersion="0.7.0",
                embeddingModelVersion="x",
                indexSchemaVersion="0.1.0",
            ),
            families={"chunks": 1},
            cache_hit_rates={"chunks": 1.0},
        ))
        gate.record_reconcile(ReconcileReport(
            families={"chunks": 1},
            reused_shards={"chunks": 1},
            re_ingested_shards={"chunks": 0},
        ), current_head="abc", working_tree_fingerprint="f")
    return ToolContext(
        readiness=gate,
        capability_discovery=discovery,
        orchestrator=orchestrator,
        task_context_builder=builder,
        multi_stage_retrieval=ms,
        hybrid_retrieval=hybrid,
        context_assembler=assembler,
        boundary=boundary,
        version_policy=MagicMock(),
        server_identity=DEFAULT_SERVER_IDENTITY,
        repo_root=Path("/tmp"),
        cache_root=Path("/tmp/cache"),
    )


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class McpServerDispatchTests(unittest.TestCase):

    def setUp(self) -> None:
        self.context = _build_context()
        self.server = McpServer(context=self.context)

    def test_section_36_tools_listed(self):
        # All 17 §36 tools MUST be registered.
        self.assertEqual(len(self.server.section_36_tools), 17)
        for name in SECTION_36_TOOLS:
            self.assertIn(name, self.server.tool_names)

    def test_describe_capabilities_is_extension_not_section_36(self):
        self.assertIn("project.describe_capabilities",
                      self.server.extension_tools)
        # describe_capabilities MUST NOT shadow any §36 name.
        for section_name in self.server.section_36_tools:
            self.assertNotEqual(section_name,
                                "project.describe_capabilities")

    def test_unknown_tool_returns_typed_error(self):
        result = _run(self.server.call_tool(
            "project.unknown", {},
        ))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "UnknownToolError")

    def test_read_search_call_routes_to_retrieval(self):
        result = _run(self.server.call_tool(
            "project.search",
            {"text": "OrderStatus", "top_k": 5},
        ))
        self.assertTrue(result["ok"])
        self.context.multi_stage_retrieval.retrieve.assert_called()

    def test_read_tool_rejected_when_runtime_not_ready(self):
        ctx = _build_context(readiness_ready=False)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.search", {"text": "OrderStatus"},
        ))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "RuntimeNotReadyError")

    def test_write_tool_requires_approval_id(self):
        result = _run(self.server.call_tool(
            "project.materialize_knowledge", {"approval_id": ""},
        ))
        self.assertFalse(result["ok"])
        # The boundary's ClosedTrustedApprovalBoundary default
        # rejects "no_issuer_key" / missing; with our HMAC key
        # the boundary verifies a forged-empty token as missing.
        self.assertIn("error", result)

    def test_describe_capabilities_returns_descriptor(self):
        result = _run(self.server.call_tool(
            "project.describe_capabilities", {},
        ))
        self.assertTrue(result["ok"])
        self.assertIn("descriptor", result)
        self.assertIn("serverIdentity", result)
        self.assertEqual(result["serverIdentity"]["name"],
                         "project-intelligence")

    def test_describe_capabilities_honest_dimensions(self):
        result = _run(self.server.call_tool(
            "project.describe_capabilities", {},
        ))
        descriptor = result["descriptor"]
        self.assertIn("dimensions", descriptor)
        dims = descriptor["dimensions"]
        self.assertFalse(dims["a2aAdapterVersion"]["available"])
        self.assertFalse(dims["agentAdapterVersion"]["available"])
        self.assertEqual(dims["a2aAdapterVersion"]["value"], None)
        self.assertEqual(dims["agentAdapterVersion"]["value"], None)

    def test_get_project_version_uses_snapshot(self):
        result = _run(self.server.call_tool(
            "project.get_project_version", {},
        ))
        self.assertTrue(result["ok"])
        self.assertTrue(result["consistent"])

    def test_build_task_context_routes_to_task_context_builder(self):
        result = _run(self.server.call_tool(
            "project.build_task_context",
            {"goal": "Implement REQ-471", "budget_tokens": 500},
        ))
        self.assertTrue(result["ok"])
        self.context.task_context_builder.build.assert_called()

    def test_get_entity_reports_missing_evidence_not_fabricated(self):
        result = _run(self.server.call_tool(
            "project.get_entity",
            {"entity_id": "OrderStatus"},
        ))
        self.assertTrue(result["ok"])
        # Prerequisite 4: missing evidence is reported as missing.
        self.assertEqual(result["evidence"], [])
        self.assertIn("not implemented", result["evidence_text"])

    def test_materialize_with_boundary_issued_token(self):
        from pi_platform.ports import ApprovalRequest
        token = self.context.boundary.issue(
            ApprovalRequest(action="materialise",
                            repo_root="/tmp",
                            change_ids=()),
            ttl_seconds=60,
        )
        result = _run(self.server.call_tool(
            "project.materialize_knowledge",
            {"approval_id": token, "repo_root": "/tmp",
             "cache_root": "/tmp/cache", "change_ids": []},
        ))
        self.assertTrue(result["ok"])
        self.assertIn("grant", result)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()