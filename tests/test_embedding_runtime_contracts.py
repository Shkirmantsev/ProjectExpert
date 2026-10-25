"""Exact vendor prompt, batch, loader and safe device regression contracts."""
import math
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from pi_platform.adapters.config.runtime_device import select_device
from pi_platform.adapters.retrieval.embeddinggemma2_embedding_model import EmbeddingGemma2EmbeddingModel
from pi_platform.adapters.retrieval.qwen3_embedding_model import Qwen3EmbeddingModel, QUERY_INSTRUCTION
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

    def test_qwen_mixed_batch_uses_instruct_template_once(self):
        adapter = Qwen3EmbeddingModel()
        model = self.fake_loaded(adapter)
        adapter.embed_requests([
            EmbeddingRequest(text='refund', role=EmbeddingRole.QUERY),
            EmbeddingRequest(text='contract', role=EmbeddingRole.DOCUMENT),
        ])
        self.assertEqual(model.encode.call_count, 1)
        self.assertEqual(model.encode.call_args.args[0], [f'Instruct: {QUERY_INSTRUCTION}\nQuery:refund', 'contract'])
        self.assertEqual(model.encode.call_args.kwargs['prompt'], '')

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
