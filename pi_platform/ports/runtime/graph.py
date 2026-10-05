"""Graph port for the v0.8 Phase 3 storage layer.

Covers architecture section §66 (Source Configuration Example —
canonical knowledge graph), §10.1 (Sharded Graph Storage), §16
(Canonical Knowledge Graph) and §17 (ANN Graphs vs Knowledge
Graphs).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import (
    Entity,
    KnowledgeState,
    Relation,
    Shard,
)


__all__ = [
    "GraphPort",
    "GraphPortError",
    "GraphManifest",
]


class GraphPortError(RuntimeError):
    """Raised when the canonical knowledge graph cannot satisfy a
    request."""


@dataclass(frozen=True)
class GraphManifest:
    family: str
    schemaVersion: str
    shards: Sequence[Shard] = field(default_factory=tuple)
    dependencies: Sequence[str] = field(default_factory=tuple)
    contentHash: Optional[str] = None
    entity_count: int = 0
    relation_count: int = 0


class GraphPort(abc.ABC):
    """Abstract canonical knowledge-graph port."""

    @abc.abstractmethod
    def upsert_entity(self, entity: Entity) -> None: ...

    @abc.abstractmethod
    def upsert_relation(self, relation: Relation) -> None: ...

    @abc.abstractmethod
    def get_entity(self, entity_id: str) -> Optional[Entity]: ...

    @abc.abstractmethod
    def get_relations(
        self, entity_id: str, *, edge_type: Optional[str] = None,
        direction: str = "outgoing",
    ) -> Sequence[Relation]: ...

    @abc.abstractmethod
    def shard_by(self, content_hash: str) -> Shard: ...

    @abc.abstractmethod
    def rebuild_manifest(self) -> GraphManifest: ...

    @abc.abstractmethod
    def backend_name(self) -> str: ...