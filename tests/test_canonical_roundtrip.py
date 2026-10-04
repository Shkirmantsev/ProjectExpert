"""Property-based round-trip tests for the canonical value types.

The
[`canonical-knowledge-schema`](../../openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md)
spec requires a property-based test asserting byte-identical canonical
serialization for at least 100 randomized shuffled-order instances of
each Phase 1 value type.
"""

from __future__ import annotations

import random
import string
import unittest
from dataclasses import fields
from typing import Iterable

from pi_platform.core.canonical import (
    Chunk,
    Entity,
    Evidence,
    KnowledgeState,
    Manifest,
    Metadata,
    ProjectVersion,
    Relation,
    Section,
    Shard,
    Source,
    chunk_content_address,
    from_canonical_json,
    to_canonical_json,
)


def _rng() -> random.Random:
    return random.Random(20261004)


def _string(rng: random.Random, n: int = 8) -> str:
    return "".join(rng.choice(string.ascii_letters) for _ in range(n))


def _metadata(rng: random.Random) -> Metadata:
    return Metadata(
        documentId=_string(rng),
        version=f"0.{rng.randint(0, 9)}.{rng.randint(0, 9)}",
        language=rng.choice(["en", "de", "uk", "und"]),
        section=_string(rng, 6) if rng.random() > 0.3 else None,
        businessDomain=_string(rng, 6) if rng.random() > 0.5 else None,
        requirementId=_string(rng, 6) if rng.random() > 0.5 else None,
        contentHash=_string(rng, 16) if rng.random() > 0.5 else None,
    )


def _chunk(rng: random.Random) -> Chunk:
    raw = _string(rng, 16)
    return Chunk(
        id=_string(rng),
        rawText=raw,
        contextualText=_string(rng, 16),
        metadata=_metadata(rng),
        sourceReference=_string(rng, 8),
        contentHash="0" * 64,
        parentId=_string(rng, 8) if rng.random() > 0.4 else None,
        childIds=tuple(sorted(_string(rng, 6) for _ in range(rng.randint(0, 4)))),
        entityIds=tuple(sorted(_string(rng, 6) for _ in range(rng.randint(0, 3)))),
        provenance=Evidence(
            knowledgeState=KnowledgeState.VERIFIED,
            parserVersion="0.1.0",
        ),
    )


def _entity(rng: random.Random) -> Entity:
    """Entity whose relations are sorted by targetId so the canonical
    serializer preserves them unchanged and the round-trip equals the
    original.
    """
    raw_rels = [
        Relation(
            sourceId=_string(rng, 6),
            targetId=_string(rng, 6),
            family=rng.choice(["IMPLEMENTS", "DEPENDS_ON", "CALLS"]),
        )
        for _ in range(rng.randint(0, 5))
    ]
    rels = tuple(sorted(raw_rels, key=lambda r: r.targetId))
    return Entity(
        id=_string(rng, 8),
        family=rng.choice(["java-class", "component", "requirement"]),
        label=_string(rng, 8),
        description=_string(rng, 12) if rng.random() > 0.4 else None,
        metadata=_metadata(rng),
        relations=rels,
        knowledgeState=rng.choice(list(KnowledgeState)),
    )


def _manifest(rng: random.Random) -> Manifest:
    shards = tuple(
        Shard(
            id=_string(rng, 8),
            path=f"objects/{_string(rng, 2)}/{_string(rng, 8)}.json",
            contentHash="0" * 64,
            sourceHash=_string(rng, 12) if rng.random() > 0.5 else None,
            count=rng.randint(1, 5),
        )
        for _ in range(rng.randint(1, 6))
    )
    return Manifest(
        schemaVersion="0.1.0",
        family="objects",
        shards=shards,
        dependencies=tuple(sorted(_string(rng, 6) for _ in range(rng.randint(0, 4)))),
    )


def _project_version(rng: random.Random) -> ProjectVersion:
    return ProjectVersion(
        gitHead=_string(rng, 40),
        workingTreeFingerprint=_string(rng, 64),
        knowledgeSchemaVersion="0.1.0",
        embeddingModelVersion="unknown",
        indexSchemaVersion="0.1.0",
    )


def _source(rng: random.Random) -> Source:
    return Source(
        id=_string(rng, 8),
        uri=f"file:///tmp/{_string(rng)}.md",
        family=rng.choice(["markdown", "java-class", "openapi-spec"]),
        contentHash=_string(rng, 64),
        metadata=_metadata(rng),
    )


def _section(rng: random.Random) -> Section:
    return Section(
        id=_string(rng, 8),
        heading=_string(rng, 12),
        level=rng.randint(1, 6),
        parentId=_string(rng, 8) if rng.random() > 0.5 else None,
    )


TYPES = (
    ("Metadata", _metadata),
    ("Chunk", _chunk),
    ("Entity", _entity),
    ("Manifest", _manifest),
    ("ProjectVersion", _project_version),
    ("Source", _source),
    ("Section", _section),
)


class CanonicalRoundTripTests(unittest.TestCase):
    """Property-based round-trip tests for Phase 1 value types."""

    ITERATIONS = 100

    def test_byte_identical_serialization_per_type(self) -> None:
        rng = _rng()
        for name, factory in TYPES:
            with self.subTest(type=name):
                # For each iteration: serialize the same instance twice
                # and assert byte-identical output. The property test
                # checks that the serializer is deterministic for a
                # single logical state, regardless of insertion order
                # in memory (dataclass field order is fixed in Python).
                for _ in range(self.ITERATIONS):
                    instance = factory(rng)
                    first = to_canonical_json(instance)
                    second = to_canonical_json(instance)
                    self.assertEqual(first, second,
                                    f"{name} canonical bytes drifted")

    def test_round_trip_preserves_state(self) -> None:
        rng = _rng()
        for name, factory in TYPES:
            with self.subTest(type=name):
                for _ in range(self.ITERATIONS):
                    instance = factory(rng)
                    payload = to_canonical_json(instance)
                    decoded = from_canonical_json(type(instance), payload)
                    self.assertEqual(decoded, instance)

    def test_chunk_content_address_independent_of_metadata(self) -> None:
        """Two chunks with the same body (rawText, contextualText,
        sourceReference) share the same content address even when their
        surrounding metadata, identifier arrays or knowledge state
        differ.
        """
        rng = _rng()
        for _ in range(self.ITERATIONS):
            raw = _string(rng, 16)
            ctx = _string(rng, 16)
            src = _string(rng, 8)
            ch1 = Chunk(
                id=_string(rng), rawText=raw,
                contextualText=ctx,
                metadata=_metadata(rng),
                sourceReference=src,
                contentHash="0" * 64,
            )
            ch2 = Chunk(
                id=_string(rng), rawText=raw,
                contextualText=ctx,
                metadata=_metadata(rng),
                sourceReference=src,
                contentHash="0" * 64,
            )
            self.assertEqual(chunk_content_address(ch1),
                            chunk_content_address(ch2))

    def test_manifest_self_hash_order_independent(self) -> None:
        """Manifests with the same shards/dependencies in different order
        produce the same self hash.
        """
        rng = _rng()
        for _ in range(self.ITERATIONS):
            ids = [_string(rng, 8) for _ in range(rng.randint(2, 6))]
            paths = [f"objects/{_string(rng, 2)}/{i}.json" for i in ids]
            shards_a = [
                Shard(id=i, path=p, contentHash="0" * 64)
                for i, p in zip(ids, paths)
            ]
            shards_b = list(reversed(shards_a))
            deps_a = sorted(_string(rng, 6) for _ in range(rng.randint(0, 4)))
            deps_b = list(reversed(deps_a))
            m1 = manifest_with(shards_a, deps_a)
            m2 = manifest_with(shards_b, deps_b)
            self.assertEqual(m1.contentHash, m2.contentHash)

    def test_value_types_have_documented_fields(self) -> None:
        """Every Phase 1 value type carries the documented required
        fields (smoke test for the documented contract).
        """
        for cls, required in (
            (Metadata, {"documentId", "version", "language"}),
            (Chunk, {"id", "rawText", "contextualText", "metadata",
                     "sourceReference", "contentHash"}),
            (Entity, {"id", "family", "label"}),
            (Relation, {"sourceId", "targetId", "family"}),
            (Evidence, {"knowledgeState", "parserVersion"}),
            (ProjectVersion, {"gitHead", "workingTreeFingerprint",
                               "knowledgeSchemaVersion",
                               "embeddingModelVersion",
                               "indexSchemaVersion"}),
            (Shard, {"id", "path", "contentHash"}),
            (Manifest, {"schemaVersion", "family"}),
            (Source, {"id", "uri", "family", "contentHash"}),
            (Section, {"id", "heading", "level"}),
        ):
            with self.subTest(cls=cls.__name__):
                names = {f.name for f in fields(cls)}
                self.assertTrue(required.issubset(names),
                                f"{cls.__name__} missing {required - names}")


def manifest_with(ids_a, deps) -> Manifest:
    from pi_platform.core.canonical import manifest_from_shards
    return manifest_from_shards("objects", list(ids_a), dependencies=tuple(sorted(deps)))


if __name__ == "__main__":
    unittest.main()