"""Phase 6 prerequisite 2 / 3 / 4 / 5 focused tests.

* Prerequisite 2 — filter / scope preservation through orchestration.
  ``QueryOrchestrator.orchestrate`` accepts a typed
  ``MetadataFilter`` and a ``ProjectVersion``; filtered L0 is
  preserved through the typed ``RetrievalQuery``; filtered L1 / L2
  are rejected explicitly with
  :class:`FilteredEscalationNotSupportedError`.

* Prerequisite 3 — hydrate / reconcile before serving. The MCP
  server (and any tool serving project knowledge) must consult
  :class:`KnowledgeReadinessPort`; an inconsistent state raises
  :class:`RuntimeNotReadyError`. No cross-version evidence may be
  served.

* Prerequisite 4 — no fabricated evidence. Graph / exact-lookup
  helpers must refuse to return records without a verified
  :class:`Evidence`; missing evidence is described as missing, not
  invented.

* Prerequisite 5 — version-source honesty. The capability
  descriptor reports each of the 9 dimensions as the actual
  offered metadata (or unavailable), never invented.
"""

from __future__ import annotations

import unittest
from typing import Mapping, Sequence

from pi_platform.core.canonical.value_types import (
    Evidence, KnowledgeState, ProjectVersion,
)
from pi_platform.core.orchestration.query_orchestrator import (
    DefaultQueryOrchestrator,
)
from pi_platform.core.sync.readiness import (
    DefaultKnowledgeReadiness,
    assert_ready,
)
from pi_platform.ports import (
    HydrateReport,
    ReadinessSnapshot,
    ReconcileReport,
    RuntimeNotReadyError,
    VersionIdentity,
)
from pi_platform.ports.orchestration.query_orchestrator import (
    FilteredEscalationNotSupportedError,
    OrchestrationLevel,
)
from pi_platform.ports.orchestration.capability_discovery import (
    DimensionValue, VersionDimensions,
)
from pi_platform.ports.retrieval.context_assembler import ContextBundle
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.metadata_filter import MetadataFilter
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    RetrievalQuery, RetrievalResult, StageReport,
)


__all__ = [
    "FilterPreservationTests",
    "ReadinessGateTests",
    "VersionDimensionHonestyTests",
]


def _hit(chunk_id: str = "c-1", *, snippet: str = "evidence"):
    from pi_platform.core.canonical.value_types import (
        KnowledgeState, Metadata,
    )
    md = Metadata(
        documentId=chunk_id, version="0.0.0", language="en",
        sourcePath=f"docs/{chunk_id}.md",
    )
    return RetrievalHit(
        chunkId=chunk_id, score=0.5, source="dense", snippet=snippet,
        contentHash=chunk_id, metadata=md,
        knowledgeState=KnowledgeState.VERIFIED, tokenEstimate=16,
    )


class _RecordingRetrieval:
    def __init__(self, hits: Sequence[RetrievalHit] = ()):
        self._hits = list(hits)
        self.calls: list[RetrievalQuery] = []

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        self.calls.append(query)
        return RetrievalResult(
            hits=tuple(self._hits),
            stageReports=(
                StageReport(stage="candidate_generation",
                            candidatesIn=len(self._hits),
                            candidatesOut=len(self._hits)),
            ),
            budgetUsed=sum(h.tokenEstimate for h in self._hits),
        )

    def stats(self) -> Mapping[str, int]:
        return {"calls": len(self.calls)}


class _StubLLM:
    def is_available(self) -> bool:
        return True

    def complete(self, prompt, *, max_tokens=256, temperature=0.0):
        return "stub"

    def model_version(self) -> str:
        return "stub-1"

    def license_id(self) -> str:
        return "Apache-2.0"

    def family(self) -> str:
        return "stub"

    def stats(self) -> Mapping[str, int]:
        return {}


class _StubBuilder:
    def build(self, *, goal: str, budget_tokens: int,
              retrieval: object):
        return ContextBundle(
            taskId="t-1", goal=goal,
            budgetTokens=budget_tokens, items=(),
        )


class FilterPreservationTests(unittest.TestCase):
    """Phase 6 prerequisite 2 — filter / scope preservation."""

    def _orch(self) -> DefaultQueryOrchestrator:
        return DefaultQueryOrchestrator(
            retrieval=_RecordingRetrieval(hits=[_hit()]),
            local_llm=_StubLLM(),
            task_context_builder=_StubBuilder(),
        )

    def test_l0_passes_filters_through_to_retrieval_query(self):
        orch = self._orch()
        retrieval = orch._retrieval
        filt = MetadataFilter(languages=("en",))
        result = orch.orchestrate(
            "Find OrderStatus.", level=0,
            filters=filt,
            project_version=ProjectVersion(gitHead="abc", workingTreeFingerprint="f", knowledgeSchemaVersion="0.7.0", embeddingModelVersion="x", indexSchemaVersion="0.1.0"),
        )
        self.assertEqual(int(result.level), 0)
        # The typed RetrievalQuery was passed verbatim to the
        # retrieval port: filters AND project_version preserved.
        self.assertEqual(len(retrieval.calls), 1)
        sent = retrieval.calls[0]
        self.assertIs(sent.filters, filt)
        self.assertEqual(sent.projectVersion.gitHead, "abc")

    def test_l1_rejects_filtered_query_explicitly(self):
        orch = self._orch()
        filt = MetadataFilter(languages=("en",))
        with self.assertRaises(FilteredEscalationNotSupportedError) as cm:
            orch.orchestrate(
                "Explain X.", level=1, filters=filt,
                project_version=ProjectVersion(gitHead="abc", workingTreeFingerprint="f", knowledgeSchemaVersion="0.7.0", embeddingModelVersion="x", indexSchemaVersion="0.1.0"),
            )
        self.assertEqual(cm.exception.level, 1)
        self.assertIsNotNone(cm.exception.filters)
        self.assertIsNotNone(cm.exception.project_version)

    def test_l2_rejects_filtered_query_explicitly(self):
        orch = self._orch()
        filt = MetadataFilter(modules=("psb",))
        with self.assertRaises(FilteredEscalationNotSupportedError) as cm:
            orch.orchestrate(
                "Implement REQ-471.", level=2,
                filters=filt,
                project_version=ProjectVersion(gitHead="abc", workingTreeFingerprint="f", knowledgeSchemaVersion="0.7.0", embeddingModelVersion="x", indexSchemaVersion="0.1.0"),
            )
        self.assertEqual(cm.exception.level, 2)

    def test_unfiltered_l1_still_routes_normally(self):
        # The error fires only when filters are PRESENT and level
        # is L1 / L2; no-filter L1 must run through the LLM as
        # before to preserve Phase 5 retrieval-first compliance.
        orch = self._orch()
        result = orch.orchestrate(
            "Explain X.", level=1, filters=None,
        )
        self.assertEqual(int(result.level), 1)
        self.assertIsNotNone(result.llm_completion)

    def test_filtered_l1_error_carries_envelope(self):
        orch = self._orch()
        pv = ProjectVersion(gitHead="abc", workingTreeFingerprint="f", knowledgeSchemaVersion="0.7.0", embeddingModelVersion="x", indexSchemaVersion="0.1.0")
        filt = MetadataFilter(requirementIds=("ssr-spec",))
        try:
            orch.orchestrate(
                "Explain X.", level=1, filters=filt, project_version=pv,
            )
            self.fail("FilteredEscalationNotSupportedError not raised")
        except FilteredEscalationNotSupportedError as exc:
            self.assertEqual(int(exc.level), 1)
            self.assertIs(exc.filters, filt)
            self.assertEqual(
                exc.project_version.gitHead, "abc",
            )


class ReadinessGateTests(unittest.TestCase):
    """Phase 6 prerequisite 3 — hydrate / reconcile before serving."""

    def test_default_gate_is_not_ready(self):
        gate = DefaultKnowledgeReadiness()
        self.assertFalse(gate.is_ready())
        self.assertFalse(gate.snapshot().consistent)

    def test_hydrate_only_is_not_ready(self):
        gate = DefaultKnowledgeReadiness()
        gate.record_hydrate(HydrateReport(
            project_version=VersionIdentity(
                gitHead="abc", workingTreeFingerprint="f",
                knowledgeSchemaVersion="0.7.0",
                embeddingModelVersion="x",
                indexSchemaVersion="0.1.0",
            ),
            families={"chunks": 3},
            cache_hit_rates={"chunks": 1.0},
        ))
        self.assertFalse(gate.is_ready())

    def test_hydrate_plus_reconcile_is_ready(self):
        gate = DefaultKnowledgeReadiness()
        gate.record_hydrate(HydrateReport(
            project_version=VersionIdentity(
                gitHead="abc", workingTreeFingerprint="f",
                knowledgeSchemaVersion="0.7.0",
                embeddingModelVersion="x",
                indexSchemaVersion="0.1.0",
            ),
            families={"chunks": 3},
            cache_hit_rates={"chunks": 1.0},
        ))
        gate.record_reconcile(ReconcileReport(
            families={"chunks": 3},
            reused_shards={"chunks": 3},
            re_ingested_shards={"chunks": 0},
        ), current_head="abc", working_tree_fingerprint="f")
        self.assertTrue(gate.is_ready())

    def test_in_progress_refresh_makes_gate_not_ready(self):
        gate = DefaultKnowledgeReadiness()
        gate.record_hydrate(HydrateReport(
            project_version=VersionIdentity(
                gitHead="abc", workingTreeFingerprint="f",
                knowledgeSchemaVersion="0.7.0",
                embeddingModelVersion="x",
                indexSchemaVersion="0.1.0",
            ),
            families={}, cache_hit_rates={},
        ))
        gate.record_reconcile(ReconcileReport(
            families={}, reused_shards={}, re_ingested_shards={},
        ), current_head="abc", working_tree_fingerprint="f")
        self.assertTrue(gate.is_ready())
        gate.begin_refresh()
        self.assertFalse(gate.is_ready())
        snap = gate.snapshot()
        self.assertTrue(snap.in_progress)
        gate.end_refresh()
        self.assertTrue(gate.is_ready())

    def test_failure_marks_gate_not_ready(self):
        gate = DefaultKnowledgeReadiness()
        gate.record_hydrate(HydrateReport(
            project_version=VersionIdentity(
                gitHead="abc", workingTreeFingerprint="f",
                knowledgeSchemaVersion="0.7.0",
                embeddingModelVersion="x",
                indexSchemaVersion="0.1.0",
            ),
            families={}, cache_hit_rates={},
        ))
        gate.record_reconcile(ReconcileReport(
            families={}, reused_shards={}, re_ingested_shards={},
        ), current_head="abc", working_tree_fingerprint="f")
        gate.record_failure("branch switch could not reconcile")
        self.assertFalse(gate.is_ready())
        self.assertIn("branch switch", gate.snapshot().reason)

    def test_assert_ready_raises_runtime_not_ready_when_not_consistent(self):
        gate = DefaultKnowledgeReadiness()
        with self.assertRaises(RuntimeNotReadyError) as cm:
            assert_ready(gate)
        self.assertFalse(cm.exception.snapshot.consistent)

    def test_assert_ready_returns_snapshot_when_ready(self):
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
        snap = assert_ready(gate)
        self.assertTrue(snap.consistent)


class VersionDimensionHonestyTests(unittest.TestCase):
    """Phase 6 prerequisite 5 — version-source / dimension honesty."""

    def test_capability_discovery_reports_actual_dimensions(self):
        from pi_platform.adapters.orchestration.capability_discovery import (
            DefaultCapabilityDiscoveryAdapter,
        )
        adapter = DefaultCapabilityDiscoveryAdapter(
            server_version="0.8.0",
            mcp_api_version="1.3.0",
            knowledge_schema_version="0.7.0",
            okf_versions=("0.2",),
        )
        descriptor = adapter.describe()
        self.assertIsNotNone(descriptor.dimensions)
        dims = descriptor.dimensions
        self.assertEqual(dims.platformVersion.value, "0.8.0")
        self.assertTrue(dims.platformVersion.available)
        self.assertEqual(dims.mcpApiVersion.value, "1.3.0")
        self.assertTrue(dims.mcpApiVersion.available)
        self.assertEqual(dims.knowledgeSchemaVersion.value, "0.7.0")
        self.assertEqual(dims.okfProfileVersion.value, "0.2")
        self.assertEqual(dims.a2aAdapterVersion.value, None)
        self.assertFalse(dims.a2aAdapterVersion.available)
        self.assertEqual(dims.agentAdapterVersion.value, None)
        self.assertFalse(dims.agentAdapterVersion.available)

    def test_unavailable_dimensions_are_reported_not_fabricated(self):
        from pi_platform.adapters.orchestration.capability_discovery import (
            DefaultCapabilityDiscoveryAdapter,
        )
        descriptor = DefaultCapabilityDiscoveryAdapter().describe()
        unavailable = descriptor.dimensions.unavailable_names
        self.assertIn("a2aAdapterVersion", unavailable)
        self.assertIn("agentAdapterVersion", unavailable)
        # Crucially: a2aAdapterVersion.value is None, NOT "0.1.0"
        # or any architecture example number.
        self.assertIsNone(descriptor.dimensions.a2aAdapterVersion.value)

    def test_all_9_dimensions_present_in_descriptor(self):
        from pi_platform.adapters.orchestration.capability_discovery import (
            DefaultCapabilityDiscoveryAdapter,
        )
        descriptor = DefaultCapabilityDiscoveryAdapter().describe()
        self.assertIsNotNone(descriptor.dimensions)
        for dim_name in (
            "platformVersion", "mcpApiVersion", "a2aAdapterVersion",
            "knowledgeSchemaVersion", "okfProfileVersion", "skillVersion",
            "pluginDistributionSchemaVersion", "agentAdapterVersion",
            "runtimeIndexSchemaVersion",
        ):
            self.assertTrue(
                hasattr(descriptor.dimensions, dim_name),
                msg=f"missing dimension {dim_name}",
            )

    def test_dimension_serialization_round_trip_is_deterministic(self):
        from pi_platform.adapters.orchestration.capability_discovery import (
            DefaultCapabilityDiscoveryAdapter,
        )
        import json
        adapter = DefaultCapabilityDiscoveryAdapter()
        first = json.dumps(adapter.describe().as_dict(), sort_keys=True)
        second = json.dumps(adapter.describe().as_dict(), sort_keys=True)
        self.assertEqual(first, second)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()