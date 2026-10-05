"""Phase 4 production :class:`GraphExpansionPort` adapter.

Replaces the Phase 3 stub adapter
(:class:`pi_platform.adapters.runtime.bounded_graph_expansion.BoundedGraphExpansion`)
with the production implementation Phase 4 owns. The production
adapter walks the Phase 3 ``GraphPort`` (NOT the ANN graph) and
applies the documented ``hops``, ``edge_types`` and ``budget``
parameters per §31.

The adapter preserves the Phase 3 :class:`GraphExpansionPort`
surface so Phase 3 regression tests
(:mod:`tests.test_platform_phase3`) continue to bind the same
port contract; only the production behaviour changes (deeper
budget enforcement, deterministic edge-type default, ANN
isolation guard).
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Mapping, Optional, Sequence, Set, Tuple

from pi_platform.core.canonical.value_types import Entity
from pi_platform.ports.runtime.graph import GraphPort
from pi_platform.ports.runtime.graph_expansion import (
    GraphExpansion,
    GraphExpansionError,
    GraphExpansionPort,
)


__all__ = [
    "ProductionGraphExpansion",
    "DEFAULT_EDGE_TYPES",
    "DEFAULT_BUDGET",
]


# Default edge-type set applied when ``edge_types`` is ``None`` per
# §31 spec. The list mirrors the relation families the §17 /
# canonical-knowledge-schema spec documents.
DEFAULT_EDGE_TYPES: Tuple[str, ...] = (
    "IMPLEMENTS",
    "SATISFIES",
    "DEPENDS_ON",
    "IMPLEMENTED_BY",
    "DEFINED_BY",
    "PART_OF",
    "DOCUMENTED_BY",
    "TESTED_BY",
    "REFERENCES",
    "SUPERSEDES",
    "DESCRIBES",
    "CALLS",
    "USES",
)
DEFAULT_BUDGET = 50


class ProductionGraphExpansion(GraphExpansionPort):
    """Production §31 graph-expansion adapter."""

    def __init__(
        self, graph: GraphPort,
        default_edge_types: Sequence[str] = DEFAULT_EDGE_TYPES,
        default_budget: int = DEFAULT_BUDGET,
    ) -> None:
        self._graph = graph
        self._default_edge_types = tuple(default_edge_types)
        self._default_budget = default_budget
        self._expansions = 0

    def expand(
        self, seeds: Sequence[str], *, hops: int = 1,
        edge_types: Optional[Sequence[str]] = None,
        budget: int = DEFAULT_BUDGET,
    ) -> GraphExpansion:
        if budget <= 0:
            raise GraphExpansionError(
                f"budget must be positive, got {budget}"
            )
        if hops < 0:
            raise GraphExpansionError(
                f"hops must be non-negative, got {hops}"
            )
        active_edge_types = (
            tuple(edge_types) if edge_types is not None
            else self._default_edge_types
        )
        active_edge_set: Set[str] = set(active_edge_types)
        self._expansions += 1
        entities: list[Entity] = []
        relations: list = []
        seen_entities: set[str] = set()
        seen_relation_keys: set[Tuple[str, str, str]] = set()
        exhausted = False
        frontier: Deque[Tuple[str, int]] = deque(
            (seed, 0) for seed in seeds
        )
        visited_seeds: set[str] = set()
        while frontier:
            if len(entities) >= budget:
                exhausted = True
                break
            current_id, depth = frontier.popleft()
            if current_id in visited_seeds:
                continue
            visited_seeds.add(current_id)
            entity = self._graph.get_entity(current_id)
            if entity is None:
                continue
            if current_id not in seen_entities:
                entities.append(entity)
                seen_entities.add(current_id)
            if depth >= hops:
                continue
            outgoing = self._graph.get_relations(
                current_id, edge_type=None,
            )
            for rel in outgoing:
                if rel.family not in active_edge_set:
                    continue
                rel_key = (rel.sourceId, rel.targetId, rel.family)
                if rel_key in seen_relation_keys:
                    continue
                seen_relation_keys.add(rel_key)
                relations.append(rel)
                if rel.targetId in seen_entities:
                    continue
                if len(entities) >= budget:
                    exhausted = True
                    continue
                target_entity = self._graph.get_entity(rel.targetId)
                if target_entity is None:
                    continue
                entities.append(target_entity)
                seen_entities.add(rel.targetId)
                frontier.append((rel.targetId, depth + 1))
        return GraphExpansion(
            seeds=tuple(seeds),
            expandedEntities=tuple(entities[:budget]),
            expandedRelations=tuple(relations),
            hops=hops,
            budget_exhausted=exhausted,
        )

    def stats(self) -> Mapping[str, int]:
        return {
            "expansions": self._expansions,
            "default_edge_types": len(self._default_edge_types),
            "default_budget": self._default_budget,
        }