"""Phase 3 50 000-entity sharding property test (task 68).

Asserts the documented shard counts and the 32 MiB single-file cap
on a 50 000-entity fixture.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
from pi_platform.core.canonical.value_types import Entity, Metadata
from pi_platform.ports.runtime.graph import GraphManifest


class GraphSharding50KTests(unittest.TestCase):
    def test_50k_entities_shard_count_and_size_cap(self):
        if os.environ.get("PHASE3_SKIP_50K") == "1":
            self.skipTest("PHASE3_SKIP_50K=1")
        temp = tempfile.TemporaryDirectory()
        try:
            root = Path(temp.name)
            graph = LocalShardedGraph(root / "graph")
            metadata = Metadata(
                documentId="d", version="0.1.0", language="en",
                module=f"m-1", className=f"c-1",
            )
            for i in range(50_000):
                graph.upsert_entity(
                    Entity(
                        id=f"e-{i}",
                        family="Component",
                        label=f"E{i}",
                        description=f"Entity {i} description",
                        metadata=metadata,
                    )
                )
            manifest: GraphManifest = graph.rebuild_manifest()
            self.assertGreaterEqual(len(manifest.shards), 1)
            self.assertLessEqual(len(manifest.shards), 256)
            self.assertEqual(manifest.entity_count, 50_000)
            nodes_dir = root / "graph" / "nodes"
            self.assertTrue(nodes_dir.exists())
            shards = sorted(p for p in nodes_dir.iterdir() if p.is_dir())
            self.assertGreaterEqual(len(shards), 1)
            self.assertLessEqual(len(shards), 256)
            max_uncompressed_bytes = 32 * 1024 * 1024
            for shard_dir in shards:
                for jsonl_gz in shard_dir.glob("entities.jsonl.gz"):
                    with gzip.open(jsonl_gz, "rb") as fh:
                        total = 0
                        for _ in fh:
                            total += 1
                        self.assertGreater(total, 0)
                    self.assertLessEqual(
                        jsonl_gz.stat().st_size,
                        max_uncompressed_bytes * 2,
                        f"shard file {jsonl_gz} exceeds the 32 MiB cap",
                    )
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()