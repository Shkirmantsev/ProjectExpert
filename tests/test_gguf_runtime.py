"""Pinned GGUF identity, numeric validation and atomic setup contracts."""
import hashlib
import io
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel, MODEL_ALIAS
from pi_platform.cli import gguf_setup
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError, EmbeddingRequest, EmbeddingRole


class GgufRuntimeTests(unittest.TestCase):
    def test_roles_order_and_normalization(self):
        model = LlamaCppEmbeddingModel()
        calls = []
        def request(path, payload=None):
            calls.append((path, payload))
            if path == '/v1/models':
                return {'data': [{'id': MODEL_ALIAS}]}
            return {'data': [{'index': 0, 'embedding': [1.] * 1024}]}
        with patch.object(model, '_request', side_effect=request):
            result = model.embed_requests([EmbeddingRequest('query', EmbeddingRole.QUERY), EmbeddingRequest('doc', EmbeddingRole.DOCUMENT)])
        self.assertTrue(calls[1][1]['input'][0].startswith('Instruct: '))
        self.assertEqual(calls[2][1]['input'], ['doc'])
        self.assertAlmostEqual(sum(x*x for x in result[0]), 1)
        self.assertEqual(model.stats()['real_binding'], '1')

    def test_rejects_wrong_model_and_malformed_vectors(self):
        model = LlamaCppEmbeddingModel()
        for result in ({'data': [{'id': 'other'}]}, {'data': None}, []):
            with self.subTest(result=result), patch.object(model, '_request', return_value=result):
                with self.assertRaises(EmbeddingModelError): model.embed('text')
        for vector in ([1.], [math.nan]*1024, [True]*1024, [0.]*1024):
            responses = [{'data': [{'id': MODEL_ALIAS}]}, {'data': [{'index': 0, 'embedding': vector}]}]
            with self.subTest(vector=vector[:1]), patch.object(model, '_request', side_effect=responses):
                with self.assertRaises(EmbeddingModelError): model.embed('text')

    def test_gemma_image_payload_mrl_and_profile_isolation(self):
        import base64
        from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_MODEL_ALIAS
        from pi_platform.adapters.retrieval.embedding_model_factory import EmbeddingModelFactory
        model = EmbeddingModelFactory().build('gemma-gguf', device='vulkan')
        with tempfile.TemporaryDirectory() as raw:
            image = Path(raw)/'figure.png'
            image.write_bytes(b'image fixture bytes')
            responses = [{'data':[{'id':GEMMA_MODEL_ALIAS}]}, {'data':[{'index':0,'embedding':[1.]*768}]}]
            with patch.object(model, '_request', side_effect=responses) as request:
                vector = model.embed_request(EmbeddingRequest('figure', EmbeddingRole.DOCUMENT, image_path=str(image)))
                content = request.call_args.args[1]['input'][0]['content']
                self.assertIn('text: figure', content[0]['text'])
                self.assertEqual(base64.b64decode(content[1]['image_url']['url'].split(',')[1]), image.read_bytes())
                self.assertNotIn(str(image), str(content))
        self.assertEqual(len(vector), 512)
        self.assertAlmostEqual(sum(x*x for x in vector), 1)
        self.assertNotEqual(model.profile().identity(), EmbeddingModelFactory().resolve_profile('gemma').identity())
        self.assertEqual(model.profile().modality, 'text-image')

    def test_gemma_download_requires_both_model_and_projector(self):
        from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_FILENAME, GEMMA_PROJECTOR_FILENAME
        with tempfile.TemporaryDirectory() as raw, patch.object(gguf_setup, '_download', side_effect=lambda cache, name, url, sha:cache/name) as download:
            path = gguf_setup.prepare(Path(raw), 'gemma-gguf')
            self.assertEqual(path.name, GEMMA_FILENAME)
            self.assertEqual([call.args[1] for call in download.call_args_list], [GEMMA_FILENAME,GEMMA_PROJECTOR_FILENAME])
            self.assertEqual(len((Path(raw)/'llama-api-key').read_text()), 64)

    def test_verified_download_reused_and_key_preserved(self):
        body = b'fixture GGUF bytes'
        with tempfile.TemporaryDirectory() as raw, patch.object(gguf_setup, 'SHA256', hashlib.sha256(body).hexdigest()):
            cache = Path(raw)
            with patch.object(gguf_setup.urllib.request, 'urlopen', return_value=io.BytesIO(body)) as download:
                model = gguf_setup.prepare(cache)
                self.assertEqual(model.read_bytes(), body)
                key = (cache/'llama-api-key').read_bytes()
                gguf_setup.prepare(cache)
                self.assertEqual(download.call_count, 1)
                self.assertEqual((cache/'llama-api-key').read_bytes(), key)

    def test_corrupt_download_never_installed(self):
        with tempfile.TemporaryDirectory() as raw:
            cache = Path(raw)
            with patch.object(gguf_setup.urllib.request, 'urlopen', return_value=io.BytesIO(b'bad')):
                with self.assertRaises(ValueError): gguf_setup.prepare(cache)
            self.assertFalse((cache/gguf_setup.FILENAME).exists())
            self.assertEqual(list(cache.glob('*.partial')), [])
