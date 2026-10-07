"""Phase 4 preview :class:`GraphExpansionPort` stub adapter.

Phase 4 task 73 owns the production implementation; this stub
documents the port contract and returns the seed entities unchanged.
"""

from __future__ import annotations

from typing import Optional, Sequence

from pi_platform.core.canonical.value_types import Entity
from pi_platform.ports.runtime.graph import GraphPort
from pi_platform.ports.runtime.graph_expansion import (
    GraphExpansion,
    GraphExpansionError,
    GraphExpansionPort,
)


__all__ = ["BoundedGraphExpansion"]


class BoundedGraphExpansion(GraphExpansionPort):
    """Stub adapter that documents the budget + edge-type contract."""

    def __init__(self, graph: GraphPort):
        self._graph = graph

    def expand(
        self, seeds: Sequence[str], *, hops: int = 1,
        edge_types: Optional[Sequence[str]] = None,
        budget: int = 100,
    ) -> GraphExpansion:
        if budget <= 0:
            raise GraphExpansionError("budget must be positive")
        entities: list[Entity] = []
        relations = []
        seen: set[str] = set()
        exhausted = False
        for seed in seeds:
            if seed in seen:
                continue
            if len(entities) >= budget:
                exhausted = True
                break
            seen.add(seed)
            entity = self._graph.get_entity(seed)
            if entity is not None:
                entities.append(entity)
            for hop in range(hops):
                if len(entities) >= budget:
                    exhausted = True
                    break
                seed_rels = self._graph.get_relations(
                    seed, edge_type=edge_types[0] if edge_types and len(edge_types) == 1 else None
                )
                for rel in seed_rels:
                    if len(entities) >= budget:
                        exhausted = True
                        break
                    if edge_types is not None and rel.family not in edge_types:
                        continue
                    relations.append(rel)
                    target = self._graph.get_entity(rel.targetId)
                    if target is not None and target.id not in seen:
                        seen.add(target.id)
                        if len(entities) >= budget:
                            exhausted = True
                            break
                        entities.append(target)
                        seed = rel.targetId
        return GraphExpansion(
            seeds=tuple(seeds),
            expandedEntities=tuple(entities[:budget]),
            expandedRelations=tuple(relations),
            hops=hops,
            budget_exhausted=exhausted,
        )

    def stats(self) -> dict:
        return {"expansions": 0, "stub": 1}