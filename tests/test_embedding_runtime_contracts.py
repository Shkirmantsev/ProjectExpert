"""Exact vendor prompt, batch, loader and safe device regression contracts."""
import math
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pi_platform.adapters.config.runtime_device import select_device
from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import EmbeddingGemma2EmbeddingModel
from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel
from pi_platform.ports.retrieval.embedding_model import EmbeddingRequest, EmbeddingRole, EmbeddingTask


class Row(list):
    def tolist(self):
        return list(self)


class EmbeddingRuntimeContracts(unittest.TestCase):
    def fake_loaded(self, adapter):
        dim = adapter.dimension()
        model = Mock()
        model.encode.side_effect = lambda texts, **kwargs: [Row([1/math.sqrt(dim)]*dim) for _ in texts]
        adapter._model = model
        return model

    def test_gemma_vendor_prompts_are_not_literal_prompt_names(self):
        adapter = EmbeddingGemma2EmbeddingModel()
        model = self.fake_loaded(adapter)
        adapter.embed_requests([
            EmbeddingRequest(text='refund', role=EmbeddingRole.QUERY),
            EmbeddingRequest(text='function', role=EmbeddingRole.QUERY, task=EmbeddingTask.CODE_RETRIEVAL),
            EmbeddingRequest(text='contract', role=EmbeddingRole.DOCUMENT, title='Billing'),
        ])
        self.assertEqual(model.encode.call_count, 1)
        self.assertEqual(model.encode.call_args.args[0], [
            'task: search result | query: refund', 'task: code retrieval | query: function',
            'title: Billing | text: contract',
        ])
        self.assertEqual(model.encode.call_args.kwargs['prompt'], '')

    def test_gguf_query_task_prompt_applied_only_to_queries(self):
        # The retired Qwen3 binding is gone; the production GGUF binding
        # (llama.cpp / EmbeddingGemma 2) is exercised against a fake
        # transport instead of a real runtime. The query side must carry
        # the EmbeddingGemma 2 task prompt while the document side must
        # stay in the plain "title: ... | text: ..." document format.
        from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_MODEL_ALIAS
        adapter = LlamaCppEmbeddingModel()
        calls = []
        def request(path, payload=None):
            calls.append((path, payload))
            if path == '/v1/models':
                return {'data': [{'id': GEMMA_MODEL_ALIAS,
                                  'architecture': {'input_modalities': ['text', 'image', 'audio', 'video']}}]}
            return {'data': [{'index': 0, 'embedding': [1/math.sqrt(768)] * 768}]}
        with patch.object(adapter, '_request', side_effect=request):
            vectors = adapter.embed_requests([
                EmbeddingRequest('refund', EmbeddingRole.QUERY),
                EmbeddingRequest('function', EmbeddingRole.QUERY, task=EmbeddingTask.CODE_RETRIEVAL),
                EmbeddingRequest('contract', EmbeddingRole.DOCUMENT, title='Billing'),
                EmbeddingRequest('plain', EmbeddingRole.DOCUMENT),
            ])
        # One identity probe plus one request per sequence.
        self.assertEqual([path for path, _ in calls], ['/v1/models'] + ['/v1/embeddings'] * 4)
        query_payloads = [calls[1][1]['input'][0], calls[2][1]['input'][0]]
        self.assertEqual(query_payloads, [
            'task: search result | query: refund',
            'task: code retrieval | query: function',
        ])
        for payload in query_payloads:
            self.assertTrue(payload.startswith('task: '), payload)
        # The task prompt is applied ONLY to queries: documents keep the
        # structured title/text format and never receive a task prompt.
        doc_payloads = [calls[3][1]['input'][0], calls[4][1]['input'][0]]
        self.assertEqual(doc_payloads, [
            'title: Billing | text: contract',
            'title: none | text: plain',
        ])
        for payload in doc_payloads:
            self.assertNotIn('task: ', payload)
            self.assertNotIn('query: ', payload)
        self.assertEqual(len(vectors), 4)
        self.assertEqual({len(vector) for vector in vectors}, {512})

    def test_gemma_loader_disables_unused_encoders_and_keeps_cpu_float32(self):
        constructor = Mock(return_value=object())
        torch = SimpleNamespace(float32='float32', bfloat16='bfloat16')
        with patch.dict(sys.modules, {'sentence_transformers': SimpleNamespace(SentenceTransformer=constructor), 'torch':torch}):
            adapter = EmbeddingGemma2EmbeddingModel(device='cpu', cache_folder='/tmp/model-cache')
            adapter._ensure_loaded()
        kwargs = constructor.call_args.kwargs
        self.assertEqual(kwargs['config_kwargs'], {'audio_config':None})
        self.assertEqual(kwargs['model_kwargs']['torch_dtype'], 'float32')
        self.assertEqual(kwargs['cache_folder'], '/tmp/model-cache/hub')
        self.assertEqual(kwargs['revision'], adapter.profile().model_revision)

    def test_gemma_passes_image_pixels_to_multimodal_encoder(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as raw:
            image = Path(raw) / 'image.png'
            image.write_bytes(b'fixture')
            adapter = EmbeddingGemma2EmbeddingModel()
            model = self.fake_loaded(adapter)
            adapter.embed_requests([EmbeddingRequest(text='figure', role=EmbeddingRole.DOCUMENT, image_path=str(image))])
            payload = model.encode.call_args.args[0][0]
            self.assertEqual(payload['image'], str(image))
            self.assertIn('<|image|>', payload['text'])
            self.assertEqual(adapter.profile().modality, 'text-image')

    def test_auto_checks_free_memory_before_selecting_gpu(self):
        cuda = SimpleNamespace(is_available=lambda:True, mem_get_info=lambda:(1024,8*1024**3))
        with patch.dict(sys.modules, {'torch':SimpleNamespace(cuda=cuda)}):
            decision = select_device('auto')
        self.assertEqual(decision.device,'cpu')
        self.assertIn('below safe threshold',decision.reason)
        cuda.mem_get_info=lambda:(5*1024**3,8*1024**3)
        with patch.dict(sys.modules, {'torch':SimpleNamespace(cuda=cuda)}):
            self.assertEqual(select_device('auto').device, 'cuda')
