"""GraphExpansion port for the v0.8 Phase 3 storage layer.

Covers architecture section §73 (Graph Expansion in Multi-Stage
Retrieval) and §31 (Graph Expansion). Phase 4 owns the production
implementation; Phase 3 ships the port contract and a stub default
adapter.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional, Sequence

from pi_platform.core.canonical.value_types import Entity, Relation


__all__ = [
    "GraphExpansionPort",
    "GraphExpansionError",
    "GraphExpansion",
]


class GraphExpansionError(RuntimeError):
    """Raised when a graph expansion cannot satisfy a request."""


@dataclass(frozen=True)
class GraphExpansion:
    seeds: Sequence[str] = field(default_factory=tuple)
    expandedEntities: Sequence[Entity] = field(default_factory=tuple)
    expandedRelations: Sequence[Relation] = field(default_factory=tuple)
    hops: int = 1
    budget_exhausted: bool = False


class GraphExpansionPort(abc.ABC):
    """Abstract graph expansion port."""

    @abc.abstractmethod
    def expand(
        self, seeds: Sequence[str], *, hops: int = 1,
        edge_types: Optional[Sequence[str]] = None,
        budget: int = 100,
    ) -> GraphExpansion: ...

    @abc.abstractmethod
    def stats(self) -> dict: ...