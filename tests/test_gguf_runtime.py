"""Pinned GGUF identity, numeric validation and atomic setup contracts."""
import hashlib
import io
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_MODEL_ALIAS
from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel
from pi_platform.cli import gguf_setup
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError, EmbeddingRequest, EmbeddingRole


def _models_response():
    """The pinned runtime identity: alias plus advertised modalities."""
    return {'data': [{'id': GEMMA_MODEL_ALIAS,
                      'architecture': {'input_modalities': ['text', 'image', 'audio', 'video']}}]}


class GgufRuntimeTests(unittest.TestCase):
    def test_roles_order_and_normalization(self):
        model = LlamaCppEmbeddingModel()
        calls = []
        def request(path, payload=None):
            calls.append((path, payload))
            if path == '/v1/models':
                return _models_response()
            return {'data': [{'index': 0, 'embedding': [1.] * 768}]}
        with patch.object(model, '_request', side_effect=request):
            result = model.embed_requests([EmbeddingRequest('query', EmbeddingRole.QUERY), EmbeddingRequest('doc', EmbeddingRole.DOCUMENT)])
        self.assertTrue(calls[1][1]['input'][0].startswith('task: search result | query: '))
        self.assertEqual(calls[2][1]['input'], ['title: none | text: doc'])
        self.assertAlmostEqual(sum(x*x for x in result[0]), 1)
        self.assertEqual(model.stats()['real_binding'], '1')

    def test_rejects_wrong_model_and_malformed_vectors(self):
        model = LlamaCppEmbeddingModel()
        for result in ({'data': [{'id': 'other'}]}, {'data': None}, []):
            with self.subTest(result=result), patch.object(model, '_request', return_value=result):
                with self.assertRaises(EmbeddingModelError): model.embed('text')
        for vector in ([1.], [math.nan]*768, [True]*768, [0.]*768, [1.]*1024):
            responses = [_models_response(), {'data': [{'index': 0, 'embedding': vector}]}]
            with self.subTest(vector=vector[:1], length=len(vector)), patch.object(model, '_request', side_effect=responses):
                with self.assertRaises(EmbeddingModelError): model.embed('text')

    def test_gemma_image_payload_mrl_and_profile_isolation(self):
        import base64
        from pi_platform.adapters.retrieval.embedding_model_factory import EmbeddingModelFactory
        model = EmbeddingModelFactory().build('gemma', device='vulkan')
        with tempfile.TemporaryDirectory() as raw:
            image = Path(raw)/'figure.png'
            image.write_bytes(b'image fixture bytes')
            responses = [_models_response(), {'data':[{'index':0,'embedding':[1.]*768}]}]
            with patch.object(model, '_request', side_effect=responses) as request:
                vector = model.embed_request(EmbeddingRequest('figure', EmbeddingRole.DOCUMENT, image_path=str(image)))
                content = request.call_args.args[1]['input'][0]['content']
                self.assertIn('text: figure', content[0]['text'])
                self.assertEqual(base64.b64decode(content[1]['image_url']['url'].split(',')[1]), image.read_bytes())
                self.assertNotIn(str(image), str(content))
        self.assertEqual(len(vector), 512)
        self.assertAlmostEqual(sum(x*x for x in vector), 1)
        # The default binding resolves to the pinned GGUF profile and the
        # native Transformers binding keeps its own vector namespace.
        self.assertEqual(model.profile().identity(), EmbeddingModelFactory().resolve_profile('gemma').identity())
        self.assertNotEqual(model.profile().identity(), EmbeddingModelFactory().resolve_profile('gemma-torch').identity())
        self.assertEqual(model.profile().modality, 'text-image-audio-video')
        self.assertEqual(model.profile().output_dimension, 512)

    def test_gemma_download_requires_both_model_and_projector(self):
        from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_FILENAME, GEMMA_PROJECTOR_FILENAME
        with tempfile.TemporaryDirectory() as raw, patch.object(gguf_setup, '_download', side_effect=lambda cache, name, url, sha:cache/name) as download:
            path = gguf_setup.prepare(Path(raw), 'gemma')
            self.assertEqual(path.name, GEMMA_FILENAME)
            self.assertEqual([call.args[1] for call in download.call_args_list], [GEMMA_FILENAME,GEMMA_PROJECTOR_FILENAME])
            self.assertEqual(len((Path(raw)/'llama-api-key').read_text()), 64)

    def test_verified_download_reused_and_key_preserved(self):
        body = b'fixture GGUF bytes'
        with tempfile.TemporaryDirectory() as raw:
            cache = Path(raw)
            # A fresh body per download: prepare() fetches both pinned
            # artefacts and closes each response stream when done.
            with patch.object(gguf_setup, 'GEMMA_FILES', (
                ('backbone.gguf', 'https://example.invalid/backbone.gguf', hashlib.sha256(body).hexdigest()),
                ('projector.gguf', 'https://example.invalid/projector.gguf', hashlib.sha256(body).hexdigest()),
            )), patch.object(gguf_setup.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(body)) as download:
                model = gguf_setup.prepare(cache)
                self.assertEqual(model.read_bytes(), body)
                key = (cache/'llama-api-key').read_bytes()
                gguf_setup.prepare(cache)
                self.assertEqual(download.call_count, 2)
                self.assertEqual((cache/'llama-api-key').read_bytes(), key)

    def test_corrupt_download_never_installed(self):
        with tempfile.TemporaryDirectory() as raw:
            cache = Path(raw)
            with patch.object(gguf_setup, 'GEMMA_FILES', (
                ('backbone.gguf', 'https://example.invalid/backbone.gguf', hashlib.sha256(b'expected').hexdigest()),
            )), patch.object(gguf_setup.urllib.request, 'urlopen', side_effect=lambda *a, **k: io.BytesIO(b'bad')):
                with self.assertRaises(ValueError): gguf_setup.prepare(cache)
            self.assertFalse((cache/'backbone.gguf').exists())
            self.assertEqual(list(cache.glob('*.partial')), [])

    def test_prepare_rejects_retired_alias(self):
        from pi_platform.adapters.retrieval.embedding_model_factory import RetiredEmbeddingAliasError
        with tempfile.TemporaryDirectory() as raw:
            for alias in ('qwen-gguf', 'gemma-gguf', 'gemma-torch'):
                with self.subTest(alias=alias):
                    with self.assertRaises(RetiredEmbeddingAliasError):
                        gguf_setup.prepare(Path(raw), alias)


if __name__ == '__main__':
    unittest.main()
