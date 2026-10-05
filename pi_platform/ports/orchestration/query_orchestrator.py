"""Query orchestrator port for the v0.8 Phase 5 orchestration
layer.

Covers architecture section §34 (Query Orchestrator) and the
§33 retrieval-first agent access strategy the orchestrator
encodes. The :class:`QueryOrchestratorPort` composes the
Phase 4 :class:`pi_platform.ports.retrieval.multi_stage_retrieval.MultiStageRetrievalPort`
and the Phase 5 :class:`LocalLLMPort` into the three
documented escalation levels (L0 direct retrieval, L1
retrieval + small local LLM, L2 strong external agent).
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence


__all__ = [
    "OrchestrationLevel",
    "OrchestrationResult",
    "QueryOrchestratorError",
    "QueryOrchestratorPort",
]


class OrchestrationLevel(int, enum.Enum):
    """§34 three-level escalation."""

    L0_DIRECT_RETRIEVAL = 0
    L1_RETRIEVAL_PLUS_LLM = 1
    L2_STRONG_EXTERNAL_AGENT = 2

    @classmethod
    def from_int(cls, value: int) -> "OrchestrationLevel":
        try:
            return cls(value)
        except ValueError as exc:
            raise QueryOrchestratorError(
                f"unknown orchestration level: {value!r}"
            ) from exc


class QueryOrchestratorError(RuntimeError):
    """Raised when the orchestrator cannot satisfy a request."""


class EscalationCapError(QueryOrchestratorError):
    """Raised when the orchestrator is asked to escalate past L2."""


@dataclass(frozen=True)
class OrchestrationResult:
    """The orchestrator's per-query output."""

    level: OrchestrationLevel
    query: str
    retrieval: object = None
    llm_completion: Optional[str] = None
    task_context: object = None
    budgetUsed: int = 0
    explanations: Sequence[str] = field(default_factory=tuple)
    retrieval_first_violation: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.level, OrchestrationLevel):
            self.level = OrchestrationLevel.from_int(int(self.level))


class QueryOrchestratorPort(abc.ABC):
    """Abstract query orchestrator port."""

    @abc.abstractmethod
    def orchestrate(
        self, query: str, *, level: Optional[int] = None,
        task_context: object = None,
    ) -> OrchestrationResult: ...

    @abc.abstractmethod
    def escalate(
        self, orchestration: OrchestrationResult, *, reason: str,
    ) -> OrchestrationResult: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...