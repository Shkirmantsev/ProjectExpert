"""Phase 3 50 000-entity sharding property test (task 68).

Asserts the documented shard counts and the 8 MiB single-file cap
on a 50 000-entity fixture.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
from pi_platform.adapters.runtime.candidate_artifacts import build_graph_shards
from pi_platform.core.canonical.value_types import Entity, Metadata
from pi_platform.ports.runtime.graph import GraphManifest


class GraphSharding50KTests(unittest.TestCase):
    def test_50k_entities_shard_count_and_size_cap(self):
        if os.environ.get("PHASE3_SKIP_50K") == "1":
            self.skipTest("PHASE3_SKIP_50K=1")
        temp = tempfile.TemporaryDirectory()
        started = time.monotonic()
        try:
            root = Path(temp.name).resolve()
            graph = LocalShardedGraph(root / "graph")
            metadata = Metadata(
                documentId="d", version="0.1.0", language="en",
                module=f"m-1", className=f"c-1",
            )
            native_replace = os.replace
            replacements = 0
            def bounded_replace(source, target):
                nonlocal replacements
                replacements += 1
                if replacements > 4 * graph.SHARDS_PER_PREFIX:
                    self.fail('Scale construction must write per shard, not per entity')
                return native_replace(source, target)
            # Exercise the actual production bulk builder. Single-entity
            # mutation/atomicity remains covered by the small GraphPort tests.
            entities = tuple(Entity(
                id=f"e-{i}", family="Component", label=f"E{i}",
                description=f"Entity {i} description", metadata=metadata,
            ) for i in range(50_000))
            with patch('os.replace', side_effect=bounded_replace):
                build_graph_shards(graph, entities, ())
            print(f'\n50k graph: bulk built 50000 entities with {replacements} '
                  f'atomic replacements ({time.monotonic() - started:.1f}s)',
                  file=sys.stderr, flush=True)
            manifest: GraphManifest = graph.rebuild_manifest()
            self.assertGreaterEqual(len(manifest.shards), 1)
            self.assertLessEqual(len(manifest.shards), 256)
            self.assertEqual(manifest.entity_count, 50_000)
            nodes_dir = graph.root / "nodes"
            self.assertTrue(nodes_dir.exists())
            shards = sorted(p for p in nodes_dir.iterdir() if p.is_dir())
            self.assertGreaterEqual(len(shards), 1)
            self.assertLessEqual(len(shards), 256)
            max_uncompressed_bytes = 8 * 1024 * 1024
            files = sorted(nodes_dir.glob("*/shard.jsonl"))
            self.assertEqual(len(files), len(manifest.shards))
            actual_count = 0
            import hashlib
            for path in files:
                with path.open("rb") as handle:
                    actual_count += sum(1 for _ in handle)
                self.assertLessEqual(path.stat().st_size, max_uncompressed_bytes)
                shard = next(s for s in manifest.shards if s.path == path.relative_to(graph.root).as_posix())
                self.assertEqual(shard.contentHash, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(actual_count, 50_000)
            for i in (0, 24_999, 49_999):
                self.assertEqual(graph.get_entity(f"e-{i}"), entities[i])
        finally:
            print('\n50k graph: removing temporary production graph',
                  file=sys.stderr, flush=True)
            temp.cleanup()
            print(f'50k graph: cleanup finished ({time.monotonic() - started:.1f}s total)',
                  file=sys.stderr, flush=True)


if __name__ == "__main__":
    unittest.main()
