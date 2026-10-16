"""MCP ``project.retrieve_context`` v0.8 output extensions tests.

Change Package I of the v0.8 refinement
(``improve-ingestion-retrieval-local-models``) extends the MCP
``project.retrieve_context`` tool output with the fields named
in plan §33:

* ``selection_state``
* ``source`` (the legacy four-way source taxonomy)
* ``provenance`` (citation references for the assembled hits)
* ``project_version`` (readiness snapshot + requested version)
* ``conflicts`` (conflicting chunk ids / source documents)
* ``support_relationships`` (graph / hierarchy / table / figure
  evidence counts)
* ``retrieval_trace_id`` (set when debug mode is on AND the
  multi-stage pipeline actually produced a trace)

The tests assert the output shape, the source taxonomy stays
``dense|sparse|exact|hybrid`` and the support summary never
leaks graph / hierarchy into the legacy source field.
"""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import MagicMock

from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
from pi_platform.core.orchestration.capability_discovery import (
    DefaultCapabilityDiscovery,
)
from pi_platform.core.retrieval.retrieval_trace import RetrievalTrace
from pi_platform.mcp.server import (
    DEFAULT_SERVER_IDENTITY,
    McpServer,
    SECTION_36_TOOLS,
    ToolContext,
)
from pi_platform.ports import HydrateReport, ReconcileReport, VersionIdentity
from pi_platform.ports.retrieval.context_assembler import (
    Citation,
    ContextBundle,
)


__all__ = ["McpRetrieveContextOutputTests"]


@dataclass(frozen=True)
class _FakeHit:
    chunkId: str
    source: str = "dense"
    snippet: str = "snippet"
    score: float = 0.5
    contentHash: str = ""
    metadata: object = None
    knowledgeState: object = None
    evidenceWeight: float = 1.0
    tokenEstimate: int = 8


@dataclass(frozen=True)
class _FakeMetadata:
    documentId: str = "doc-1"
    sourcePath: str = ""
    validFrom: str = ""
    validTo: str = ""
    gitCommit: str = ""


@dataclass(frozen=True)
class _FakeSupport:
    chunk_id: str
    evidence_kind: str = "graph"
    source_document_id: str = "doc-2"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _build_context(
    *, debug_mode: bool = False, include_trace: bool = False,
    hits: tuple = (),
    bundle: ContextBundle | None = None,
) -> ToolContext:
    boundary = HmacTrustedApprovalBoundary(key=b"test")
    discovery = DefaultCapabilityDiscovery()
    orchestrator = MagicMock()
    builder = MagicMock()
    builder.build.return_value = MagicMock(taskId="t-1", goal="g",
                                           budgetTokens=100, items=())
    ms = MagicMock()
    result = MagicMock(
        hits=hits, stageReports=(), budgetUsed=0,
        primary_count=2, reserve_count=1, protected_count=1,
        support_count=2, selection_result=MagicMock(
            primary=("c1", "c2"),
            reserve=("c3",),
            protected=("c4",),
            dropped_duplicate=(),
            traces=(MagicMock(protected_reason="engineering "
                              "identifier ILO-5193"),),
        ),
        trace=RetrievalTrace() if include_trace else None,
        conflicts=(hits[0],) if hits else (),
    )
    ms.retrieve.return_value = result
    hybrid = MagicMock()
    assembler = MagicMock()
    if bundle is None:
        bundle = ContextBundle(
            hits=hits,
            citations=(Citation(
                chunkId="c1", contentHash="h1",
                sourceReference="docs/spec.md",
                projectVersion=VersionIdentity(
                    gitHead="abc", workingTreeFingerprint="f",
                    knowledgeSchemaVersion="0.8.0",
                    embeddingModelVersion="unknown",
                    indexSchemaVersion="0.1.0",
                ),
                evidenceWeight=0.9,
            ),) if hits else (),
            conflictingHits=(hits[0],) if hits else (),
            support_hits=(_FakeSupport(chunk_id="s1",
                                      evidence_kind="graph",
                                      source_document_id="doc-2"),
                        _FakeSupport(chunk_id="s2",
                                     evidence_kind="hierarchy",
                                     source_document_id="doc-2"),),
            selection_summary={
                "primary": 2, "reserve": 1,
                "protected": 1, "support": 2,
            },
        )
    assembler.assemble.return_value = bundle
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
        trace_store=None,
        debug_mode=debug_mode,
    )


class McpRetrieveContextOutputTests(unittest.TestCase):

    def test_section_36_tools_still_registered(self) -> None:
        # Regression: the v0.8 extension MUST NOT shadow any §36
        # name even when the new tool is registered.
        ctx = _build_context()
        server = McpServer(context=ctx)
        for name in SECTION_36_TOOLS:
            self.assertIn(name, server.tool_names)

    def test_retrieve_context_returns_v0_8_fields(self) -> None:
        hits = (_FakeHit(chunkId="c1", source="dense",
                         metadata=_FakeMetadata()),)
        ctx = _build_context(hits=hits)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "top_k": 5, "contextBudget": 800},
        ))
        self.assertTrue(result["ok"])
        for key in (
            "selection_state", "source", "provenance",
            "project_version", "conflicts",
            "support_relationships", "retrieval_trace_id",
        ):
            self.assertIn(key, result)

    def test_selection_state_summary_counts(self) -> None:
        hits = (_FakeHit(chunkId="c1", source="dense",
                         metadata=_FakeMetadata()),)
        ctx = _build_context(hits=hits)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800},
        ))
        selection = result["selection_state"]
        self.assertEqual(selection["primary"], 2)
        self.assertEqual(selection["reserve"], 1)
        self.assertEqual(selection["protected"], 1)
        self.assertEqual(selection["support"], 2)
        self.assertEqual(
            selection["protected_reasons"],
            ["engineering identifier ILO-5193"],
        )
        self.assertEqual(
            selection["bundle"],
            {"primary": 2, "reserve": 1, "protected": 1, "support": 2},
        )

    def test_source_summary_uses_legacy_taxonomy(self) -> None:
        # The four-way taxonomy MUST NOT grow a ``graph`` /
        # ``hierarchy`` value even when support items are
        # attached (Package A3 invariant).
        hits = (
            _FakeHit(chunkId="c1", source="dense",
                     metadata=_FakeMetadata()),
            _FakeHit(chunkId="c2", source="sparse",
                     metadata=_FakeMetadata()),
            _FakeHit(chunkId="c3", source="exact",
                     metadata=_FakeMetadata()),
        )
        ctx = _build_context(hits=hits)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800},
        ))
        self.assertEqual(
            set(result["source"]),
            {"dense", "sparse", "exact"},
        )

    def test_provenance_lists_citations(self) -> None:
        hits = (_FakeHit(chunkId="c1", source="dense",
                         metadata=_FakeMetadata()),)
        ctx = _build_context(hits=hits)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800},
        ))
        provenance = result["provenance"]
        self.assertEqual(len(provenance), 1)
        self.assertEqual(provenance[0]["chunkId"], "c1")
        self.assertEqual(provenance[0]["sourceReference"], "docs/spec.md")

    def test_project_version_summary_includes_snapshot(self) -> None:
        hits = (_FakeHit(chunkId="c1", source="dense",
                         metadata=_FakeMetadata()),)
        ctx = _build_context(hits=hits)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800,
             "project_version": {"gitHead": "abc"}},
        ))
        pv = result["project_version"]
        self.assertEqual(pv["current_head"], "abc")
        self.assertTrue(pv["consistent"])
        self.assertEqual(pv["requested"], {"gitHead": "abc"})

    def test_conflict_summary_lists_chunk_ids(self) -> None:
        hits = (_FakeHit(chunkId="c1", source="dense",
                         metadata=_FakeMetadata(documentId="doc-1")),)
        ctx = _build_context(hits=hits)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800},
        ))
        conflicts = result["conflicts"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["chunkId"], "c1")
        self.assertEqual(conflicts[0]["sourceDocumentId"], "doc-1")

    def test_support_relationships_summary(self) -> None:
        hits = (_FakeHit(chunkId="c1", source="dense",
                         metadata=_FakeMetadata()),)
        ctx = _build_context(hits=hits)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800},
        ))
        support = result["support_relationships"]
        self.assertEqual(support["counts"], {"graph": 1, "hierarchy": 1})
        self.assertEqual(support["chunkIds"], ["s1", "s2"])
        self.assertEqual(support["sourceDocumentIds"], ["doc-2"])
        self.assertEqual(support["total"], 2)

    def test_retrieve_context_without_debug_mode_omits_trace(self) -> None:
        hits = (_FakeHit(chunkId="c1", source="dense",
                         metadata=_FakeMetadata()),)
        ctx = _build_context(hits=hits, debug_mode=False,
                             include_trace=True)
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800,
             "include_trace": True},
        ))
        self.assertTrue(result["ok"])
        # ``include_trace=True`` is silently ignored outside debug
        # mode so the production surface stays narrow.
        self.assertIsNone(result["retrieval_trace_id"])

    def test_retrieve_context_empty_hits_yields_empty_fields(self) -> None:
        ctx = _build_context(hits=())
        server = McpServer(context=ctx)
        result = _run(server.call_tool(
            "project.retrieve_context",
            {"text": "OrderStatus", "contextBudget": 800},
        ))
        self.assertTrue(result["ok"])
        self.assertEqual(result["source"], [])
        self.assertEqual(result["provenance"], [])
        self.assertEqual(result["conflicts"], [])
        self.assertEqual(result["support_relationships"]["total"], 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()