"""Multi-stage retrieval port for the v0.8 Phase 4 retrieval layer.

Covers architecture section §29 (Multi-Stage Retrieval) and the §33
retrieval-first escalation policy. The :class:`MultiStageRetrievalPort`
orchestrates the seven documented stages (candidate generation →
fusion → metadata / version / security filter → graph expansion →
hierarchy expansion → rerank → context assembly) with explicit per-
stage budgets and per-stage telemetry.

The :class:`RetrievalQuery` value type is the public input shape;
:class:`RetrievalResult` is the public output shape consumed by
Phase 5 (orchestrator) and Phase 6 (MCP server).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import ProjectVersion

from pi_platform.ports.retrieval.context_assembler import ContextBundle
from pi_platform.ports.retrieval.metadata_filter import MetadataFilter


__all__ = [
    "RetrievalQuery",
    "StageReport",
    "RetrievalResult",
    "MultiStageRetrievalPort",
    "MultiStageRetrievalError",
]


class MultiStageRetrievalError(RuntimeError):
    """Raised when the multi-stage pipeline cannot satisfy a request."""


# Documented stage names. The multi-stage pipeline emits one
# :class:`StageReport` per executed stage in the order listed.
STAGE_CANDIDATE_GENERATION = "candidate_generation"
STAGE_FUSION = "fusion"
STAGE_METADATA_FILTER = "metadata_filter"
STAGE_GRAPH_EXPANSION = "graph_expansion"
STAGE_HIERARCHY_EXPANSION = "hierarchy_expansion"
STAGE_RERANK = "rerank"
STAGE_CONTEXT_ASSEMBLY = "context_assembly"
STAGE_ORDER: tuple[str, ...] = (
    STAGE_CANDIDATE_GENERATION,
    STAGE_FUSION,
    STAGE_METADATA_FILTER,
    STAGE_GRAPH_EXPANSION,
    STAGE_HIERARCHY_EXPANSION,
    STAGE_RERANK,
    STAGE_CONTEXT_ASSEMBLY,
)


@dataclass(frozen=True)
class RetrievalQuery:
    """§29 multi-stage retrieval query input."""

    text: str
    top_k: int = 10
    contextBudget: int = 2000
    filters: Optional[MetadataFilter] = None
    purpose: str = ""
    projectVersion: Optional[ProjectVersion] = None
    enableReranking: bool = False

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError(
                f"RetrievalQuery.top_k must be positive, got {self.top_k}"
            )
        if self.contextBudget <= 0:
            raise ValueError(
                f"RetrievalQuery.contextBudget must be positive, got "
                f"{self.contextBudget}"
            )


@dataclass(frozen=True)
class StageReport:
    """§29 per-stage telemetry."""

    stage: str
    candidatesIn: int
    candidatesOut: int
    durationMs: int = 0
    budgetExhausted: bool = False
    error: str = ""

    def __post_init__(self) -> None:
        if self.candidatesIn < 0 or self.candidatesOut < 0:
            raise ValueError(
                "StageReport candidate counters must be non-negative"
            )
        if self.candidatesOut > self.candidatesIn and self.candidatesIn:
            raise ValueError(
                "StageReport.candidatesOut must be <= candidatesIn"
            )


@dataclass(frozen=True)
class RetrievalResult:
    """§29 multi-stage retrieval query output."""

    hits: Sequence[object] = field(default_factory=tuple)
    contextBundle: Optional[ContextBundle] = None
    stageReports: Sequence[StageReport] = field(default_factory=tuple)
    evictions: Sequence[str] = field(default_factory=tuple)
    conflicts: Sequence[object] = field(default_factory=tuple)
    uncertainties: Sequence[object] = field(default_factory=tuple)
    budgetUsed: int = 0


class MultiStageRetrievalPort(abc.ABC):
    """Abstract multi-stage retrieval port."""

    @abc.abstractmethod
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...