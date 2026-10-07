"""Default :class:`GraphPort` implementation (hash-prefix sharded
graph).

The implementation uses the §10.1 hash-prefix shard layout
(``graph/nodes/<prefix>/``, ``graph/edges/<prefix>/``) with one
JSONL body file per prefix directory (so the per-prefix shard count
is bounded by the number of hash prefixes — 256 by default). The
50 000-entity property test (``tests/test_graph_50k.py``) asserts
both the shard count distribution and the 32 MiB per-file cap.

Entity bodies are appended to the prefix shard whose first two
characters of the entity-id SHA-256 hash match; reads scan the shard
line-by-line until the matching entity ID is found.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Optional, Sequence

from pi_platform.core.canonical.content_address import (
    content_address_bytes,
    object_path,
)
from pi_platform.core.canonical.serializer import canonical_dump_json
from pi_platform.core.canonical.value_types import (
    Entity,
    KnowledgeState,
    Relation,
    Shard,
    from_canonical_json,
    to_canonical_json,
)
from pi_platform.ports.runtime.graph import (
    GraphManifest,
    GraphPort,
    GraphPortError,
)


__all__ = ["LocalShardedGraph"]


class LocalShardedGraph(GraphPort):
    """Default canonical knowledge-graph adapter."""

    NODES_DIR = "nodes"
    EDGES_DIR = "edges"
    OBJECTS_DIR = "objects"
    SHARDS_PER_PREFIX = 256

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / self.NODES_DIR).mkdir(exist_ok=True)
        (self.root / self.EDGES_DIR).mkdir(exist_ok=True)
        (self.root / self.OBJECTS_DIR).mkdir(exist_ok=True)
        self._manifest_path = self.root / "graph-manifest.json"
        self._edge_index_path = self.root / "edge-index.jsonl"

    @staticmethod
    def _id_hash(entity_id: str) -> str:
        return hashlib.sha256(entity_id.encode("utf-8")).hexdigest()

    def _shard_path_for_entity(self, kind: str, entity_id: str) -> Path:
        id_hash = self._id_hash(entity_id)
        prefix = id_hash[:2]
        d = self.root / kind / prefix
        d.mkdir(parents=True, exist_ok=True)
        return d / "shard.jsonl"

    def _shard_dir(self, kind: str, content_hash: str) -> Path:
        if len(content_hash) < 2:
            raise GraphPortError(
                f"content_hash must be at least 2 hex chars; got {content_hash!r}"
            )
        prefix = content_hash[:2]
        d = self.root / kind / prefix
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _shard_path(self, kind: str, content_hash: str) -> Path:
        return self._shard_dir(kind, content_hash) / "shard.jsonl"

    def shard_by(self, content_hash: str) -> Shard:
        shard_path = self._shard_path(self.NODES_DIR, content_hash)
        relative = shard_path.relative_to(self.root)
        return Shard(
            id=f"nodes/{content_hash[:2]}",
            path=str(relative),
            contentHash=content_hash,
        )

    def _write_shard_line(self, shard_path: Path, new_line: bytes, key_fn) -> None:
        new_line = new_line.rstrip(b"\n")
        existing: list[bytes] = []
        if shard_path.exists():
            existing = [line for line in shard_path.read_bytes().splitlines() if line.strip()]
        target_key = key_fn(new_line)
        kept: list[bytes] = []
        replaced = False
        for line in existing:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            if key_fn(line) == target_key:
                kept.append(new_line)
                replaced = True
            else:
                kept.append(line)
        if not replaced:
            kept.append(new_line)
        shard_path.write_bytes(b"\n".join(kept) + b"\n")

    def upsert_entity(self, entity: Entity) -> None:
        body = to_canonical_json(entity)
        content_address = content_address_bytes(body)
        canonical_obj_path = self.root / object_path(content_address)
        canonical_obj_path.parent.mkdir(parents=True, exist_ok=True)
        if not canonical_obj_path.exists():
            canonical_obj_path.write_bytes(body)
        shard_path = self._shard_path_for_entity(self.NODES_DIR, entity.id)
        self._write_shard_line(
            shard_path,
            body,
            key_fn=lambda line: json.loads(line).get("id"),
        )

    def upsert_relation(self, relation: Relation) -> None:
        body = to_canonical_json(relation)
        content_address = content_address_bytes(body)
        canonical_obj_path = self.root / object_path(content_address)
        canonical_obj_path.parent.mkdir(parents=True, exist_ok=True)
        if not canonical_obj_path.exists():
            canonical_obj_path.write_bytes(body)
        shard_path = self._shard_path_for_entity(self.EDGES_DIR, relation.sourceId)
        self._write_shard_line(
            shard_path,
            body,
            key_fn=lambda line: (
                json.loads(line).get("sourceId"),
                json.loads(line).get("targetId"),
                json.loads(line).get("family"),
            ),
        )
        index_record = canonical_dump_json({
            "sourceId": relation.sourceId,
            "shardPath": str(shard_path.relative_to(self.root)),
        })
        with self._edge_index_path.open("ab") as fh:
            fh.write(index_record)
            fh.write(b"\n")

    def get_entity(self, entity_id: str) -> Optional[Entity]:
        shard_path = self._shard_path_for_entity(self.NODES_DIR, entity_id)
        if not shard_path.exists():
            return None
        for line in shard_path.read_bytes().splitlines():
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if parsed.get("id") != entity_id:
                continue
            return from_canonical_json(Entity, line)
        return None

    def get_relations(
        self, entity_id: str, *, edge_type: Optional[str] = None,
        direction: str = "outgoing",
    ) -> Sequence[Relation]:
        if direction == "outgoing":
            shard_path = self._shard_path_for_entity(self.EDGES_DIR, entity_id)
            if not shard_path.exists():
                return ()
            result = []
            for line in shard_path.read_bytes().splitlines():
                if not line.strip():
                    continue
                try:
                    rel_dict = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rel_dict.get("sourceId") != entity_id:
                    continue
                if edge_type is not None and rel_dict.get("family") != edge_type:
                    continue
                result.append(from_canonical_json(Relation, line))
            return tuple(result)
        result = []
        for line in self._edge_index_path.read_bytes().splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record["sourceId"] != entity_id:
                continue
            shard_path = self.root / record["shardPath"]
            for rel_line in shard_path.read_bytes().splitlines():
                if not rel_line.strip():
                    continue
                rel_dict = json.loads(rel_line)
                if rel_dict.get("targetId") != entity_id:
                    continue
                if edge_type is not None and rel_dict.get("family") != edge_type:
                    continue
                result.append(from_canonical_json(Relation, rel_line))
        return tuple(result)

    def rebuild_manifest(self) -> GraphManifest:
        shards: list[Shard] = []
        entity_count = 0
        relation_count = 0
        for prefix_dir in sorted((self.root / self.NODES_DIR).iterdir()):
            if not prefix_dir.is_dir():
                continue
            for shard_file in sorted(prefix_dir.glob("shard.jsonl")):
                count = sum(1 for line in shard_file.read_bytes().splitlines() if line.strip())
                entity_count += count
                shards.append(Shard(
                    id=f"nodes/{prefix_dir.name}",
                    path=str(shard_file.relative_to(self.root)),
                    contentHash=prefix_dir.name,
                    count=count,
                ))
        for prefix_dir in sorted((self.root / self.EDGES_DIR).iterdir()):
            if not prefix_dir.is_dir():
                continue
            for shard_file in sorted(prefix_dir.glob("shard.jsonl")):
                count = sum(1 for line in shard_file.read_bytes().splitlines() if line.strip())
                relation_count += count
                shards.append(Shard(
                    id=f"edges/{prefix_dir.name}",
                    path=str(shard_file.relative_to(self.root)),
                    contentHash=prefix_dir.name,
                    count=count,
                ))
        manifest = GraphManifest(
            family="knowledge_graph",
            schemaVersion="0.1.0",
            shards=tuple(shards),
            dependencies=("pi_platform.ports.runtime.graph",),
            contentHash=None,
            entity_count=entity_count,
            relation_count=relation_count,
        )
        self._manifest_path.write_bytes(canonical_dump_json({
            "schemaVersion": manifest.schemaVersion,
            "family": manifest.family,
            "shards": [
                {
                    "id": s.id,
                    "path": s.path,
                    "contentHash": s.contentHash,
                    "count": s.count,
                }
                for s in manifest.shards
            ],
            "dependencies": list(manifest.dependencies),
            "entity_count": manifest.entity_count,
            "relation_count": manifest.relation_count,
        }))
        return manifest

    def backend_name(self) -> str:
        return "sharded-graph"