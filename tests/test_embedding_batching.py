"""Regression evidence for bounded end-to-end embedding batches."""
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel, _BatchCapacityError
from pi_platform.adapters.runtime.sqlite_vector_record_store import SqliteVectorRecordStore, encode_vector_payload
from pi_platform.core.retrieval.semantic_index_service import SemanticIndexServiceError
from pi_platform.core.inference.stage_resources import StageResourceEvidence, StageResourcePlanner
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError
from pi_platform.ports.runtime.vector_record_store import VectorRecordStoreError
from tests.test_vector_record_store import _record, PROFILE_A, PROFILE_B
from tests import test_semantic_index_service as semantic_tests
from tests.test_semantic_index_service import _make_chunk
from tests.test_gguf_runtime import _models_response


class SemanticBatchTests(unittest.TestCase):
    setUp = semantic_tests.SemanticIndexServiceReuseTests.setUp
    def test_semantic_batch_rollout_flag_and_explicit_override(self):
        from pi_platform.core.retrieval.semantic_index_service import SemanticIndexService
        kwargs = dict(embedding_model=self.model, vector_record_store=self.store, dense_index=self.dense)
        with patch.dict('os.environ', {'PI_EMBED_BATCHING': '0'}):
            self.assertEqual(SemanticIndexService(**kwargs)._batch_size, 1)
            self.assertEqual(SemanticIndexService(**kwargs, batch_size=7)._batch_size, 7)
        with patch.dict('os.environ', {'PI_EMBED_BATCHING': '1'}):
            self.assertEqual(SemanticIndexService(**kwargs)._batch_size, 32)

    def test_only_misses_are_grouped_and_restart_reuses_committed_batches(self):
        chunks = [_make_chunk(str(i), f'text {i}') for i in range(5)]
        self.service._batch_size = 2
        original = self.model.embed_requests
        with patch.object(self.model, 'embed_requests', wraps=original) as embed:
            report = self.service.embed_active_chunks(chunks)
            self.assertEqual([len(call.args[0]) for call in embed.call_args_list], [2, 2, 1])
            self.assertEqual(report.embedded_count, 5)
        with patch.object(self.model, 'embed_requests', side_effect=AssertionError('cache hit embedded')):
            self.assertEqual(self.service.embed_active_chunks(chunks).reused_count, 5)

    def test_malformed_late_result_does_not_persist_partial_batch(self):
        self.service._batch_size = 32
        chunks = [_make_chunk('a', 'alpha'), _make_chunk('b', 'beta')]
        vector = self.model._deterministic_vector("alpha")
        with patch.object(self.model, 'embed_requests', return_value=[vector, [float('nan')] * 512]):
            with self.assertRaises(SemanticIndexServiceError):
                self.service.embed_active_chunks(chunks)
        self.assertEqual(self.store.stats()['records'], 0)
        self.assertEqual(self.dense.stats()['vectors'], 0)

    def test_cached_revision_and_normalization_must_match_profile(self):
        chunk = _make_chunk('a', 'alpha')
        self.service.embed_active_chunks([chunk])
        for changes in ({'model_revision': 'other'}, {'normalization': 'none'}):
            record = self.store.get('a', self.profile_hash)
            self.store.put(replace(record, **changes))
            self.assertEqual(self.service.embed_active_chunks([chunk]).embedded_count, 1)

    def test_progress_is_emitted_after_persistence_and_dense_insertion(self):
        chunks = [_make_chunk(str(i), f'text {i}') for i in range(3)]
        self.service._batch_size = 2
        progress = []
        def callback(completed, total):
            self.assertEqual(self.store.stats()['records'], completed)
            self.assertEqual(self.dense.stats()['vectors'], completed)
            progress.append((completed, total))
        self.service.set_progress_callback(callback)
        self.service.embed_active_chunks(chunks)
        self.assertEqual(progress, [(2, 3), (3, 3)])

    def test_failed_batch_does_not_advance_progress(self):
        progress = []
        self.service.set_progress_callback(lambda completed, total: progress.append((completed, total)))
        with patch.object(self.model, 'embed_requests', side_effect=EmbeddingModelError('fixture')):
            with self.assertRaises(SemanticIndexServiceError):
                self.service.embed_active_chunks([_make_chunk('a', 'alpha')])
        self.assertEqual(progress, [])

    def test_corrupt_persisted_vector_is_recomputed(self):
        chunk = _make_chunk('a', 'alpha')
        self.service.embed_active_chunks([chunk])
        record = self.store.get('a', self.profile_hash)
        self.store.put(replace(record, vector_payload=encode_vector_payload([0.] * 512)))
        self.assertEqual(self.service.embed_active_chunks([chunk]).embedded_count, 1)


class SqliteBatchTests(unittest.TestCase):
    def test_bulk_lookup_bounded_and_profile_scoped_and_borrowed_transaction(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        store = SqliteVectorRecordStore(db)
        store.put_many([_record(str(i)) for i in range(1100)])
        store.put(_record('0', PROFILE_B))
        result = store.get_many([str(i) for i in range(1101)], PROFILE_A)
        self.assertEqual(len(result), 1100)
        self.assertEqual(result['0'].embedding_profile_hash, PROFILE_A)
        self.assertTrue(db.in_transaction)
        db.rollback()
        self.assertEqual(store.stats()['records'], 0)

    def test_failed_batch_rolls_back_without_touching_borrowed_work(self):
        db = sqlite3.connect(':memory:')
        self.addCleanup(db.close)
        store = SqliteVectorRecordStore(db)
        store.put(_record('prior'))
        db.execute("CREATE TRIGGER reject_bad BEFORE INSERT ON embeddings WHEN NEW.chunk_id = 'bad' BEGIN SELECT RAISE(ABORT, 'fixture'); END")
        with self.assertRaises(VectorRecordStoreError):
            store.put_many([_record('good'), _record('bad')])
        self.assertEqual(list(store.get_many(['prior', 'good', 'bad'], PROFILE_A)), ['prior'])

    def test_owned_batch_is_durable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / 'vectors.sqlite')
            SqliteVectorRecordStore(db_path=path).put_many([_record('a'), _record('b')])
            self.assertEqual(len(SqliteVectorRecordStore(db_path=path).get_many(['a', 'b'], PROFILE_A)), 2)


class LlamaBatchTests(unittest.TestCase):
    def make(self, **kwargs):
        kwargs.setdefault("batch_size", 32)
        model = LlamaCppEmbeddingModel(**kwargs)
        calls = []
        def request(path, payload=None):
            if path == '/v1/models':
                return _models_response()
            calls.append(payload['input'])
            return {'data': [{'index': i, 'embedding': [i + 1.] * 768}
                             for i in reversed(range(len(payload['input'])))]}
        model._request = request
        return model, calls

    def test_batching_is_gated_off_by_default_and_environment_can_enable_it(self):
        with patch.dict('os.environ', {'PI_EMBED_BATCHING': '0'}):
            self.assertEqual(LlamaCppEmbeddingModel()._batch_size, 1)
        with patch.dict('os.environ', {'PI_EMBED_BATCHING': '1'}):
            self.assertEqual(LlamaCppEmbeddingModel()._batch_size, 32)
        self.assertEqual(LlamaCppEmbeddingModel(batch_size=3)._batch_size, 3)

    def test_text_batch_respects_item_and_prompted_token_budgets(self):
        model, calls = self.make(batch_size=3, max_batch_tokens=4, token_counter=lambda text: 2)
        self.assertEqual(len(model.embed_batch(['a', 'b', 'c', 'd', 'e'])), 5)
        self.assertEqual([len(batch) for batch in calls], [2, 2, 1])

    def test_overlong_single_input_fails_explicitly_without_transport(self):
        model, calls = self.make(max_input_tokens=3, token_counter=lambda text: 4)
        with self.assertRaisesRegex(EmbeddingModelError, 'smaller segments'):
            model.embed_batch(['a'])
        self.assertEqual(calls, [])

    def test_duplicate_response_indices_are_rejected(self):
        model, calls = self.make()
        model._modalities = frozenset({'text'})
        model._request = lambda *args: {'data': [{'index': 0, 'embedding': [1.] * 768}] * 2}
        with self.assertRaises(EmbeddingModelError):
            model.embed_batch(['a', 'b'])

    def test_capacity_errors_split_batches_without_changing_order(self):
        model, calls = self.make()
        original = model._request
        def request(path, payload=None):
            if path == '/v1/embeddings' and len(payload['input']) > 1:
                raise _BatchCapacityError('fixture capacity')
            return original(path, payload)
        model._request = request
        self.assertEqual(len(model.embed_batch(['a', 'b', 'c'])), 3)
        self.assertEqual([batch[0] for batch in calls], ['title: none | text: a', 'title: none | text: b', 'title: none | text: c'])


class StageResourceTests(unittest.TestCase):
    def item(self, backend, values, stage='embedding', **kwargs):
        return StageResourceEvidence(stage, backend, 'runtime', 'workload', tuple(values), **kwargs)

    def select(self, items, stage='embedding'):
        return StageResourcePlanner().select(stage, items, runtime_identity='runtime', workload_identity='workload')

    def test_two_percent_gain_wins_without_artificial_threshold(self):
        decision = self.select([self.item('cpu', [100] * 3), self.item('cuda', [102] * 3)])
        self.assertEqual((decision.backend, decision.evidence_state), ('cuda', 'measured'))

    def test_overlapping_samples_report_inconclusive_and_prefer_accelerator(self):
        decision = self.select([self.item('cpu', [100, 103, 100]), self.item('cuda', [101, 102, 103])])
        self.assertEqual((decision.backend, decision.evidence_state), ('cuda', 'inconclusive'))

    def test_stage_quality_memory_and_device_gates(self):
        decision = self.select([
            self.item('cuda', [500] * 3, quality_validated=False),
            self.item('vulkan', [500] * 3, memory_admitted=False),
            self.item('hybrid', [500] * 3, physical_devices=('gpu0', 'gpu0')),
            self.item('cpu', [100] * 3), self.item('cuda', [900] * 3, stage='pdf'),
        ])
        self.assertEqual(decision.backend, 'cpu')
        self.assertEqual(len(decision.rejected), 3)

    def test_invalid_or_stale_measurements_do_not_select_a_gpu(self):
        decision = self.select([self.item('cuda', [float('nan')] * 3),
                                replace(self.item('vulkan', [200] * 3), runtime_identity='old')])
        self.assertEqual((decision.backend, decision.evidence_state), ('cpu', 'unavailable'))
