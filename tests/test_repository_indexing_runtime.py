"""Runtime proof for ingestion, vector reuse, removal and shared retrieval."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.core.control.retrieval_settings import RetrievalSettings
from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery
from pi_platform.core.orchestration.repository_indexing import index_repository
from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery


class RepositoryIndexingRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.cache = self.root / '.project-intelligence-cache'
        self.env = patch.dict(os.environ, {
            'PI_STARTUP_PROFILE': 'minimal', 'PI_EMBEDDING_MODEL': 'hashing',
            'PI_DENSE_INDEX': 'flat', 'PI_DOCLING_ENABLED': '0',
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.discovery = RepositorySourceDiscovery()

    def build(self):
        return index_repository(target=self.root, cache_root=self.cache,
                                inventory=self.discovery.discover(self.root),
                                previous_inventory=None, settings=RetrievalSettings())

    def test_image_pixels_reach_encoder_and_changed_bytes_invalidate_vectors(self):
        import math
        from unittest.mock import Mock
        from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import EmbeddingGemma2EmbeddingModel
        class Row(list):
            def tolist(self): return list(self)
        adapter = EmbeddingGemma2EmbeddingModel()
        encoder = Mock()
        encoder.encode.side_effect = lambda texts, **kw: [Row([1/math.sqrt(512)]*512) for _ in texts]
        adapter._model = encoder
        image = self.root / 'diagram.png'
        image.write_bytes(b'pixels version one')
        with patch.dict(os.environ, {'PI_STARTUP_PROFILE':'minimal', 'PI_EMBEDDING_MODEL':'gemma'}), patch(
                'pi_platform.core.orchestration.retrieval_composition.EmbeddingModelFactory.build', return_value=adapter):
            first = self.build()
            self.assertEqual(first.extra['indexing_report'].embedded_count, 1)
            self.assertTrue(any(isinstance(call.args[0][0], dict) and call.args[0][0].get('image') == str(image)
                                for call in encoder.encode.call_args_list))
            self.assertEqual(self.build().extra['indexing_report'].reused_count, 1)
            image.write_bytes(b'pixels version two')
            self.assertEqual(self.build().extra['indexing_report'].embedded_count, 1)

    def test_restart_reuses_vectors_and_removed_source_is_not_searchable(self):
        source = self.root / 'billing.md'
        source.write_text('# Billing\nrefund customer payment safely\n')
        first = self.build()
        self.assertGreater(first.extra['indexing_report'].embedded_count, 0)
        self.assertTrue(first.multi_stage_retrieval.retrieve(RetrievalQuery(text='refund customer')).hits)
        second = self.build()
        self.assertEqual(second.extra['indexing_report'].embedded_count, 0)
        self.assertEqual(second.extra['indexing_report'].reused_count, len(second.extra['chunk_ids']))
        old_ids = set(second.extra['chunk_ids'])
        source.unlink()
        (self.root / 'shipping.md').write_text('# Shipping\nparcel dispatch tracking\n')
        third = self.build()
        self.assertFalse(old_ids.intersection(third.extra['chunk_ids']))
        self.assertFalse(old_ids.intersection(h.chunkId for h in third.multi_stage_retrieval.retrieve(RetrievalQuery(text='refund')).hits))
        self.assertTrue(third.multi_stage_retrieval.retrieve(RetrievalQuery(text='parcel dispatch')).hits)
        with __import__('sqlite3').connect(self.cache / 'indexes/embeddings.sqlite') as db:
            self.assertGreater(db.execute('SELECT count(*) FROM embeddings').fetchone()[0], 0)

    def test_graph_edge_changes_publish_new_graph_without_old_entities(self):
        from pi_platform.core.canonical.value_types import Entity, Relation
        from pi_platform.core.canonical.value_types import to_canonical_json
        graph = self.root / 'project-knowledge/graph'
        (graph / 'nodes/aa').mkdir(parents=True)
        (graph / 'edges/aa').mkdir(parents=True)
        nodes = graph / 'nodes/aa/shard.jsonl'
        edges = graph / 'edges/aa/shard.jsonl'
        nodes.write_bytes(to_canonical_json(Entity('a', 'Component', 'Billing')) + to_canonical_json(Entity('b', 'Component', 'Ledger')))
        edges.write_bytes(to_canonical_json(Relation('a', 'b', 'DEPENDS_ON')))
        first = self.build()
        result = first.graph_expansion.expand(['a'], hops=1, edge_types=None, budget=10)
        self.assertEqual({e.id for e in result.expandedEntities}, {'a', 'b'})
        self.assertEqual(set(first.extra['graph_node_ids']), {'a', 'b'})
        nodes.write_bytes(to_canonical_json(Entity('a', 'Component', 'Billing')))
        edges.write_text('')
        # A previous branch's unscoped runtime rows are historical cache only.
        with __import__('sqlite3').connect(self.cache / 'runtime.db') as db:
            db.execute('CREATE TABLE runtime_entries(body_json TEXT)')
            db.execute('INSERT INTO runtime_entries VALUES (?)',
                       (to_canonical_json(Entity('b', 'Component', 'Old ledger')).decode(),))
            db.execute('INSERT INTO runtime_entries VALUES (?)',
                       (to_canonical_json(Entity('a', 'Component', 'Old billing')).decode(),))
        second = self.build()
        result = second.graph_expansion.expand(['a'], hops=1, edge_types=None, budget=10)
        self.assertEqual({e.id for e in result.expandedEntities}, {'a'})
        self.assertEqual(result.expandedRelations, ())
        self.assertEqual(next(e.label for e in result.expandedEntities if e.id == 'a'), 'Billing')
        self.assertFalse((graph / 'objects').exists())

    def test_empty_repository_is_a_valid_empty_generation(self):
        runtime = self.build()
        self.assertEqual(runtime.extra['chunk_ids'], ())
        self.assertEqual(runtime.multi_stage_retrieval.retrieve(RetrievalQuery(text='anything')).hits, ())

    def test_exact_identifier_retains_catalog_metadata_and_complete_text(self):
        (self.root / 'billing.md').write_text('# Billing\nPAY-REFUND-042 requires an audit record for every refund.\n')
        runtime = self.build()
        result = runtime.multi_stage_retrieval.retrieve(RetrievalQuery(text='PAY-REFUND-042'))
        self.assertTrue(result.hits)
        hit = result.hits[0]
        self.assertEqual(Path(hit.metadata.sourcePath).name, 'billing.md')
        self.assertIn('requires an audit record', hit.snippet)
        self.assertEqual(hit.metadata.documentId, 'repo:billing.md')

    def test_cli_evaluation_uses_the_actual_repository_runtime(self):
        import argparse
        import contextlib
        import io
        from pi_platform.cli.main import _cmd_eval_retrieval
        (self.root/'billing.md').write_text('# Billing\nPAY-REFUND-042 requires an audit record.\n')
        runtime = self.build()
        expected = runtime.multi_stage_retrieval.retrieve(RetrievalQuery('PAY-REFUND-042')).hits
        golden = self.cache/'golden.yaml'
        golden.write_text('queries:\n  - id: exact\n    corpus: requirements\n    text: PAY-REFUND-042\n    tier: 3\n    tags: [identifier]\n    ground_truth:\n      chunk_ids: ['+expected[0].chunkId+']\n      protected: []\n')
        output = self.cache/'evaluation.json'
        args = argparse.Namespace(target=self.root,golden=golden,corpus_root=self.root/'absent-fixture',
                                  out=output,no_baseline=True,baseline=None)
        with patch('pi_platform.core.eval.tier3_commands.build_default_pipeline',
                   side_effect=AssertionError('must not build a parallel fixture pipeline')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(_cmd_eval_retrieval(args),0)
        payload = json.loads(output.read_text())
        self.assertEqual(payload['rows'][0]['hit_chunk_ids'],[h.chunkId for h in expected])

    def test_dense_query_is_embedded_once_with_query_role(self):
        from pi_platform.core.retrieval.semantic_index_service import CountingEmbeddingModel
        from pi_platform.ports.retrieval.embedding_profile import EMBEDDINGGEMMA2_512
        from pi_platform.core.orchestration.retrieval_composition import build_production_retrieval_runtime
        from pi_platform.core.retrieval.semantic_index_service import InMemoryVectorRecordStore
        from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
        from pi_platform.adapters.runtime.flat_dense_index import FlatDenseIndex
        model = CountingEmbeddingModel(profile=EMBEDDINGGEMMA2_512)
        catalog = {'c1': RetrievalHit(chunkId='c1', score=0.5, source='dense', snippet='billing content')}
        dense = FlatDenseIndex(embedding_profile_hash=model.profile().identity())
        from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole
        vector = model.embed_request(EmbeddingRequest(text='reimburse', role=EmbeddingRole.QUERY))
        dense.index_chunk('c1', vector, {})
        model.embed_request_calls.clear()
        runtime = build_production_retrieval_runtime(
            cache_root=self.cache, embedding_model=model, dense_index=dense,
            vector_record_store=InMemoryVectorRecordStore(), chunk_catalog=catalog,
        )
        result = runtime.multi_stage_retrieval.retrieve(RetrievalQuery(text='reimburse'))
        self.assertTrue(result.hits)
        self.assertEqual(len(model.embed_request_calls), 1)
        self.assertEqual(model.embed_request_calls[0].role.value, 'query')


if __name__ == '__main__':
    unittest.main()
