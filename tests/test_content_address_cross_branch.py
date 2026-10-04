"""Seeded property checks for content reuse with independent branch contexts."""

import dataclasses
import random
import string
import unittest
from pi_platform.core.canonical.value_types import (
    Chunk,
    Entity,
    Relation,
    Metadata,
    Evidence,
    KnowledgeState,
    to_canonical_json,
)
from pi_platform.core.canonical.content_address import (
    content_address,
    content_address_bytes,
    chunk_content_address,
)
from pi_platform.core.canonical.serializer import canonical_dump_json
from pi_platform.core.ingest.runtime_cache import InMemoryRuntimeCache


class ContentAddressCrossBranchTests(unittest.TestCase):
    def test_100_random_instances_per_type(self):
        for seed in range(100):
            rng = random.Random(seed)
            text = "".join(rng.choice(string.ascii_letters + "é\n") for _ in range(200))
            pairs = [("a", text), ("b", seed), ("c", {"x": seed, "y": text})]
            rng.shuffle(pairs)
            left = dict(pairs)
            rng.shuffle(pairs)
            right = dict(pairs)
            self.assertEqual(content_address(left), content_address(right))
            meta = Metadata("doc", "1", "text", extensions=left)
            chunk = Chunk(
                f"c-{seed}",
                text,
                text,
                meta,
                "source",
                content_address(text),
                parentId="section",
            )
            entity = Entity(
                f"e-{seed}",
                "concept",
                text,
                metadata=meta,
                knowledgeState=KnowledgeState.VERIFIED,
            )
            relation = Relation(
                f"a-{seed}",
                f"b-{seed}",
                "PART_OF",
                evidence=(Evidence(KnowledgeState.VERIFIED, "1"),),
            )
            for value in (chunk, entity, relation):
                with self.subTest(seed=seed, type=type(value).__name__):
                    other = (
                        dataclasses.replace(
                            value, metadata=dataclasses.replace(meta, extensions=right)
                        )
                        if hasattr(value, "metadata")
                        else dataclasses.replace(value)
                    )
                    address = (
                        chunk_content_address(value)
                        if isinstance(value, Chunk)
                        else content_address_bytes(to_canonical_json(value))
                    )
                    address2 = (
                        chunk_content_address(other)
                        if isinstance(other, Chunk)
                        else content_address_bytes(to_canonical_json(other))
                    )
                    self.assertEqual(address, address2)
                    cache = InMemoryRuntimeCache()
                    cache.put(address, to_canonical_json(value))
                    self.assertIsNotNone(cache.get(address2))
                    self.assertEqual(cache.hits(), 1)
                    self.assertEqual(len(cache), 1)
            altered = dataclasses.replace(
                chunk, metadata=Metadata("different", "2", "text"), parentId="different"
            )
            self.assertEqual(
                chunk_content_address(chunk), chunk_content_address(altered)
            )
            self.assertNotEqual(
                chunk_content_address(chunk),
                chunk_content_address(dataclasses.replace(chunk, rawText=text + "x")),
            )
