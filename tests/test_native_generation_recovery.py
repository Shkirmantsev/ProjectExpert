"""Native ANN/recovery proof using explicit controlled embeddings, never model proof."""
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from dataclasses import replace
from unittest.mock import patch

from pi_platform.adapters.runtime.usearch_dense_index import is_real_usearch_available, compute_source_generation


@unittest.skipUnless(is_real_usearch_available(), 'requires the actual USearch native package')
class NativeGenerationRecoveryTests(unittest.TestCase):
    def setUp(self):
        from pi_platform.adapters.ui.composition import build_ui_service
        from pi_platform.core.retrieval.semantic_index_service import CountingEmbeddingModel
        from pi_platform.ports.retrieval.embedding_profile import EMBEDDINGGEMMA2_512
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.cache = self.root / '.project-intelligence-cache'
        (self.root / 'billing.md').write_text('# Billing\nRefund card payments to the customer.\n')
        env = patch.dict(os.environ, {'PI_STARTUP_PROFILE':'production', 'PI_EMBEDDING_MODEL':'gemma',
            'PI_EMBEDDING_DEVICE':'cpu', 'PI_DENSE_INDEX':'usearch', 'PI_DOCLING_ENABLED':'0'})
        env.start()
        self.addCleanup(env.stop)
        factory = patch('pi_platform.adapters.retrieval.embedding_model_factory.EmbeddingModelFactory.build',
            side_effect=lambda alias, **kwargs: CountingEmbeddingModel(profile=replace(
                EMBEDDINGGEMMA2_512, output_dimension=16, model_revision='native-test-' + alias)))
        factory.start()
        self.addCleanup(factory.stop)
        self.service, self.readiness = build_ui_service(repo_root=self.root, defer_runtime=True)

    def build(self, **kwargs):
        from pi_platform.cli.main import _bootstrap_and_index_target
        summary = _bootstrap_and_index_target(self.root, service=self.service, readiness=self.readiness, **kwargs)
        return summary, self.service._retrieval.runtime

    def test_native_switchback_loads_generation_and_missing_snapshot_recovers(self):
        first, runtime_a = self.build()
        self.assertFalse(runtime_a.extra['dense_generation_loaded'])
        index = Path(runtime_a.dense_index.index_path)
        original_bytes, modified_at = index.read_bytes(), index.stat().st_mtime_ns
        (self.root / 'shipping.md').write_text('# Shipping\nDispatch warehouse parcels.\n')
        _, runtime_b = self.build()
        self.assertNotEqual(runtime_b.extra['source_generation'], runtime_a.extra['source_generation'])
        (self.root / 'shipping.md').unlink()
        third, returned = self.build()
        self.assertTrue(returned.extra['dense_generation_loaded'])
        self.assertEqual(third['new_vectors'], 0)
        self.assertEqual(index.read_bytes(), original_bytes)
        self.assertEqual(index.stat().st_mtime_ns, modified_at)
        shutil.rmtree(self.cache / 'runtime-state')
        recovered, runtime = self.build()
        self.assertTrue(runtime.extra['dense_generation_loaded'])
        self.assertTrue(self.readiness.is_ready())
        self.assertEqual(recovered['new_vectors'], 0)

    def test_corrupt_native_index_metadata_or_key_sidecar_rebuilds_without_inference(self):
        _, runtime = self.build()
        for artifact in ('index', 'metadata', 'keys'):
            with self.subTest(artifact=artifact):
                dense = runtime.dense_index
                path = Path({'index':dense.index_path, 'metadata':dense.index_meta_path, 'keys':dense.key_sidecar_path}[artifact])
                path.write_bytes(b'corrupt generation artifact')
                summary, runtime = self.build()
                self.assertFalse(runtime.extra['dense_generation_loaded'])
                self.assertEqual(summary['new_vectors'], 0)
                self.assertEqual(runtime.dense_index.stats()['vectors'], len(runtime.extra['chunk_ids']))
                self.assertTrue(self.readiness.is_ready())
                _, reopened = self.build()
                self.assertTrue(reopened.extra['dense_generation_loaded'])

    def test_valid_json_with_wrong_native_profile_dimension_or_count_is_rebuilt(self):
        _, runtime = self.build()
        for field, value in (("embedding_profile_hash", "wrong-profile"), ("dim", 999), ("vector_count", 999)):
            with self.subTest(field=field):
                path = Path(runtime.dense_index.index_meta_path)
                metadata = json.loads(path.read_text())
                metadata[field] = value
                path.write_text(json.dumps(metadata))
                summary, runtime = self.build()
                self.assertFalse(runtime.extra['dense_generation_loaded'])
                self.assertEqual(summary['new_vectors'], 0)

    def test_failed_native_activation_preserves_successful_snapshot_and_runtime(self):
        from pi_platform.core.sync.version_snapshot import RuntimeSnapshotService
        _, previous_runtime = self.build()
        before = RuntimeSnapshotService(self.cache).read_snapshot()
        (self.root / 'added.md').write_text('# Added\nNew branch evidence.\n')
        original_replace = os.replace
        def fail_activation(source, destination):
            if str(destination).endswith('.usearch'):
                raise OSError('simulated interruption before native rename')
            return original_replace(source, destination)
        with patch('pi_platform.adapters.runtime.usearch_dense_index.os.replace', side_effect=fail_activation):
            with self.assertRaisesRegex(RuntimeError, 'native rename'):
                self.build()
        self.assertFalse(self.readiness.is_ready())
        self.assertIs(self.service._retrieval.runtime, previous_runtime)
        self.assertEqual(RuntimeSnapshotService(self.cache).read_snapshot(), before)
        from pi_platform.adapters.runtime.usearch_dense_index import USearchDenseIndex, ANNIndexError
        with patch.object(USearchDenseIndex, '_validate_native', side_effect=ANNIndexError('sample query validation failed')):
            with self.assertRaisesRegex(RuntimeError, 'sample query validation failed'):
                self.build()
        self.assertFalse(self.readiness.is_ready())
        self.assertEqual(RuntimeSnapshotService(self.cache).read_snapshot(), before)
        recovered, _ = self.build()
        self.assertTrue(recovered['ready'])
        self.assertTrue(self.readiness.is_ready())

    def test_seeded_native_ann_recall_against_exact_cosine(self):
        import time
        import numpy as np
        import usearch
        from pi_platform.adapters.runtime.usearch_dense_index import USearchDenseIndex
        # Acceptance floor: retain at least nine of ten true nearest neighbors
        # on average for a held-out isotropic corpus. This is ANN correctness /
        # tuning evidence, not a semantic-model retrieval-quality benchmark.
        rng = np.random.default_rng(20261020)
        corpus = rng.normal(size=(1000,64)).astype(np.float32)
        corpus /= np.linalg.norm(corpus, axis=1, keepdims=True)
        queries = rng.normal(size=(50,64)).astype(np.float32)
        queries /= np.linalg.norm(queries, axis=1, keepdims=True)
        dense = USearchDenseIndex(embedding_profile_hash="seeded-recall-64d",
            cache_root=str(self.cache / "recall"), output_dimension=64,
            m=32, ef_construction=200, ef_query=100)
        for ordinal, vector in enumerate(corpus):
            dense.index_chunk(f"c{ordinal}", vector.tolist(), {})
        exact_scores = queries @ corpus.T
        expected = np.argsort(-exact_scores, axis=1)[:, :10]
        recall = []
        started = time.perf_counter()
        for vector, truth in zip(queries, expected):
            found = {int(hit.chunkId[1:]) for hit in dense.query(vector.tolist(), top_k=10)}
            recall.append(len(found.intersection(int(item) for item in truth)) / 10)
        elapsed = time.perf_counter() - started
        result = {
            "benchmark": "seeded-native-ann-exact-cosine", "seed":20261020,
            "corpus_size":1000, "query_count":50, "dimension":64, "top_k":10,
            "recall_at_10":sum(recall)/len(recall), "required_recall_at_10":0.9,
            "mean_query_ms":elapsed*1000/len(queries), "usearch_version":usearch.__version__,
            "connectivity":32, "expansion_add":200, "expansion_search":100,
            "limitation":"Synthetic ANN recall; does not certify semantic model quality or production scale.",
        }
        Path("/tmp/projectexpert-native-ann-recall.json").write_text(json.dumps(result, indent=2, sort_keys=True))
        self.assertGreaterEqual(result["recall_at_10"], 0.9, result)

    def test_generation_binds_text_hash_to_chunk_identity(self):
        first = compute_source_generation(['a','b'], retrieval_text_hashes=['x','y'], embedding_profile_hash='profile')
        swapped = compute_source_generation(['a','b'], retrieval_text_hashes=['y','x'], embedding_profile_hash='profile')
        self.assertNotEqual(first, swapped)

    def test_operator_override_wins_startup_environment_for_subsequent_refreshes(self):
        from pi_platform.adapters.ui.http_server import UiHttpServer
        from pi_platform.core.control.retrieval_settings import load_retrieval_settings
        first, _ = self.build()
        self.assertEqual(first['active_model'], 'gemma')
        server = UiHttpServer(self.service, readiness=self.readiness.is_ready)
        response = server.admin_routes.handle_put_retrieval({'embedding_model_alias':'qwen', 'device':'cpu'})
        self.assertEqual(response.status, 200)
        self.assertFalse(self.readiness.is_ready())
        selected, _ = self.build(model_alias='gemma')  # old startup CLI/default cannot undo a later command
        self.assertEqual(selected['active_model'], 'qwen')
        (self.root / 'changed.md').write_text('# Change\nTrigger a later branch refresh.\n')
        refreshed, _ = self.build()
        self.assertEqual(refreshed['active_model'], 'qwen')
        self.assertEqual(load_retrieval_settings(self.root).embedding_model_alias, 'qwen')

    def test_operator_change_at_publication_cannot_be_cleared_by_refresh_finalizer(self):
        from pi_platform.adapters.ui.http_server import UiHttpServer
        from pi_platform.core.control.retrieval_settings import load_retrieval_settings
        self.build()
        server = UiHttpServer(self.service, readiness=self.readiness.is_ready)
        def late_operator_change(*args, **kwargs):
            response = server.admin_routes.handle_put_retrieval({'embedding_model_alias':'qwen'})
            self.assertEqual(response.status, 200)
            return {'ready':True}
        with patch('pi_platform.cli.main._bootstrap_and_index_target_locked', side_effect=late_operator_change):
            with self.assertRaisesRegex(RuntimeError, 'configuration changed during indexing'):
                self.build()
        self.assertFalse(self.readiness.is_ready())
        self.assertEqual(load_retrieval_settings(self.root).embedding_model_alias, 'qwen')
        recovered, _ = self.build()
        self.assertEqual(recovered['active_model'], 'qwen')
        self.assertTrue(self.readiness.is_ready())

    def test_first_bootstrap_preserves_project_defaults_and_retrieval_hash_inventory(self):
        from pi_platform.core.control.retrieval_settings import load_retrieval_settings
        (self.root / 'project-context.yaml').write_text('runtime:\n  embedding_model: qwen\n  embedding_device: cpu\n')
        with patch.dict(os.environ):
            os.environ.pop('PI_EMBEDDING_MODEL', None)
            summary, _ = self.build()
        self.assertEqual(summary['active_model'], 'qwen')
        self.assertEqual(load_retrieval_settings(self.root).embedding_model_alias, 'qwen')
        inventory = json.loads((self.cache / 'source-inventory.json').read_text())
        entries = inventory['entries']
        if isinstance(entries, dict):
            entries = entries.values()
        self.assertTrue(all(entry['retrieval_text_hash'] for entry in entries if entry['path'].endswith('.md')))


class SnapshotBundleCrashTests(unittest.TestCase):
    def snapshot(self, suffix):
        from pi_platform.core.sync.version_snapshot import PersistedActiveVersion, ManifestSnapshot, SourceSnapshot
        return dict(active=PersistedActiveVersion(
            project_version=suffix, branch=suffix, head=suffix, working_tree_fingerprint=suffix,
            manifest_snapshot_hash="manifest-" + suffix, source_snapshot_hash="source-" + suffix,
            embedding_profile_identity="profile", active_index_generation=suffix, last_refresh_id=suffix),
            manifest=ManifestSnapshot(snapshot_hash="manifest-" + suffix, chunk_ids=(suffix,), graph_node_ids=()),
            source=SourceSnapshot(snapshot_hash="source-" + suffix, source_ids=(suffix,), content_hashes={suffix:suffix}))

    def test_process_exit_after_manifest_write_cannot_mix_snapshot_generations(self):
        import subprocess
        import sys
        from pi_platform.core.sync.version_snapshot import RuntimeSnapshotService
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeSnapshotService(tmp)
            previous = service.commit(**self.snapshot("A"))
            candidate = self.snapshot("B")
            payload = {key:value.as_dict() for key,value in candidate.items()}
            script = """
import json, os, sys
from pi_platform.core.sync.version_snapshot import RuntimeSnapshotService, PersistedActiveVersion, ManifestSnapshot, SourceSnapshot
service = RuntimeSnapshotService(sys.argv[1])
payload = json.loads(sys.argv[2])
original = service._atomic_write_json
def exit_after_manifest(path, body):
    original(path, body)
    if path.name == 'manifest-snapshot.json':
        os._exit(91)
service._atomic_write_json = exit_after_manifest
service.commit(active=PersistedActiveVersion(**payload['active']), manifest=ManifestSnapshot.from_dict(payload['manifest']), source=SourceSnapshot.from_dict(payload['source']))
"""
            child = subprocess.run([sys.executable, '-c', script, tmp, json.dumps(payload)], capture_output=True, timeout=20)
            self.assertEqual(child.returncode, 91, child.stderr.decode())
            self.assertEqual(service.read_snapshot(), previous)
            service.commit(**candidate)
            self.assertEqual(service.read_snapshot().active.head, 'B')

    def test_legacy_snapshot_migrates_before_any_new_mirror_is_written(self):
        from pi_platform.core.sync.version_snapshot import RuntimeSnapshotService, RuntimeSnapshotError
        with tempfile.TemporaryDirectory() as tmp:
            service = RuntimeSnapshotService(tmp)
            previous = service.commit(**self.snapshot('A'))
            (service.runtime_state_dir / 'snapshot.json').unlink()
            self.assertEqual(service.read_snapshot(), previous)
            original = service._atomic_write_json
            def fail_source(path, payload):
                if path.name == 'source-snapshot.json':
                    raise OSError('simulated migration write failure')
                original(path, payload)
            with patch.object(service, '_atomic_write_json', side_effect=fail_source):
                with self.assertRaises(RuntimeSnapshotError):
                    service.commit(**self.snapshot('B'))
            self.assertEqual(service.read_snapshot(), previous)


if __name__ == '__main__':
    unittest.main()
