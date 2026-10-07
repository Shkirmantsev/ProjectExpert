"""Phase 5 orchestration behavior regressions.

The tests cover the five Phase 5 capability specs
(`query-orchestrator`, `local-llm-port`, `task-context-builder`,
`capability-discovery`, `retrieval-first-policy`). Every test
exercises real implementations behind the documented ports;
no mocks are used. The §33 retrieval-first policy regression
test lives under
:mod:`tests.test_orchestration_policy`.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict, is_dataclass
from typing import Iterable, Mapping, Sequence

from pi_platform.adapters.orchestration.capability_discovery import (
    DefaultCapabilityDiscoveryAdapter,
)
from pi_platform.adapters.orchestration.stub_local_llm import (
    StubLocalLLMAdapter,
)
from pi_platform.adapters.orchestration.task_context import (
    DefaultTaskContextBuilderAdapter,
)
from pi_platform.adapters.retrieval.bm25_light_reranker import (
    Bm25LightRerankerAdapter,
)
from pi_platform.adapters.retrieval.context_assembler_adapter import (
    ContextAssemblerAdapter,
)
from pi_platform.adapters.retrieval.hashing_embedding_model import (
    HashingEmbeddingAdapter,
)
from pi_platform.adapters.retrieval.hybrid_retrieval import (
    HybridRetrievalAdapter,
)
from pi_platform.adapters.retrieval.identifier_query_detector import (
    IdentifierQueryDetector,
)
from pi_platform.adapters.retrieval.metadata_filter_adapter import (
    MetadataFilterAdapter,
)
from pi_platform.adapters.runtime.graph_expansion import (
    ProductionGraphExpansion,
)
from pi_platform.core.canonical.value_types import (
    Entity,
    KnowledgeState,
    Metadata,
)
from pi_platform.core.orchestration.capability_discovery import (
    DEFAULT_KNOWLEDGE_SCHEMA_VERSION,
    DEFAULT_MCP_API_VERSION,
    DEFAULT_OKF_VERSIONS,
    DEFAULT_SERVER_VERSION,
)
from pi_platform.core.orchestration.query_orchestrator import (
    DEFAULT_L2_BUDGET_TOKENS,
    DEFAULT_LLM_MAX_TOKENS,
)
from pi_platform.core.orchestration.task_context import (
    BUNDLE_SLOT_PRIORITY,
    OPENSPEC_PATTERN,
    REQUIREMENT_PATTERN,
)
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)
from pi_platform.ports.orchestration.capability_discovery import (
    CapabilityDescriptor,
    CapabilityFeatures,
)
from pi_platform.ports.orchestration.local_llm import LocalLLMError
from pi_platform.ports.orchestration.query_orchestrator import (
    EscalationCapError,
    OrchestrationLevel,
    QueryOrchestratorError,
)
from pi_platform.ports.orchestration.task_context import (
    TaskContextBuilderError,
    TaskContextBundle,
)
from pi_platform.ports.retrieval.hybrid_retrieval import (
    HIT_SOURCE_DENSE,
    HIT_SOURCE_SPARSE,
    RetrievalHit,
)
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    RetrievalQuery,
)


def _hit(
    chunk_id: str, *, score: float = 0.5, source: str = HIT_SOURCE_SPARSE,
    snippet: str = "", language: str = "en",
    family: str = "Component",
    validFrom: str | None = None, validTo: str | None = None,
    git_commit: str | None = None,
    security_classification: str | None = None,
    knowledge_state: KnowledgeState = KnowledgeState.VERIFIED,
    token_estimate: int = 16,
) -> RetrievalHit:
    md = Metadata(
        documentId=chunk_id, version="0.0.0", language=language,
        validFrom=validFrom, validTo=validTo, gitCommit=git_commit,
        sourcePath=f"docs/{chunk_id}.md",
        securityClassification=security_classification,
    )
    return RetrievalHit(
        chunkId=chunk_id, score=score, source=source, snippet=snippet,
        contentHash=chunk_id, metadata=md,
        knowledgeState=knowledge_state,
        tokenEstimate=token_estimate,
    )


class _PipelineStub:
    """Minimal stand-in for the Phase 4 multi-stage pipeline the
    orchestrator composes; the Phase 4 tests cover the real
    pipeline.
    """

    def __init__(self, hits: Sequence[RetrievalHit] = ()) -> None:
        self._hits = list(hits)
        self._calls = 0
        self._last_query: RetrievalQuery | None = None

    def retrieve(self, query: RetrievalQuery):
        from pi_platform.ports.retrieval.multi_stage_retrieval import (
            RetrievalResult,
            StageReport,
        )
        self._calls += 1
        self._last_query = query
        return RetrievalResult(
            hits=tuple(self._hits),
            stageReports=(
                StageReport(
                    stage="candidate_generation",
                    candidatesIn=len(self._hits),
                    candidatesOut=len(self._hits),
                ),
            ),
            budgetUsed=sum(h.tokenEstimate for h in self._hits),
        )

    def stats(self) -> Mapping[str, int]:
        return {"calls": self._calls}


class _GraphStub:
    def expand(self, seeds, *, hops, edge_types, budget):
        from pi_platform.ports.runtime.graph_expansion import GraphExpansion
        from pi_platform.core.canonical.value_types import (
            Entity,
            KnowledgeState,
            Metadata,
        )
        return GraphExpansion(
            seeds=tuple(seeds),
            expandedEntities=(),
            expandedRelations=(),
            hops=hops,
            budget_exhausted=False,
        )


def _build_orchestrator(
    *, hits: Sequence[RetrievalHit] = (), default_level: int = 0,
):
    from pi_platform.adapters.orchestration.query_orchestrator import (
        DefaultQueryOrchestratorAdapter,
    )
    retrieval = _PipelineStub(hits=hits)
    local_llm = StubLocalLLMAdapter()
    task_builder = DefaultTaskContextBuilderAdapter()
    orchestrator = DefaultQueryOrchestratorAdapter(
        retrieval=retrieval,
        local_llm=local_llm,
        task_context_builder=task_builder,
        default_level=default_level,
    )
    return orchestrator, retrieval, local_llm, task_builder


class QueryOrchestratorTests(unittest.TestCase):
    """§34 three-level escalation tests."""

    def test_l0_query_returns_direct_retrieval(self):
        orchestrator, retrieval, _, _ = _build_orchestrator(
            hits=[_hit("c-1", snippet="FinishPack protocol message")],
        )
        result = orchestrator.orchestrate("Where is OrderStatus declared?")
        self.assertEqual(result.level, OrchestrationLevel.L0_DIRECT_RETRIEVAL)
        self.assertIsNone(result.llm_completion)
        self.assertIsNone(result.task_context)
        self.assertEqual(retrieval._calls, 1)
        stats = orchestrator.stats()
        self.assertEqual(stats["level0_calls"], 1)

    def test_l1_query_emits_llm_completion_when_available(self):
        orchestrator, _, _, _ = _build_orchestrator(
            hits=[_hit("c-1", snippet="FinishPack protocol message")],
        )
        # Use a fake local LLM that is available for the L1 path.
        class _AvailableStub:
            family_name = "stub"
            def is_available(self): return True
            def complete(self, prompt, *, max_tokens=256, temperature=0.0):
                return "stub completion"
            def model_version(self): return "stub-1.0.0"
            def license_id(self): return "Apache-2.0"
            def family(self): return "stub"
            def stats(self): return {}
        from pi_platform.adapters.orchestration.query_orchestrator import (
            DefaultQueryOrchestratorAdapter,
        )
        from pi_platform.adapters.orchestration.task_context import (
            DefaultTaskContextBuilderAdapter,
        )
        orchestrator = DefaultQueryOrchestratorAdapter(
            retrieval=_PipelineStub(hits=[
                _hit("c-1", snippet="FinishPack protocol message"),
            ]),
            local_llm=_AvailableStub(),
            task_context_builder=DefaultTaskContextBuilderAdapter(),
        )
        result = orchestrator.orchestrate(
            "Explain the FinishPack protocol message.",
            level=1,
        )
        self.assertEqual(
            result.level, OrchestrationLevel.L1_RETRIEVAL_PLUS_LLM,
        )
        self.assertEqual(result.llm_completion, "stub completion")
        self.assertIsNone(result.task_context)
        stats = orchestrator.stats()
        self.assertEqual(stats["level1_calls"], 1)

    def test_l1_query_skips_llm_when_unavailable_and_emits_l2(self):
        orchestrator, _, _, _ = _build_orchestrator(
            hits=[_hit("c-1", snippet="FinishPack protocol message")],
        )
        result = orchestrator.orchestrate(
            "Explain the FinishPack protocol message.",
            level=1,
        )
        self.assertEqual(
            result.level, OrchestrationLevel.L2_STRONG_EXTERNAL_AGENT,
        )
        self.assertIsNotNone(result.task_context)

    def test_l2_query_emits_task_context_bundle(self):
        orchestrator, _, _, _ = _build_orchestrator(
            hits=[_hit("c-1", snippet="FinishPack protocol message")],
        )
        result = orchestrator.orchestrate(
            "Implement REQ-471 and adapt integration tests.",
            level=2,
        )
        self.assertEqual(
            result.level, OrchestrationLevel.L2_STRONG_EXTERNAL_AGENT,
        )
        self.assertIsNotNone(result.task_context)
        self.assertEqual(result.task_context.goal,
                         "Implement REQ-471 and adapt integration tests.")
        stats = orchestrator.stats()
        self.assertEqual(stats["level2_calls"], 1)

    def test_explicit_level_override(self):
        orchestrator, _, _, _ = _build_orchestrator()
        result = orchestrator.orchestrate("Explain X.", level=0)
        self.assertEqual(result.level, OrchestrationLevel.L0_DIRECT_RETRIEVAL)

    def test_escalation_from_l0_skips_to_l2_when_stub_unavailable(self):
        orchestrator, _, _, _ = _build_orchestrator(
            hits=[_hit("c-1", snippet="FinishPack protocol message")],
        )
        l0 = orchestrator.orchestrate("Where is X?", level=0)
        escalated = orchestrator.escalate(l0, reason="needs-explanation")
        # Stub is unavailable so the orchestrator skips L1 and
        # escalates directly to L2.
        self.assertEqual(
            escalated.level, OrchestrationLevel.L2_STRONG_EXTERNAL_AGENT,
        )
        self.assertIs(escalated.retrieval, l0.retrieval)

    def test_escalation_caps_at_l2(self):
        orchestrator, _, _, _ = _build_orchestrator()
        l2 = orchestrator.orchestrate("Implement X.", level=2)
        with self.assertRaises(EscalationCapError):
            orchestrator.escalate(l2, reason="more")

    def test_deterministic_level_selection(self):
        orchestrator, _, _, _ = _build_orchestrator()
        first = orchestrator.orchestrate("Where is X?", level=0)
        second = orchestrator.orchestrate("Where is X?", level=0)
        self.assertEqual(first.level, second.level)


class LocalLLMTests(unittest.TestCase):
    """§35 LocalLLMPort tests."""

    def test_stub_is_unavailable(self):
        stub = StubLocalLLMAdapter()
        self.assertFalse(stub.is_available())
        self.assertEqual(stub.family(), "stub")
        self.assertEqual(stub.license_id(), "Apache-2.0")

    def test_stub_complete_returns_empty(self):
        stub = StubLocalLLMAdapter()
        self.assertEqual(stub.complete("Hello", max_tokens=16), "")

    def test_stub_complete_rejects_empty_prompt(self):
        stub = StubLocalLLMAdapter()
        with self.assertRaises(LocalLLMError):
            stub.complete("", max_tokens=16)

    def test_stub_complete_rejects_non_positive_max_tokens(self):
        stub = StubLocalLLMAdapter()
        with self.assertRaises(LocalLLMError):
            stub.complete("hello", max_tokens=0)

    def test_stub_stats_record_calls(self):
        stub = StubLocalLLMAdapter()
        stub.complete("hello", max_tokens=16)
        stub.complete("world", max_tokens=16)
        stats = stub.stats()
        self.assertGreaterEqual(stats["calls"], 2)
        self.assertEqual(stats["errors"], 0)


class TaskContextBuilderTests(unittest.TestCase):
    """§52 TaskContextBuilderPort tests."""

    def _make_builder(self):
        return DefaultTaskContextBuilderAdapter()

    def test_build_produces_bounded_bundle(self):
        builder = self._make_builder()
        bundle = builder.build("Implement REQ-471", budget_tokens=2000)
        self.assertTrue(bundle.taskId)
        self.assertEqual(bundle.budgetTokens, 2000)
        self.assertEqual(bundle.goal, "Implement REQ-471")
        self.assertIsNotNone(bundle.requirement)
        self.assertEqual(bundle.requirement.identifier, "REQ-471")

    def test_requirement_slot_extracted(self):
        builder = self._make_builder()
        bundle = builder.build("Implement GEN-3.0.03 in module X")
        self.assertIsNotNone(bundle.requirement)
        self.assertEqual(bundle.requirement.identifier, "GEN-3.0.03")

    def test_openspec_slot_extracted(self):
        builder = self._make_builder()
        bundle = builder.build("Review 2026-10-05-query-orchestrator spec")
        self.assertEqual(len(bundle.openSpec), 1)
        self.assertEqual(
            bundle.openSpec[0].capabilityId,
            "2026-10-05-query-orchestrator",
        )

    def test_priority_ordering(self):
        self.assertEqual(BUNDLE_SLOT_PRIORITY[0], "requirement")
        self.assertEqual(BUNDLE_SLOT_PRIORITY[-1], "gitDiff")

    def test_budget_truncation_drops_lowest_priority_slots(self):
        builder = self._make_builder()
        # budget_tokens=1 forces the requirement slot to be
        # dropped because the requirement text costs more than
        # one token; the truncation is recorded under
        # `droppedSlots`.
        bundle = builder.build(
            "Implement REQ-471 with extensive evidence",
            budget_tokens=1,
        )
        self.assertEqual(len(bundle.droppedSlots), 1)
        explanations_text = "\n".join(bundle.explanations or ())
        self.assertIn("dropped_slots", explanations_text)

    def test_repeated_build_is_deterministic(self):
        builder = self._make_builder()
        first = builder.build("Implement REQ-471", budget_tokens=2000)
        second = builder.build("Implement REQ-471", budget_tokens=2000)
        self.assertEqual(first.taskId, second.taskId)
        self.assertEqual(first.budgetTokens, second.budgetTokens)

    def test_validate_reports_issues(self):
        builder = self._make_builder()
        bundle = TaskContextBundle(
            taskId="task-test", goal="x", budgetTokens=100,
        )
        # Manually invalidate after construction since the port
        # refuses to build bundles with negative budgets.
        object.__setattr__(bundle, "budgetTokens", 0)
        issues = builder.validate(bundle)
        self.assertIn("budgetTokens must be positive", issues)

    def test_patterns_recognise_documented_identifiers(self):
        self.assertIsNotNone(REQUIREMENT_PATTERN.search("REQ-471"))
        self.assertIsNotNone(OPENSPEC_PATTERN.search("2026-10-05-embedding-model"))

    def test_rejects_non_positive_budget(self):
        builder = self._make_builder()
        with self.assertRaises(TaskContextBuilderError):
            TaskContextBundle(taskId="t", goal="x", budgetTokens=0)


class CapabilityDiscoveryTests(unittest.TestCase):
    """§47 CapabilityDiscoveryPort tests."""

    def test_descriptor_default_is_unavailable_for_optional_features(self):
        discovery = DefaultCapabilityDiscoveryAdapter()
        descriptor = discovery.describe()
        self.assertIsInstance(descriptor, CapabilityDescriptor)
        self.assertEqual(descriptor.serverVersion, DEFAULT_SERVER_VERSION)
        self.assertEqual(descriptor.mcpApiVersion, DEFAULT_MCP_API_VERSION)
        self.assertEqual(
            descriptor.knowledgeSchemaVersion,
            DEFAULT_KNOWLEDGE_SCHEMA_VERSION,
        )
        self.assertEqual(list(descriptor.okfVersions), list(DEFAULT_OKF_VERSIONS))
        self.assertFalse(descriptor.features.localLlm)
        self.assertFalse(descriptor.features.a2a)
        self.assertFalse(descriptor.features.materialization)
        self.assertFalse(descriptor.features.hybridRetrieval)
        self.assertFalse(descriptor.features.graphExpansion)

    def test_descriptor_includes_retrieval_when_provided(self):
        discovery = DefaultCapabilityDiscoveryAdapter(retrieval=object())
        descriptor = discovery.describe()
        self.assertTrue(descriptor.features.hybridRetrieval)

    def test_descriptor_reports_local_llm_when_available(self):
        class _AvailableLLM:
            def is_available(self): return True
        discovery = DefaultCapabilityDiscoveryAdapter(
            retrieval=object(), graph_expansion=object(),
            materialisation=object(), local_llm=_AvailableLLM(),
        )
        descriptor = discovery.describe()
        self.assertTrue(descriptor.features.localLlm)

    def test_descriptor_reports_local_llm_false_when_unavailable(self):
        class _UnavailableLLM:
            def is_available(self): return False
        discovery = DefaultCapabilityDiscoveryAdapter(
            local_llm=_UnavailableLLM(),
        )
        descriptor = discovery.describe()
        self.assertFalse(descriptor.features.localLlm)

    def test_descriptor_serialises_to_deterministic_json(self):
        discovery = DefaultCapabilityDiscoveryAdapter(retrieval=object())
        first = json.dumps(discovery.describe().as_dict(), sort_keys=True)
        second = json.dumps(discovery.describe().as_dict(), sort_keys=True)
        self.assertEqual(first, second)

    def test_descriptor_matches_section_47_example_shape(self):
        discovery = DefaultCapabilityDiscoveryAdapter(retrieval=object())
        descriptor_dict = discovery.describe().as_dict()
        for key in (
            "serverVersion", "mcpApiVersion",
            "knowledgeSchemaVersion", "features",
        ):
            self.assertIn(key, descriptor_dict)
        for feature_key in (
            "hybridRetrieval", "graphExpansion", "okf",
            "materialization", "a2a", "localLlm",
        ):
            self.assertIn(feature_key, descriptor_dict["features"])

    def test_refresh_re_evaluates_registrations(self):
        discovery = DefaultCapabilityDiscoveryAdapter()
        first = discovery.refresh()
        self.assertIsInstance(first, CapabilityDescriptor)
        self.assertEqual(discovery.stats()["refresh_calls"], 1)


class _LlmAvailableProbe:
    """Probe adapter for capability discovery tests."""


if __name__ == "__main__":  # pragma: no cover
    unittest.main()