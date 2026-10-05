"""Default query orchestrator adapter.

Wraps :class:`pi_platform.core.orchestration.query_orchestrator.DefaultQueryOrchestrator`
as a thin adapter so the registry / CLI can introspect the
same shape across the default and alternative orchestrator
implementations.
"""

from __future__ import annotations

from pi_platform.core.orchestration.query_orchestrator import (
    DEFAULT_LLM_MAX_TOKENS,
    DEFAULT_L2_BUDGET_TOKENS,
    DefaultQueryOrchestrator,
)


__all__ = [
    "DefaultQueryOrchestratorAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "query-orchestrator-default"


class DefaultQueryOrchestratorAdapter(DefaultQueryOrchestrator):
    """Default §34 query orchestrator adapter."""

    def __init__(
        self, retrieval, local_llm, task_context_builder, *,
        default_level: int = 0,
    ) -> None:
        super().__init__(
            retrieval=retrieval,
            local_llm=local_llm,
            task_context_builder=task_context_builder,
            default_level=default_level,
        )
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name