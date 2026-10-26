"""Tests for the multimodal GGUF embedding binding.

The binding must transport media to the runtime, must discover which
modalities the runtime actually supports instead of assuming them, and must
refuse an unsupported modality rather than substituting a text-only or
fabricated vector.
"""

import json
import math
import os
import unittest
from unittest.mock import patch

from pi_platform.adapters.retrieval.gguf_artifacts import GEMMA_MODEL_ALIAS
from pi_platform.adapters.retrieval.llama_cpp_embedding_model import (
    LlamaCppEmbeddingModel,
)
from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingRequest,
    EmbeddingRole,
)


def unit_vector(dimension=768):
    return [1.0 / math.sqrt(dimension)] * dimension


def models_response(modalities=("text", "image", "audio", "video")):
    return {
        "data": [
            {
                "id": GEMMA_MODEL_ALIAS,
                "architecture": {"input_modalities": list(modalities)},
            }
        ]
    }


class FakeRuntime:
    """A minimal fake of the llama.cpp HTTP surface."""

    def __init__(self, modalities=("text", "image", "audio", "video")):
        self.modalities = list(modalities)
        self.requests = []
        self.vectors = []

    def request(self, path, payload=None):
        self.requests.append((path, payload))
        if path == "/v1/models":
            return models_response(self.modalities)
        if path == "/v1/embeddings":
            self.vectors.append(payload)
            return {"data": [{"index": 0, "embedding": unit_vector()}]}
        raise AssertionError(f"unexpected path {path}")

    @property
    def last_payload(self):
        return self.requests[-1][1]


class MultimodalAdapterTests(unittest.TestCase):
    def make(self, modalities=("text", "image", "audio", "video")):
        runtime = FakeRuntime(modalities)
        model = LlamaCppEmbeddingModel(device="cpu")
        model._request = runtime.request
        return model, runtime

    def test_text_request_uses_the_query_task_prompt(self):
        model, runtime = self.make()
        model.embed_request(EmbeddingRequest("refund policy", EmbeddingRole.QUERY))
        payload = runtime.last_payload
        self.assertEqual(
            payload["input"][0],
            "task: search result | query: refund policy",
        )

    def test_document_request_uses_the_document_format(self):
        model, runtime = self.make()
        model.embed_request(
            EmbeddingRequest("the policy", EmbeddingRole.DOCUMENT, title="Billing")
        )
        self.assertEqual(
            runtime.last_payload["input"][0],
            "title: Billing | text: the policy",
        )

    def test_image_request_is_shaped_as_a_content_part(self):
        model, runtime = self.make()
        with patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as stat, \
             patch("pathlib.Path.read_bytes", return_value=b"\x89PNG\r\n\x1a\n"):
            stat.return_value.st_size = 64
            model.embed_request(
                EmbeddingRequest("a diagram", EmbeddingRole.DOCUMENT, image_path="/tmp/a.png")
            )
        content = runtime.last_payload["input"][0]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertEqual(content[1]["type"], "image_url")
        self.assertTrue(content[1]["image_url"]["url"].startswith("data:image/png;base64,"))

    def test_audio_request_is_shaped_as_an_input_audio_part(self):
        model, runtime = self.make()
        with patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as stat, \
             patch("pathlib.Path.read_bytes", return_value=b"RIFF"):
            stat.return_value.st_size = 64
            model.embed_request(
                EmbeddingRequest("a recording", EmbeddingRole.DOCUMENT, audio_path="/tmp/a.wav")
            )
        content = runtime.last_payload["input"][0]["content"]
        self.assertEqual(content[1]["type"], "input_audio")
        self.assertIn("data", content[1]["input_audio"])

    def test_video_request_is_shaped_as_an_input_video_part(self):
        model, runtime = self.make()
        with patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as stat, \
             patch("pathlib.Path.read_bytes", return_value=b"\x00\x00"):
            stat.return_value.st_size = 64
            model.embed_request(
                EmbeddingRequest("a clip", EmbeddingRole.DOCUMENT, video_path="/tmp/a.mp4")
            )
        content = runtime.last_payload["input"][0]["content"]
        self.assertEqual(content[1]["type"], "input_video")

    def test_unsupported_modality_is_refused_explicitly(self):
        model, _runtime = self.make(modalities=("text", "image"))
        with patch("pathlib.Path.is_file", return_value=True), \
             patch("pathlib.Path.stat") as stat, \
             patch("pathlib.Path.read_bytes", return_value=b"RIFF"):
            stat.return_value.st_size = 64
            with self.assertRaises(Exception) as ctx:
                model.embed_request(
                    EmbeddingRequest("a recording", EmbeddingRole.DOCUMENT, audio_path="/tmp/a.wav")
                )
        self.assertIn("does not support audio", str(ctx.exception))

    def test_a_runtime_without_advertised_modalities_is_text_only(self):
        model, _runtime = self.make(modalities=())
        capabilities = model.capabilities()
        self.assertEqual(capabilities["input_modalities"], ["text"])

    def test_vector_is_truncated_to_the_profile_dimension_and_renormalised(self):
        model, _runtime = self.make()
        vector = model.embed_request(EmbeddingRequest("x", EmbeddingRole.DOCUMENT))
        self.assertEqual(len(vector), model.dimension())
        self.assertEqual(model.dimension(), 512)
        norm = math.sqrt(sum(value * value for value in vector))
        self.assertAlmostEqual(norm, 1.0, places=9)

    def test_a_wrong_runtime_identity_fails_closed(self):
        runtime = FakeRuntime()
        model = LlamaCppEmbeddingModel(device="cpu")

        def request(path, payload=None):
            if path == "/v1/models":
                return {"data": [{"id": "some-other-model"}]}
            raise AssertionError

        model._request = request
        with self.assertRaises(Exception) as ctx:
            model.embed_request(EmbeddingRequest("x", EmbeddingRole.DOCUMENT))
        self.assertIn("identity differs", str(ctx.exception))

    def test_a_malformed_model_response_fails_closed(self):
        model = LlamaCppEmbeddingModel(device="cpu")

        def request(path, payload=None):
            if path == "/v1/models":
                return {"data": None}
            raise AssertionError

        model._request = request
        with self.assertRaises(Exception) as ctx:
            model.embed_request(EmbeddingRequest("x", EmbeddingRole.DOCUMENT))
        self.assertIn("Invalid GGUF model identity response", str(ctx.exception))

    def test_capabilities_report_the_pinned_artefacts(self):
        model, _runtime = self.make()
        capabilities = model.capabilities()
        self.assertEqual(capabilities["quantization"], "Q8_0")
        self.assertEqual(capabilities["pooling"], "mean")
        self.assertEqual(capabilities["full_dimension"], 768)
        self.assertEqual(capabilities["index_dimension"], 512)
        self.assertEqual(capabilities["input_modalities"], ["audio", "image", "text", "video"])
        self.assertEqual(capabilities["model_id"], GEMMA_MODEL_ALIAS)


class EmbeddingRequestContractTests(unittest.TestCase):
    def test_at_most_one_media_input_is_accepted(self):
        with self.assertRaises(ValueError):
            EmbeddingRequest(
                "x", EmbeddingRole.DOCUMENT,
                image_path="/tmp/a.png", audio_path="/tmp/a.wav",
            )


@unittest.skipUnless(
    os.environ.get("PI_RUN_MULTIMODAL_TESTS") == "1",
    "set PI_RUN_MULTIMODAL_TESTS=1 with a running pinned llama.cpp runtime",
)
class RealMultimodalInferenceTests(unittest.TestCase):
    """Real inference against a pinned llama.cpp runtime.

    Enabled with ``PI_RUN_MULTIMODAL_TESTS=1`` and an endpoint that serves the
    pinned EmbeddingGemma 2 Q8_0 backbone and projector
    (``PI_LLAMA_ENDPOINT``, ``PI_LLAMA_API_KEY_FILE``).
    """

    def test_text_image_and_audio_return_valid_normalised_vectors(self):
        import base64
        import os
        import pathlib
        import urllib.error
        import urllib.request

        endpoint = os.environ.get("PI_LLAMA_ENDPOINT", "http://127.0.0.1:8769").rstrip("/")
        key_file = pathlib.Path(
            os.environ.get("PI_LLAMA_API_KEY_FILE", "/models/llama-api-key")
        )
        token = key_file.read_text().strip() if key_file.is_file() else ""
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token

        def post(payload):
            request = urllib.request.Request(
                endpoint + "/v1/embeddings",
                data=json.dumps(payload).encode(),
                headers=headers,
            )
            with urllib.request.urlopen(request, timeout=240) as response:
                return json.loads(response.read())

        with urllib.request.urlopen(
            urllib.request.Request(endpoint + "/v1/models", headers=headers), timeout=30
        ) as response:
            body = json.loads(response.read())
        modalities = body["data"][0]["architecture"]["input_modalities"]
        alias = body["data"][0]["id"]

        vector = post({"model": alias, "input": ["warehouse pallet packing process"],
                       "encoding_format": "float"})["data"][0]["embedding"]
        self.assertEqual(len(vector), 768)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in vector)), 1.0, places=6)

        if "image" in modalities:
            png = base64.b64encode(bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108020000009077"
                "3dfc0000000c4944415408d76360000002000154a24f5f0000000049454e"
                "44ae426082"
            )).decode()
            image = post({
                "model": alias,
                "input": [{"content": [
                    {"type": "text", "text": "a solid red square"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + png}},
                ]}],
                "encoding_format": "float",
            })["data"][0]["embedding"]
            self.assertEqual(len(image), 768)
            self.assertAlmostEqual(math.sqrt(sum(x * x for x in image)), 1.0, places=6)

        if "audio" in modalities:
            wave = base64.b64encode(bytes.fromhex(
                "524946462400080000002341000010006400000010000000646174610000"
                "000000"
            )).decode()
            audio = post({
                "model": alias,
                "input": [{"content": [
                    {"type": "text", "text": "a short recording"},
                    {"type": "input_audio", "input_audio": {"data": wave, "format": "wav"}},
                ]}],
                "encoding_format": "float",
            })["data"][0]["embedding"]
            self.assertEqual(len(audio), 768)
            self.assertAlmostEqual(math.sqrt(sum(x * x for x in audio)), 1.0, places=6)


if __name__ == "__main__":
    unittest.main()
