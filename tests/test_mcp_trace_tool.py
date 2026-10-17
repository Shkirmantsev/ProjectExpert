"""MCP ``project.get_retrieval_trace`` debug-only tool tests.

Change Package I of the v0.8 refinement ships the debug-only
``project.get_retrieval_trace(trace_id)`` MCP tool described in
plan §33. The tests assert:

* the tool is hidden outside debug mode;
* the tool returns ``DebugModeRequiredError`` when called
  outside debug mode;
* the tool returns ``TraceNotFoundError`` for unknown ids;
* the tool returns the redacted retrieval trace JSON for known
  ids;
* the trace store receives a single record per
  ``retrieve_context`` call with ``include_trace=True`` and
  debug mode on.
"""

from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from pi_platform.adapters.retrieval.in_memory_trace_store import (
    InMemoryRetrievalTraceStore,
)
from pi_platform.core.orchestration.capability_discovery import (
    DefaultCapabilityDiscovery,
)
from pi_platform.core.retrieval.retrieval_trace import RetrievalTrace
from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
from pi_platform.mcp.server import (
    DEFAULT_SERVER_IDENTITY,
    DEBUG_TOOLS,
    DebugModeRequiredError,
    McpServer,
    McpServerError,
    ToolContext,
    TraceNotFoundError,
)
from pi_platform.ports import HydrateReport, ReconcileReport, VersionIdentity


__all__ = ["McpTraceToolTests"]


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build_context(
    *, debug_mode: bool, trace: object | None = None,
    trace_store: object | None = None,
) -> ToolContext:
    boundary = HmacTrustedApprovalBoundary(key=b"test")
    discovery = DefaultCapabilityDiscovery()
    orchestrator = MagicMock()
    builder = MagicMock()
    builder.build.return_value = MagicMock(taskId="t-1", goal="g",
                                           budgetTokens=100, items=())
    ms = MagicMock()
    ms.retrieve.return_value = MagicMock(
        hits=(), stageReports=(), budgetUsed=0,
        primary_count=0, reserve_count=0, protected_count=0,
        support_count=0, selection_result=None,
        conflicts=(), trace=trace,
    )
    hybrid = MagicMock()
    assembler = MagicMock()
    assembler.assemble.return_value = MagicMock(
        items=(), budget_tokens=100,
        conflictingHits=(), support_hits=(), citations=(),
        selection_summary={},
    )
    gate = DefaultKnowledgeReadiness()
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
        trace_store=trace_store,
        debug_mode=debug_mode,
    )


class McpTraceToolTests(unittest.TestCase):

    def test_debug_tool_hidden_outside_debug_mode(self) -> None:
        ctx = _build_context(debug_mode=False,
                             trace_store=InMemoryRetrievalTraceStore())
        server = McpServer(context=ctx)
        self.assertNotIn("project.get_retrieval_trace", server.tool_names)
        self.assertEqual(server.debug_tools, ())

    def test_debug_tool_listed_in_debug_mode(self) -> None:
        ctx = _build_context(debug_mode=True,
                             trace_store=InMemoryRetrievalTraceStore())
        server = McpServer(context=ctx)
        self.assertIn("project.get_retrieval_trace", server.tool_names)
        self.assertEqual(server.debug_tools, DEBUG_TOOLS)

    def test_debug_tool_rejected_when_called_without_debug_mode(
        self,
    ) -> None:
        ctx = _build_context(debug_mode=False,
                             trace_store=InMemoryRetrievalTraceStore())
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.get_retrieval_trace",
            {"trace_id": "abc"},
        ))
        self.assertFalse(result["ok"])
        self.assertEqual(
            result["error"]["type"], "DebugModeRequiredError",
        )

    def test_debug_tool_rejected_when_trace_store_missing(self) -> None:
        ctx = _build_context(debug_mode=True, trace_store=None)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.get_retrieval_trace",
            {"trace_id": "abc"},
        ))
        self.assertFalse(result["ok"])
        self.assertIn("retrieval trace store is not configured",
                      result["error"]["message"])

    def test_debug_tool_returns_trace_not_found_error(self) -> None:
        store = InMemoryRetrievalTraceStore()
        ctx = _build_context(debug_mode=True, trace_store=store)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.get_retrieval_trace",
            {"trace_id": "missing"},
        ))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["type"], "TraceNotFoundError")

    def test_retrieve_context_stores_trace_when_debug_mode_on(self) -> None:
        trace = RetrievalTrace(
            query_features={"identifiers": ("ILO-5193",)},
            dense_candidates=("c1", "c2"),
            timings=(("rerank", 5),),
        )
        store = InMemoryRetrievalTraceStore()
        ctx = _build_context(debug_mode=True, trace=trace,
                             trace_store=store)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "Where is ILO-5193 implemented?",
             "contextBudget": 800, "include_trace": True},
        ))
        self.assertTrue(result["ok"])
        self.assertIsNotNone(result["retrieval_trace_id"])
        self.assertEqual(store.stats()["stored"], 1)

        # Fetching the stored trace by id returns the JSON-encoded
        # trace payload through the debug-only tool.
        fetched = _run(server.call_tool(
            "project.get_retrieval_trace",
            {"trace_id": result["retrieval_trace_id"]},
        ))
        self.assertTrue(fetched["ok"])
        self.assertEqual(fetched["trace_id"], result["retrieval_trace_id"])
        self.assertEqual(
            fetched["query_text"],
            "Where is ILO-5193 implemented?",
        )
        self.assertIn("dense_candidates", fetched["trace"])
        self.assertEqual(fetched["trace"]["dense_candidates"], ["c1", "c2"])

    def test_debug_tool_requires_trace_id_argument(self) -> None:
        store = InMemoryRetrievalTraceStore()
        ctx = _build_context(debug_mode=True, trace_store=store)
        server = McpServer(context=ctx)
        # Missing required argument MUST raise through the
        # dispatch error path; confirm it surfaces as an
        # :class:`McpServerError`-shaped error rather than a
        # crash.
        result = _run(server.call_tool(
            "project.get_retrieval_trace", {},
        ))
        self.assertFalse(result["ok"])
        self.assertIn("missing required argument", result["error"]["message"])

    def test_debug_mode_required_error_is_mcp_server_error(self) -> None:
        # The debug-only gate inherits the McpServerError
        # hierarchy so callers can catch the base class.
        self.assertTrue(
            issubclass(DebugModeRequiredError, McpServerError),
        )
        self.assertTrue(
            issubclass(TraceNotFoundError, McpServerError),
        )

    def test_trace_tool_replays_timings(self) -> None:
        # Regression for deepseek-verify MINOR-2: the
        # debug-only tool must replay ``RetrievalTrace.timings``
        # through the builder so the stage-by-stage latency
        # breakdown is observable.
        trace = RetrievalTrace(
            query_features={"identifiers": ("ILO-5193",)},
            dense_candidates=("c1",),
            timings=(
                ("candidate_generation", 7),
                ("rerank", 12),
            ),
        )
        store = InMemoryRetrievalTraceStore()
        ctx = _build_context(debug_mode=True, trace=trace,
                             trace_store=store)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "Where is ILO-5193 implemented?",
             "contextBudget": 800, "include_trace": True},
        ))
        fetched = _run(server.call_tool(
            "project.get_retrieval_trace",
            {"trace_id": result["retrieval_trace_id"]},
        ))
        self.assertTrue(fetched["ok"])
        timings = dict(
            (stage, ms)
            for stage, ms in fetched["trace"]["timings"]
        )
        self.assertEqual(timings.get("candidate_generation"), 7)
        self.assertEqual(timings.get("rerank"), 12)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()