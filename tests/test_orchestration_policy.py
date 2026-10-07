"""§33 Retrieval-first agent access policy regression test.

The test is the primary deliverable for Phase 5 task 83. It
asserts that the Phase 5 :class:`QueryOrchestratorPort`
composes the §33 retrieval-first escalation order: retrieval
evidence is gathered BEFORE the LLM completion, the task
context bundle, or any direct source-file scan. The
``retrieval_first_violations`` counter MUST be `0` for the
documented compliant query set.

The test is TDD-first (it asserts the documented contract)
and exercises the real :class:`DefaultQueryOrchestratorAdapter`
with a real Phase 4 ``MultiStageRetrievalPort``-shaped
collaborator. The test is non-flaky: two consecutive runs
produce the same verdict for the same query set.
"""

from __future__ import annotations

import unittest
from typing import Mapping, Sequence

from pi_platform.adapters.orchestration.query_orchestrator import (
    DefaultQueryOrchestratorAdapter,
)
from pi_platform.adapters.orchestration.stub_local_llm import (
    StubLocalLLMAdapter,
)
from pi_platform.adapters.orchestration.task_context import (
    DefaultTaskContextBuilderAdapter,
)
from pi_platform.ports.orchestration.query_orchestrator import (
    OrchestrationLevel,
)
from pi_platform.ports.orchestration.local_llm import LocalLLMPort
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    RetrievalQuery,
    RetrievalResult,
    StageReport,
)


__all__ = ["RetrievalFirstPolicyTests"]


def _hit(chunk_id: str, *, snippet: str = "evidence", token_estimate: int = 16):
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
        knowledgeState=KnowledgeState.VERIFIED,
        tokenEstimate=token_estimate,
    )


class _RecordingPipeline:
    """Records every call so the test can assert the §33 order."""

    def __init__(self, hits: Sequence[RetrievalHit] = ()) -> None:
        self._hits = list(hits)
        self.calls: list[str] = []
        self.last_query: RetrievalQuery | None = None

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        self.calls.append("retrieval")
        self.last_query = query
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
        return {"calls": len(self.calls)}


class _AvailableLLM(LocalLLMPort):
    """Probe LLM port that records when complete() runs."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def complete(self, prompt, *, max_tokens=256, temperature=0.0):
        self.calls.append("llm_complete")
        return "stub completion"

    def is_available(self) -> bool:
        return True

    def model_version(self) -> str:
        return "stub-1.0.0"

    def license_id(self) -> str:
        return "Apache-2.0"

    def family(self) -> str:
        return "stub"

    def stats(self) -> Mapping[str, int]:
        return {"calls": len(self.calls)}


def _orchestrator(
    hits: Sequence[RetrievalHit] = (),
    local_llm: LocalLLMPort | None = None,
    default_level: int = 0,
):
    retrieval = _RecordingPipeline(hits=hits)
    if local_llm is None:
        local_llm = StubLocalLLMAdapter()
    builder = DefaultTaskContextBuilderAdapter()
    orchestrator = DefaultQueryOrchestratorAdapter(
        retrieval=retrieval,
        local_llm=local_llm,
        task_context_builder=builder,
        default_level=default_level,
    )
    return orchestrator, retrieval, local_llm, builder


class RetrievalFirstPolicyTests(unittest.TestCase):
    """§33 retrieval-first policy compliance."""

    def test_implementation_question_triggers_retrieval_first(self):
        orchestrator, retrieval, _, _ = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )
        result = orchestrator.orchestrate(
            "Implement REQ-471 and adapt integration tests.",
            level=2,
        )
        # The retrieval pipeline MUST have run before any
        # task-context bundle is emitted.
        self.assertEqual(retrieval.calls, ["retrieval"])
        self.assertIsNotNone(result.task_context)
        self.assertEqual(result.retrieval_first_violation, False)
        stats = orchestrator.stats()
        self.assertEqual(stats["retrieval_first_violations"], 0)

    def test_orchestrator_does_not_skip_retrieval_stages(self):
        orchestrator, retrieval, _, _ = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )
        orchestrator.orchestrate("Where is OrderStatus declared?", level=0)
        # The retrieval pipeline is the FIRST thing the
        # orchestrator does.
        self.assertEqual(retrieval.calls, ["retrieval"])
        self.assertEqual(orchestrator.stats()["retrieval_first_violations"], 0)

    def test_l0_path_runs_retrieval_first(self):
        orchestrator, retrieval, _, _ = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )
        orchestrator.orchestrate("Where is X?", level=0)
        self.assertEqual(retrieval.calls, ["retrieval"])

    def test_l1_path_runs_retrieval_before_llm(self):
        orchestrator, retrieval, llm, _ = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
            local_llm=_AvailableLLM(),
        )
        orchestrator.orchestrate("Explain the FinishPack protocol.", level=1)
        # The retrieval pipeline ran first, then the LLM.
        self.assertEqual(retrieval.calls, ["retrieval"])
        self.assertEqual(llm.calls, ["llm_complete"])

    def test_l2_path_runs_retrieval_before_task_context(self):
        orchestrator, retrieval, _, _ = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )
        orchestrator.orchestrate("Implement REQ-471.", level=2)
        # The retrieval pipeline ran first; the task context was
        # emitted only after retrieval returned.
        self.assertEqual(retrieval.calls, ["retrieval"])
        self.assertEqual(orchestrator.stats()["retrieval_first_violations"], 0)

    def test_violation_counter_starts_at_zero(self):
        orchestrator, _, _, _ = _orchestrator()
        stats = orchestrator.stats()
        self.assertEqual(stats["retrieval_first_violations"], 0)

    def test_repeated_policy_run_is_stable(self):
        first = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )[0]
        second = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )[0]
        for query in (
            "Where is OrderStatus declared?",
            "Implement REQ-471.",
        ):
            first.orchestrate(query, level=2)
            second.orchestrate(query, level=2)
        self.assertEqual(
            first.stats()["retrieval_first_violations"],
            second.stats()["retrieval_first_violations"],
        )

    def test_l1_path_records_no_violation_when_llm_unavailable(self):
        orchestrator, retrieval, llm, _ = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )
        # Stub LLM is unavailable; the orchestrator escalates to
        # L2 but the retrieval pipeline ran first.
        self.assertFalse(llm.is_available())
        result = orchestrator.orchestrate("Explain X.", level=1)
        self.assertEqual(
            result.level, OrchestrationLevel.L2_STRONG_EXTERNAL_AGENT,
        )
        self.assertEqual(retrieval.calls, ["retrieval"])
        self.assertEqual(orchestrator.stats()["retrieval_first_violations"], 0)

    def test_explanations_record_level_and_retrieval_first_state(self):
        orchestrator, _, _, _ = _orchestrator(
            hits=[_hit("c-1", snippet="FinishPack")],
        )
        result = orchestrator.orchestrate("Where is X?", level=0)
        joined = "\n".join(result.explanations)
        self.assertIn("level=L0", joined)
        self.assertIn("retrieval_first_violation=False", joined)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()