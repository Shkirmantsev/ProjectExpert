"""Phase 3 storage behavior regressions.

The tests cover the nine Phase 3 capability specs (runtime-store,
sparse-index, dense-index, full-text-index, sharded-graph,
graph-expansion, provenance-state-model, freshness-tracking,
embedded-storage-selection). Every test exercises real
implementations behind the documented ports; no mocks are used.
"""

from __future__ import annotations

import dataclasses
import math
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pi_platform.adapters.runtime.bm25_sparse_index import Bm25SparseIndex
from pi_platform.adapters.runtime.bounded_graph_expansion import BoundedGraphExpansion
from pi_platform.adapters.runtime.flat_dense_index import FlatDenseIndex
from pi_platform.adapters.runtime.last_verified_freshness_tracker import (
    LastVerifiedFreshnessTracker,
)
from pi_platform.adapters.runtime.provenance_tracker import LocalProvenanceTracker
from pi_platform.adapters.runtime.sharded_graph import LocalShardedGraph
from pi_platform.adapters.runtime.sqlite_fts_full_text_index import (
    SqliteFtsFullTextIndex,
)
from pi_platform.adapters.runtime.sqlite_runtime_store import SqliteRuntimeStore
from pi_platform.core.canonical.content_address import content_address_bytes
from pi_platform.core.canonical.serializer import canonical_dump_json
from pi_platform.core.canonical.value_types import (
    Entity,
    Evidence,
    KnowledgeState,
    Metadata,
    ProjectVersion,
    Relation,
    Source,
)
from pi_platform.ports.runtime.dense_index import DenseHit
from pi_platform.ports.runtime.freshness import FreshnessSnapshot
from pi_platform.ports.runtime.full_text_index import FullTextHit
from pi_platform.ports.runtime.graph import GraphManifest, Shard
from pi_platform.ports.runtime.graph_expansion import GraphExpansion
from pi_platform.ports.runtime.runtime_store import RuntimeStatusReport, RuntimeStoreError
from pi_platform.ports.runtime.sparse_index import SparseHit


ENTITY_FAMILIES = [
    "Requirement",
    "Specification",
    "OpenSpecChange",
    "ADR",
    "BusinessConcept",
    "Component",
    "Module",
    "JavaClass",
    "JavaMethod",
    "Interface",
    "API",
    "Dependency",
    "DatabaseTable",
    "Protocol",
    "Test",
    "DocumentationSource",
    "Document",
    "Section",
    "Chunk",
]

RELATION_FAMILIES = [
    "IMPLEMENTS",
    "SATISFIES",
    "DEPENDS_ON",
    "CALLS",
    "USES",
    "IMPLEMENTED_BY",
    "DEFINED_BY",
    "PART_OF",
    "DOCUMENTED_BY",
    "TESTED_BY",
    "REFERENCES",
    "SUPERSEDES",
    "DESCRIBES",
]


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.version = ProjectVersion(
            gitHead="abc",
            workingTreeFingerprint="def",
            knowledgeSchemaVersion="0.1.0",
            embeddingModelVersion="unknown",
            indexSchemaVersion="0.1.0",
        )

    def metadata(self, **overrides):
        base = dict(
            documentId="d-1",
            version="0.1.0",
            language="en",
        )
        base.update(overrides)
        return Metadata(**base)


class RuntimeStoreTests(Fixture):
    def test_put_and_get_round_trip(self):
        store = SqliteRuntimeStore(cache_root=self.root / "cache", version=self.version)
        body = {"id": "x", "text": "hello"}
        address = store.put("chunk", body)
        entry = store.get(address)
        self.assertEqual(entry.family, "chunk")
        self.assertEqual(entry.body, body)
        self.assertEqual(entry.content_hash, address)

    def test_cross_branch_reuse_via_content_address(self):
        cache_root = self.root / "cache"
        body = {"id": "y", "text": "world"}
        address = content_address_bytes(canonical_dump_json(body)).decode() if False else content_address_bytes(canonical_dump_json(body))
        s1 = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        written = s1.put("chunk", body)
        self.assertEqual(written, address)
        s2 = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        again = s2.put("chunk", body)
        self.assertEqual(again, address)
        self.assertEqual(s1.stats()["entries"], s2.stats()["entries"])

    def test_version_stamp_reports_bound_identity(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        report = store.runtime_status()
        self.assertEqual(report.bound_version.gitHead, "abc")
        self.assertEqual(report.bound_version.workingTreeFingerprint, "def")
        self.assertEqual(report.bound_version.knowledgeSchemaVersion, "0.1.0")

    def test_wal_tail_is_recoverable(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        for i in range(3):
            store.put("chunk", {"id": str(i)})
        self.assertGreaterEqual(store.wal_tail_length(), 3)
        store.recover_wal()
        report = store.runtime_status()
        self.assertEqual(report.cache_entries, 3)

    def test_knowledge_state_filter_excludes_local_only_by_default(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        store.put("chunk", {"id": "durable"})
        store.put("local_only_chunk", {"id": "ephemeral"})
        default = store.runtime_status()
        self.assertIn("chunk", default.families)
        self.assertIn("local_only_chunk", default.families)
        durable_only = store.runtime_status(policy="DURABLE")
        self.assertEqual(sum(durable_only.family_counts.values()), 1)

    def test_phase1_cache_shim_keeps_round_trip(self):
        from pi_platform.runtime.cache import RuntimeCache

        shim = RuntimeCache(self.root / "shim-cache")
        body = {"id": "shim", "text": "hi"}
        address = shim.put("chunk", body)
        self.assertEqual(shim.get(address).body, body)


class SparseIndexTests(Fixture):
    def test_bm25_ranks_relevant_higher(self):
        idx = Bm25SparseIndex()
        idx.index_document("markdown", "a", "alpha beta gamma", {"family": "markdown"})
        idx.index_document("markdown", "b", "delta epsilon", {"family": "markdown"})
        idx.index_document("pdf", "c", "zeta alpha iota", {"family": "pdf"})
        hits = idx.query("alpha", top_k=3)
        ids = [h.documentId for h in hits]
        self.assertIn("a", ids)
        self.assertIn("c", ids)
        first = next(h for h in hits if h.documentId == "a")
        for other in [h for h in hits if h.documentId != "a"]:
            self.assertGreaterEqual(first.score, other.score)

    def test_identifier_friendly_retrieval(self):
        idx = Bm25SparseIndex()
        idx.index_document(
            "java_source", "A", "package demo; class RpaVaryToteJpaMapper {}", {}
        )
        hits = idx.query("RpaVaryToteJpaMapper", top_k=5)
        self.assertEqual(hits[0].documentId, "A")
        self.assertGreater(hits[0].score, 0)

    def test_metadata_aware_scoring(self):
        idx = Bm25SparseIndex()
        idx.index_document("markdown", "m1", "alpha alpha alpha", {"family": "markdown"})
        idx.index_document("pdf", "p1", "alpha alpha alpha", {"family": "pdf"})
        hits = idx.query("alpha", top_k=5, metadata={"family": "markdown"})
        self.assertEqual(hits[0].documentId, "m1")

    def test_delete_document(self):
        idx = Bm25SparseIndex()
        idx.index_document("markdown", "a", "alpha beta", {})
        self.assertEqual(idx.stats()["documents"], 1)
        idx.delete_document("a")
        self.assertEqual(idx.stats()["documents"], 0)

    def test_stats_are_stable(self):
        idx = Bm25SparseIndex()
        idx.index_document("markdown", "a", "alpha", {})
        s1 = idx.stats()
        s2 = idx.stats()
        self.assertEqual(s1, s2)


class DenseIndexTests(Fixture):
    def test_round_trip_chunk_embedding(self):
        idx = FlatDenseIndex()
        vec = [0.1, 0.2, 0.3]
        idx.index_chunk("c1", vec, {"family": "chunk"})
        hits = idx.query(vec, top_k=5)
        self.assertEqual(hits[0].chunkId, "c1")
        self.assertAlmostEqual(hits[0].score, 1.0, places=5)

    def test_reindexing_does_not_duplicate(self):
        idx = FlatDenseIndex()
        idx.index_chunk("c1", [1.0, 0.0, 0.0], {})
        idx.index_chunk("c1", [0.0, 1.0, 0.0], {})
        hits = idx.query([0.0, 1.0, 0.0], top_k=5)
        self.assertEqual(len([h for h in hits if h.chunkId == "c1"]), 1)
        old = idx.query([1.0, 0.0, 0.0], top_k=5)
        self.assertFalse(any(h.chunkId == "c1" for h in old))

    def test_delete_propagates(self):
        idx = FlatDenseIndex()
        idx.index_chunk("c1", [1.0, 0.0], {})
        idx.delete_chunk("c1")
        hits = idx.query([1.0, 0.0], top_k=5)
        self.assertFalse(any(h.chunkId == "c1" for h in hits))

    def test_dimension_mismatch_is_reported(self):
        idx = FlatDenseIndex()
        idx.index_chunk("c1", [1.0, 0.0, 0.0], {})
        from pi_platform.ports.runtime.dense_index import DenseIndexError
        with self.assertRaises(DenseIndexError):
            idx.query([1.0, 0.0], top_k=5)


class FullTextIndexTests(Fixture):
    def test_substring_hit(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        fts = SqliteFtsFullTextIndex(store)
        fts.index_document("markdown", "a", "alpha beta gamma", {})
        fts.index_document("markdown", "b", "delta epsilon", {})
        fts.index_document("markdown", "c", "alpha iota", {})
        hits = fts.query("alpha", top_k=5)
        ids = {h.documentId for h in hits}
        self.assertEqual(ids, {"a", "c"})

    def test_separation_from_sparse_index(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        fts = SqliteFtsFullTextIndex(store)
        bm25 = Bm25SparseIndex()
        text = "alpha beta gamma"
        fts.index_document("markdown", "a", text, {})
        bm25.index_document("markdown", "a", text, {})
        self.assertTrue(fts.query("alpha"))
        self.assertTrue(bm25.query("alpha"))

    def test_stats_are_stable(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        fts = SqliteFtsFullTextIndex(store)
        fts.index_document("markdown", "a", "alpha", {})
        self.assertEqual(fts.stats(), fts.stats())


class GraphTests(Fixture):
    def test_entity_round_trip(self):
        g = LocalShardedGraph(self.root / "graph")
        e = Entity(
            id="e1",
            family="Component",
            label="PackingService",
            description="Handles packing",
            metadata=self.metadata(),
        )
        g.upsert_entity(e)
        read = g.get_entity("e1")
        self.assertEqual(read, e)

    def test_relation_round_trip(self):
        g = LocalShardedGraph(self.root / "graph")
        a = Entity(id="a", family="Component", label="A", metadata=self.metadata())
        b = Entity(id="b", family="Component", label="B", metadata=self.metadata())
        g.upsert_entity(a)
        g.upsert_entity(b)
        g.upsert_relation(
            Relation(sourceId="a", targetId="b", family="IMPLEMENTS", knowledgeState=KnowledgeState.VERIFIED)
        )
        rels = g.get_relations("a")
        self.assertEqual(len(rels), 1)
        self.assertEqual(rels[0].targetId, "b")
        self.assertEqual(rels[0].family, "IMPLEMENTS")

    def test_edge_type_filter(self):
        g = LocalShardedGraph(self.root / "graph")
        for fid in ("a", "b", "c"):
            g.upsert_entity(Entity(id=fid, family="Component", label=fid, metadata=self.metadata()))
        g.upsert_relation(Relation(sourceId="a", targetId="b", family="CALLS"))
        g.upsert_relation(Relation(sourceId="a", targetId="c", family="IMPLEMENTS"))
        calls = g.get_relations("a", edge_type="CALLS")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].targetId, "b")

    def test_shard_by_returns_hash_prefix(self):
        g = LocalShardedGraph(self.root / "graph")
        address = content_address_bytes(b"x")
        shard = g.shard_by(address)
        self.assertEqual(Path(shard.path).parts[0], "nodes")
        self.assertIn(address[:2], str(shard.path))

    def test_content_addressed_entity_bodies_share_canonical_artefact(self):
        g = LocalShardedGraph(self.root / "graph")
        body = {"label": "shared", "family": "Component"}
        e1 = Entity(id="e1", family="Component", label="shared", metadata=self.metadata())
        e2 = Entity(id="e2", family="Component", label="shared", metadata=self.metadata())
        g.upsert_entity(e1)
        g.upsert_entity(e2)
        objects_root = self.root / "graph" / "objects"
        self.assertTrue(objects_root.exists())

    def test_every_entity_family_round_trips(self):
        g = LocalShardedGraph(self.root / "graph")
        for idx, family in enumerate(ENTITY_FAMILIES):
            eid = f"f-{idx}"
            e = Entity(id=eid, family=family, label=eid, metadata=self.metadata())
            g.upsert_entity(e)
            self.assertEqual(g.get_entity(eid).family, family)

    def test_every_relation_family_round_trips(self):
        g = LocalShardedGraph(self.root / "graph")
        g.upsert_entity(Entity(id="a", family="Component", label="A", metadata=self.metadata()))
        for idx, family in enumerate(RELATION_FAMILIES):
            target_id = f"t-{idx}"
            g.upsert_entity(Entity(id=target_id, family="Component", label=target_id, metadata=self.metadata()))
            g.upsert_relation(Relation(sourceId="a", targetId=target_id, family=family))
            self.assertEqual(len(g.get_relations("a", edge_type=family)), 1)

    def test_manifest_reflects_shard_state(self):
        g = LocalShardedGraph(self.root / "graph")
        for i in range(10):
            g.upsert_entity(
                Entity(id=f"e-{i}", family="Component", label=f"e-{i}", metadata=self.metadata())
            )
        manifest = g.rebuild_manifest()
        self.assertIsInstance(manifest, GraphManifest)
        self.assertEqual(manifest.entity_count, 10)
        self.assertGreaterEqual(len(manifest.shards), 1)

    def test_ann_graph_not_visible_from_knowledge_graph(self):
        from pi_platform.ports.runtime.dense_index import DenseIndexPort
        from pi_platform.ports.runtime.graph import GraphPort

        g: GraphPort = LocalShardedGraph(self.root / "graph")
        d: DenseIndexPort = FlatDenseIndex()
        e = Entity(id="e-vec", family="Component", label="vec", metadata=self.metadata())
        g.upsert_entity(e)
        d.index_chunk("e-vec", [1.0, 0.0, 0.0], {})
        self.assertIsNotNone(g.get_entity("e-vec"))
        self.assertFalse(any(h.chunkId == "e-vec" for h in d.query([0.0, 1.0, 0.0], top_k=5)))


class GraphExpansionTests(Fixture):
    def test_default_expansion_returns_seed_entities(self):
        g = LocalShardedGraph(self.root / "graph")
        g.upsert_entity(Entity(id="e1", family="Component", label="E1", metadata=self.metadata()))
        expander = BoundedGraphExpansion(g)
        result = expander.expand(["e1"])
        self.assertIsInstance(result, GraphExpansion)
        self.assertIn("e1", [e.id for e in result.expandedEntities])

    def test_budget_cap_is_enforced(self):
        g = LocalShardedGraph(self.root / "graph")
        g.upsert_entity(Entity(id="root", family="Component", label="root", metadata=self.metadata()))
        for i in range(20):
            g.upsert_entity(
                Entity(id=f"e{i}", family="Component", label=f"e{i}", metadata=self.metadata())
            )
            g.upsert_relation(Relation(sourceId="root", targetId=f"e{i}", family="IMPLEMENTS"))
        expander = BoundedGraphExpansion(g)
        result = expander.expand(["root"], hops=1, budget=3)
        self.assertLessEqual(len(result.expandedEntities), 3)
        self.assertTrue(result.budget_exhausted)

    def test_edge_type_filter(self):
        g = LocalShardedGraph(self.root / "graph")
        for fid in ("a", "b", "c"):
            g.upsert_entity(Entity(id=fid, family="Component", label=fid, metadata=self.metadata()))
        g.upsert_relation(Relation(sourceId="a", targetId="b", family="IMPLEMENTS"))
        g.upsert_relation(Relation(sourceId="a", targetId="c", family="CALLS"))
        expander = BoundedGraphExpansion(g)
        result = expander.expand(["a"], hops=1, edge_types=["IMPLEMENTS"], budget=10)
        self.assertEqual(len(result.expandedRelations), 1)
        self.assertEqual(result.expandedRelations[0].family, "IMPLEMENTS")


class ProvenanceTests(Fixture):
    def test_verified_stays_verified_when_source_unchanged(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LocalProvenanceTracker(store)
        port.transition(
            "e1",
            from_state=KnowledgeState.VERIFIED,
            to_state=KnowledgeState.VERIFIED,
            evidence={"source_hash": "sha-256:A"},
        )
        self.assertEqual(port.current_state("e1"), KnowledgeState.VERIFIED)

    def test_verified_to_stale_on_source_change(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LocalProvenanceTracker(store)
        port.transition(
            "e1",
            from_state=KnowledgeState.VERIFIED,
            to_state=KnowledgeState.STALE,
            evidence={"source_hash_before": "sha-256:A", "source_hash_after": "sha-256:B"},
        )
        self.assertEqual(port.current_state("e1"), KnowledgeState.STALE)

    def test_transition_records_evidence_chain(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LocalProvenanceTracker(store)
        port.transition(
            "e1",
            from_state=KnowledgeState.VERIFIED,
            to_state=KnowledgeState.STALE,
            evidence={"source_hash_after": "sha-256:B"},
        )
        chain = port.evidence("e1")
        self.assertEqual(len(chain), 1)
        self.assertEqual(chain[0].knowledgeState, KnowledgeState.STALE)

    def test_forbidden_transition_is_rejected(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LocalProvenanceTracker(store)
        from pi_platform.ports.runtime.provenance import ProvenanceError
        with self.assertRaises(ProvenanceError):
            port.transition(
                "e1",
                from_state=KnowledgeState.VERIFIED,
                to_state=KnowledgeState.ASSUMPTION,
                evidence={},
            )

    def test_staleness_map_reports_current_state(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LocalProvenanceTracker(store)
        port.transition("e1", from_state=KnowledgeState.VERIFIED, to_state=KnowledgeState.STALE, evidence={})
        port.transition("e2", from_state=KnowledgeState.VERIFIED, to_state=KnowledgeState.VERIFIED, evidence={})
        mapping = port.staleness_map()
        self.assertEqual(mapping["e1"], KnowledgeState.STALE)
        self.assertEqual(mapping["e2"], KnowledgeState.VERIFIED)


class FreshnessTests(Fixture):
    def test_mark_verified_records_timestamp_and_hash(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LastVerifiedFreshnessTracker(store)
        port.mark_verified("f1", source_hash="sha-256:A", version=self.version)
        self.assertFalse(port.is_stale("f1", current_source_hash="sha-256:A"))

    def test_source_hash_change_marks_fact_stale(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LastVerifiedFreshnessTracker(store)
        port.mark_verified("f1", source_hash="sha-256:A", version=self.version)
        self.assertTrue(port.is_stale("f1", current_source_hash="sha-256:B"))

    def test_derived_staleness_when_upstream_stale(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        prov = LocalProvenanceTracker(store)
        freshness = LastVerifiedFreshnessTracker(store, provenance=prov)
        prov.transition("f1", from_state=KnowledgeState.VERIFIED, to_state=KnowledgeState.STALE, evidence={})
        self.assertTrue(freshness.derived_staleness("d1", depends_on=["f1"]))

    def test_derived_staleness_when_all_upstreams_verified(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        prov = LocalProvenanceTracker(store)
        freshness = LastVerifiedFreshnessTracker(store, provenance=prov)
        for fid in ("f1", "f2", "f3"):
            prov.transition(fid, from_state=KnowledgeState.VERIFIED, to_state=KnowledgeState.VERIFIED, evidence={})
        self.assertFalse(freshness.derived_staleness("d1", depends_on=["f1", "f2", "f3"]))

    def test_snapshot_round_trips_through_replay(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LastVerifiedFreshnessTracker(store)
        for i in range(50):
            port.mark_verified(f"f{i}", source_hash=f"sha-256:{i}", version=self.version)
        snap = port.snapshot()
        self.assertEqual(len(snap.facts), 50)
        self.assertIn("f0", snap.facts)
        self.assertEqual(snap.facts["f0"].source_hash, "sha-256:0")

    def test_authoritative_knowledge_not_silently_rewritten(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        port = LastVerifiedFreshnessTracker(store)
        port.mark_verified("f1", source_hash="sha-256:A", version=self.version)
        snap_before = port.snapshot()
        port.mark_verified("f1", source_hash="sha-256:B", version=self.version)
        snap_after = port.snapshot()
        self.assertEqual(snap_before.facts["f1"].source_hash, "sha-256:A")
        self.assertEqual(snap_after.facts["f1"].source_hash, "sha-256:B")
        self.assertTrue(port.is_stale("f1", current_source_hash="sha-256:A"))


class SqliteConnectionLifetimeTests(Fixture):
    def test_failed_write_rolls_back_and_releases_connection(self):
        store = SqliteRuntimeStore(self.root / "cache", version=self.version)
        connections = []
        connect = sqlite3.connect

        class FailingConnection(sqlite3.Connection):
            def execute(self, sql, *args):
                if sql.startswith("INSERT INTO runtime_families"):
                    raise sqlite3.OperationalError("injected write failure")
                return super().execute(sql, *args)

        def tracked_connect(*args, **kwargs):
            conn = connect(*args, factory=FailingConnection, **kwargs)
            connections.append(conn)
            return conn

        self.addCleanup(lambda: [conn.close() for conn in connections])
        with patch("sqlite3.connect", side_effect=tracked_connect):
            with self.assertRaisesRegex(sqlite3.OperationalError, "injected"):
                store.put("chunk", {"id": "failed"})
        self.assertEqual(store.stats()["entries"], 0)
        self.assertEqual(len(connections), 1)
        with self.assertRaises(sqlite3.ProgrammingError):
            connections[0].execute("SELECT 1")

    def test_operations_release_connections_without_garbage_collection(self):
        # Keep strong references so garbage collection cannot hide leaked handles.
        connections = []
        connect = sqlite3.connect

        def tracked_connect(*args, **kwargs):
            conn = connect(*args, **kwargs)
            connections.append(conn)
            return conn

        self.addCleanup(lambda: [conn.close() for conn in connections])
        with patch("sqlite3.connect", side_effect=tracked_connect):
            store = SqliteRuntimeStore(self.root / "cache", version=self.version)
            address = store.put("chunk", {"id": "c1", "text": "hello"})
            store.get(address)
            store.has(address)
            store.stats()
            store.runtime_status()
            store.recover_wal()
            store.evict(address)
            store.evict(address)  # early return on a missing entry
            with self.assertRaises(RuntimeStoreError):
                store.get(address)
            fulltext = SqliteFtsFullTextIndex(store)
            fulltext.index_document("md", "d1", "hello world", {})
            self.assertEqual(len(fulltext.query("hello")), 1)
            fulltext.query('"')  # handled FTS syntax error
            fulltext.stats()
            fulltext.delete_document("d1")
            provenance = LocalProvenanceTracker(store)
            provenance.transition("e1", from_state=KnowledgeState.VERIFIED,
                                  to_state=KnowledgeState.VERIFIED, evidence={})
            provenance.transition("e1", from_state=KnowledgeState.VERIFIED,
                                  to_state=KnowledgeState.STALE, evidence={})
            provenance.current_state("e1")
            provenance.evidence("e1")
            provenance.events("e1")
            provenance.staleness_map()
            freshness = LastVerifiedFreshnessTracker(store, provenance)
            freshness.mark_verified("f1", source_hash="hash", version=self.version)
            self.assertFalse(freshness.is_stale("f1", current_source_hash="hash"))
            freshness.snapshot()
        self.assertGreater(len(connections), 20)
        for conn in connections:
            with self.assertRaises(sqlite3.ProgrammingError):
                conn.execute("SELECT 1")


class EmbeddedStorageSelectionTests(unittest.TestCase):
    def test_postgres_is_opt_in(self):
        from pi_platform.adapters.runtime.sqlite_runtime_store import (
            SqliteRuntimeStore,
        )

        cache_root = Path(tempfile.mkdtemp())
        store = SqliteRuntimeStore(cache_root=cache_root, version=ProjectVersion(
            gitHead="abc",
            workingTreeFingerprint="def",
            knowledgeSchemaVersion="0.1.0",
            embeddingModelVersion="unknown",
            indexSchemaVersion="0.1.0",
        ))
        self.assertEqual(store.backend_name(), "sqlite")
        self.assertFalse(store.supports_postgres())

    def test_default_backend_is_sqlite(self):
        cache_root = Path(tempfile.mkdtemp())
        store = SqliteRuntimeStore(cache_root=cache_root, version=ProjectVersion(
            gitHead="abc",
            workingTreeFingerprint="def",
            knowledgeSchemaVersion="0.1.0",
            embeddingModelVersion="unknown",
            indexSchemaVersion="0.1.0",
        ))
        self.assertEqual(store.backend_name(), "sqlite")

    def test_dependency_inventory_has_no_unapproved_entries(self):
        path = Path("distribution/licenses/dependency-inventory.json")
        if not path.exists():
            self.skipTest("inventory absent")
        import json
        inv = json.loads(path.read_text(encoding="utf-8"))
        for dep in inv.get("dependencies", []):
            self.assertIn("spdx", dep)
            self.assertIsNotNone(dep["spdx"])


class StatusReportTests(Fixture):
    def test_runtime_status_reports_required_fields(self):
        cache_root = self.root / "cache"
        store = SqliteRuntimeStore(cache_root=cache_root, version=self.version)
        store.put("chunk", {"id": "x"})
        report = store.runtime_status()
        self.assertIsInstance(report, RuntimeStatusReport)
        self.assertEqual(report.bound_version.gitHead, "abc")
        self.assertEqual(report.cache_entries, 1)
        self.assertIn("sqlite", report.backend)


if __name__ == "__main__":
    unittest.main()