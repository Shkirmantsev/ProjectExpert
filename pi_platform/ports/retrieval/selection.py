"""Candidate selection port for the v0.8 Phase 4 retrieval layer.

Introduces the non-destructive candidate-selection contract from the
``improve-ingestion-retrieval-local-models`` change package
(``specs/retrieval-candidate-selection``): the
:class:`SelectionState` enum, the :class:`CandidateTrace` /
:class:`SelectionResult` value objects and the
:class:`SelectionPort` interface. Selection runs after rerank and
before graph / hierarchy expansion; it is runtime / evaluation state
and is never committed to canonical Git knowledge.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from enum import Enum
from typing import Sequence

from pi_platform.core.retrieval.query_features import QueryFeatures
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit


__all__ = [
    "SelectionState",
    "CandidateTrace",
    "SelectionResult",
    "SelectionPort",
    "DEFAULT_PRIMARY_TOP_K",
    "DEFAULT_RESERVE_TOP_K",
    "DEFAULT_MAX_PRIMARY_PER_SOURCE",
]


# Default selection budgets from the retrieval-candidate-selection
# delta spec: at least 8 PRIMARY, at least 24 RESERVE, and a soft
# source-diversity cap of 3 chunks per source document applied to
# PRIMARY only.
DEFAULT_PRIMARY_TOP_K = 8
DEFAULT_RESERVE_TOP_K = 24
DEFAULT_MAX_PRIMARY_PER_SOURCE = 3


class SelectionState(str, Enum):
    """Non-destructive candidate lifecycle states."""

    PRIMARY = "PRIMARY"
    RESERVE = "RESERVE"
    PROTECTED = "PROTECTED"
    SUPPORT = "SUPPORT"
    DROPPED_DUPLICATE = "DROPPED_DUPLICATE"


@dataclass(frozen=True)
class CandidateTrace:
    """Per-candidate selection provenance (runtime / evaluation only)."""

    chunk_id: str
    dense_rank: int = 0
    sparse_rank: int = 0
    exact_match: bool = False
    rrf_rank: int = 0
    rrf_score: float = 0.0
    rerank_rank: int = 0
    rerank_score: float = 0.0
    selection_state: SelectionState = SelectionState.PRIMARY
    protected_reason: str = ""
    duplicate_of: str = ""
    source_document_id: str = ""
    trace_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SelectionResult:
    """Grouped selection output; every candidate lands in a pool or trace."""

    primary: tuple[RetrievalHit, ...] = ()
    reserve: tuple[RetrievalHit, ...] = ()
    protected: tuple[RetrievalHit, ...] = ()
    support: tuple[RetrievalHit, ...] = ()
    dropped_duplicate: tuple[RetrievalHit, ...] = ()
    traces: tuple[CandidateTrace, ...] = ()


class SelectionPort(abc.ABC):
    """Abstract non-destructive candidate selection port."""

    @abc.abstractmethod
    def select(
        self, candidates: Sequence[RetrievalHit], *,
        query_features: QueryFeatures | None,
        budget: int,
    ) -> SelectionResult: ...
