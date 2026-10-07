"""Default query orchestrator core.

Implements :class:`pi_platform.ports.orchestration.query_orchestrator.QueryOrchestratorPort`
with the deterministic three-level (L0 / L1 / L2) escalation
the §34 spec documents. The core composes the Phase 4
:class:`pi_platform.ports.retrieval.multi_stage_retrieval.MultiStageRetrievalPort`
and the Phase 5 :class:`LocalLLMPort`; the
:class:`TaskContextBuilderPort` is invoked at L2.

The level-selection heuristic is intentionally simple
(prioritise L0, escalate on demand) and remains config-
driven through
`project-context.yaml:orchestrator.level_selection`. The
retrieval-first policy is enforced: every escalation path
runs the retrieval pipeline first, and the
`retrieval_first_violations` counter increments when an
external direct source-file scan is triggered before
retrieval evidence is gathered.
"""

from __future__ import annotations

from typing import Mapping, Optional

from pi_platform.core.canonical.value_types import ProjectVersion
from pi_platform.ports.orchestration.local_llm import LocalLLMPort
from pi_platform.ports.orchestration.query_orchestrator import (
    EscalationCapError,
    FilteredEscalationNotSupportedError,
    OrchestrationLevel,
    OrchestrationResult,
    QueryOrchestratorError,
    QueryOrchestratorPort,
)
from pi_platform.ports.orchestration.task_context import (
    TaskContextBuilderPort,
    TaskContextBundle,
)
from pi_platform.ports.retrieval.metadata_filter import MetadataFilter
from pi_platform.ports.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalPort,
    RetrievalQuery,
)


__all__ = [
    "DefaultQueryOrchestrator",
    "DEFAULT_LLM_MAX_TOKENS",
    "DEFAULT_L2_BUDGET_TOKENS",
]


DEFAULT_LLM_MAX_TOKENS = 256
DEFAULT_L2_BUDGET_TOKENS = 4000


class DefaultQueryOrchestrator(QueryOrchestratorPort):
    """§34 deterministic query orchestrator."""

    def __init__(
        self,
        retrieval: MultiStageRetrievalPort,
        local_llm: LocalLLMPort,
        task_context_builder: TaskContextBuilderPort,
        *,
        default_level: int = 0,
    ) -> None:
        if not 0 <= int(default_level) <= 2:
            raise QueryOrchestratorError(
                f"default_level must be 0, 1, or 2; got {default_level!r}"
            )
        self._retrieval = retrieval
        self._local_llm = local_llm
        self._task_context_builder = task_context_builder
        self._default_level = OrchestrationLevel.from_int(default_level)
        self._level0_calls = 0
        self._level1_calls = 0
        self._level2_calls = 0
        self._escalations = 0
        self._retrieval_first_violations = 0

    def orchestrate(
        self, query: str, *, level: Optional[int] = None,
        task_context: object = None,
        filters: Optional[MetadataFilter] = None,
        project_version: Optional[ProjectVersion] = None,
    ) -> OrchestrationResult:
        target = (
            OrchestrationLevel.from_int(level)
            if level is not None else self._default_level
        )
        # Prerequisite 2: filter / scope preservation through
        # orchestration. L0 preserves the typed filters /
        # project-version; L1 / L2 reject filtered queries
        # explicitly until a separately specified extension
        # preserves them through escalation. Filters that are
        # bound to the project_version (e.g. validFrom /
        # validTo) MUST be scoped to a specific project version
        # for L0.
        has_filters = filters is not None
        if has_filters and target is not OrchestrationLevel.L0_DIRECT_RETRIEVAL:
            raise FilteredEscalationNotSupportedError(
                level=target, filters=filters,
                project_version=project_version,
            )
        retrieval_query = RetrievalQuery(
            text=query,
            top_k=10,
            contextBudget=max(2000, 0),
            filters=filters,
            projectVersion=project_version,
            enableReranking=(target == OrchestrationLevel.L1_RETRIEVAL_PLUS_LLM),
        )
        retrieval_result = self._retrieval.retrieve(retrieval_query)
        if target == OrchestrationLevel.L0_DIRECT_RETRIEVAL:
            self._level0_calls += 1
            return OrchestrationResult(
                level=OrchestrationLevel.L0_DIRECT_RETRIEVAL,
                query=query,
                retrieval=retrieval_result,
                llm_completion=None,
                task_context=None,
                budgetUsed=retrieval_result.budgetUsed,
                explanations=(
                    f"goal={query!r}",
                    "level=L0 direct retrieval; no LLM completion",
                    "retrieval_first_violation=False",
                ),
                retrieval_first_violation=False,
            )
        if target == OrchestrationLevel.L1_RETRIEVAL_PLUS_LLM:
            self._level1_calls += 1
            if not self._local_llm.is_available():
                self._escalations += 1
                return self._escalate_to_l2(
                    query=query,
                    retrieval_result=retrieval_result,
                    reason="local_llm_unavailable",
                )
            prompt = self._build_llm_prompt(query, retrieval_result)
            completion = self._local_llm.complete(
                prompt, max_tokens=DEFAULT_LLM_MAX_TOKENS,
            )
            return OrchestrationResult(
                level=OrchestrationLevel.L1_RETRIEVAL_PLUS_LLM,
                query=query,
                retrieval=retrieval_result,
                llm_completion=completion,
                task_context=None,
                budgetUsed=retrieval_result.budgetUsed
                + len(completion.split()),
                explanations=(
                    f"goal={query!r}",
                    "level=L1 retrieval + small local LLM",
                    f"llm_completion_length={len(completion)}",
                    "retrieval_first_violation=False",
                ),
                retrieval_first_violation=False,
            )
        # L2
        self._level2_calls += 1
        return self._emit_l2(query, retrieval_result)

    def escalate(
        self, orchestration: OrchestrationResult, *, reason: str,
    ) -> OrchestrationResult:
        self._escalations += 1
        next_level_value = int(orchestration.level) + 1
        if next_level_value > 2:
            raise EscalationCapError(
                f"cannot escalate past L2 (current level={int(orchestration.level)})"
            )
        next_level = OrchestrationLevel.from_int(next_level_value)
        if next_level == OrchestrationLevel.L1_RETRIEVAL_PLUS_LLM:
            if not self._local_llm.is_available():
                return self._escalate_to_l2(
                    query=orchestration.query,
                    retrieval_result=orchestration.retrieval,
                    reason=reason or "local_llm_unavailable",
                )
            prompt = self._build_llm_prompt(
                orchestration.query, orchestration.retrieval,
            )
            completion = self._local_llm.complete(
                prompt, max_tokens=DEFAULT_LLM_MAX_TOKENS,
            )
            self._level1_calls += 1
            return OrchestrationResult(
                level=OrchestrationLevel.L1_RETRIEVAL_PLUS_LLM,
                query=orchestration.query,
                retrieval=orchestration.retrieval,
                llm_completion=completion,
                task_context=None,
                budgetUsed=orchestration.budgetUsed
                + len(completion.split()),
                explanations=(
                    f"goal={orchestration.query!r}",
                    f"escalated_from=L{orchestration.level}",
                    f"reason={reason}",
                    "retrieval_first_violation=False",
                ),
                retrieval_first_violation=False,
            )
        # L2
        return self._emit_l2(
            query=orchestration.query,
            retrieval_result=orchestration.retrieval,
            reason=reason,
        )

    def stats(self) -> Mapping[str, int]:
        return {
            "level0_calls": self._level0_calls,
            "level1_calls": self._level1_calls,
            "level2_calls": self._level2_calls,
            "escalations": self._escalations,
            "retrieval_first_violations": self._retrieval_first_violations,
        }

    # -- internal helpers --------------------------------------------------

    def _emit_l2(
        self, query: str, retrieval_result: object,
        reason: str = "implementation_work",
    ) -> OrchestrationResult:
        if retrieval_result is None:
            self._retrieval_first_violations += 1
            raise QueryOrchestratorError(
                "retrieval-first policy violation: L2 emitted without "
                "retrieval evidence"
            )
        bundle = self._task_context_builder.build(
            goal=query,
            budget_tokens=DEFAULT_L2_BUDGET_TOKENS,
            retrieval=retrieval_result,
        )
        return OrchestrationResult(
            level=OrchestrationLevel.L2_STRONG_EXTERNAL_AGENT,
            query=query,
            retrieval=retrieval_result,
            llm_completion=None,
            task_context=bundle,
            budgetUsed=DEFAULT_L2_BUDGET_TOKENS
            - sum(getattr(bundle, "budgetTokens", 0) and [] or []),
            explanations=(
                f"goal={query!r}",
                "level=L2 strong external agent (task context bundle)",
                f"reason={reason}",
                f"task_id={getattr(bundle, 'taskId', '')}",
                "retrieval_first_violation=False",
            ),
            retrieval_first_violation=False,
        )

    def _escalate_to_l2(
        self, query: str, retrieval_result: object, reason: str,
    ) -> OrchestrationResult:
        return self._emit_l2(
            query=query, retrieval_result=retrieval_result, reason=reason,
        )

    @staticmethod
    def _build_llm_prompt(query: str, retrieval_result: object) -> str:
        snippets: list[str] = []
        for hit in getattr(retrieval_result, "hits", [])[:5]:
            snippet = getattr(hit, "snippet", "")
            if snippet:
                snippets.append(snippet[:200])
        joined = "\n".join(snippets)
        return (
            f"Goal: {query}\n\nEvidence:\n{joined}\n\n"
            "Provide a concise answer grounded in the evidence above."
        )