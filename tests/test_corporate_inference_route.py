import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

from pi_platform.adapters.retrieval.llama_cpp_embedding_model import LlamaCppEmbeddingModel
from pi_platform.deployment.native_route import verify_native_route
from pi_platform.ports.retrieval.embedding_model import EmbeddingModelError


class NativeRouteTests(unittest.TestCase):
    def test_wrong_engine_gateway_falls_back_to_verified_windows_interface(self):
        token = "x" * 64
        answers = {
            "host.docker.internal": ["172.17.0.1"],
            "host.rancher-desktop.internal": ["172.17.0.1", "203.0.113.42"],
        }
        requests = []

        def open_request(request, *, timeout):
            if isinstance(request, str):
                requests.append((request, None))
                if "172.17.0.1" in request:
                    raise URLError(ConnectionRefusedError())
                raise HTTPError(request, 401, "Unauthorized", {}, io.BytesIO())
            self.assertIsInstance(request, Request)
            requests.append((request.full_url, request.get_header("Authorization")))
            if request.full_url.endswith("/v1/models"):
                result = {"data": [{"id": "pinned-model"}]}
            else:
                self.assertTrue(json.loads(request.data)["input"])
                result = {"data": [{"embedding": [0.125] * 768}]}
            return io.BytesIO(json.dumps(result).encode())

        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key"
            key.write_text(token, encoding="ascii")
            with patch("pi_platform.deployment.native_route.socket.gethostbyname_ex",
                       side_effect=lambda name: (name, [], answers[name])), patch(
                           "pi_platform.deployment.native_route.build_opener") as build:
                build.return_value.open.side_effect = open_request
                result = verify_native_route(port=9009, model="pinned-model",
                                             host_ips=["172.20.0.1"], key_file=key)
        self.assertEqual(result["endpoint"], "http://172.20.0.1:9009")
        self.assertEqual(result["attempts"], [
            {"route": "host.docker.internal", "code": "connection_refused"},
        ])
        self.assertEqual(requests[:2], [
            ("http://172.17.0.1:9009/v1/models", None),
            ("http://172.20.0.1:9009/v1/models", None),
        ])
        self.assertEqual(requests[2:], [
            ("http://172.20.0.1:9009/v1/models", "Bearer " + token),
            ("http://172.20.0.1:9009/v1/embeddings", "Bearer " + token),
        ])

    def test_wrong_model_never_receives_embedding_input(self):
        with tempfile.TemporaryDirectory() as directory:
            key = Path(directory) / "key"
            key.write_text("x" * 64, encoding="ascii")
            with patch("pi_platform.deployment.native_route.socket.gethostbyname_ex",
                       return_value=("", [], ["172.17.0.1"])), patch(
                           "pi_platform.deployment.native_route.build_opener") as build:
                build.return_value.open.side_effect = [
                    HTTPError("", 401, "Unauthorized", {}, io.BytesIO()),
                    io.BytesIO(b'{"data": [{"id": "other"}]}'),
                ]
                result = verify_native_route(port=8769, model="pinned-model", host_ips=[], key_file=key)
                self.assertEqual(build.return_value.open.call_count, 2)
        self.assertFalse(result["ok"])
        self.assertEqual(result["attempts"][0]["code"], "wrong_model")

    def test_tokenless_client_uses_only_configured_private_sidecar(self):
        with patch.dict(os.environ, {"PI_LLAMA_AUTH": "none", "PI_LLAMA_DIRECT": "1"}):
            with self.assertRaises(EmbeddingModelError):
                LlamaCppEmbeddingModel(endpoint="http://172.20.0.1:9009")
            model = LlamaCppEmbeddingModel(endpoint="http://embeddings:9009", key_file="/absent")
            with patch("urllib.request.build_opener") as build:
                build.return_value.open.return_value = io.BytesIO(
                    json.dumps({"data": [{"id": model.runtime_alias}]}).encode()
                )
                self.assertEqual(model.capabilities()["model_id"], model.runtime_alias)
                request = build.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, "http://embeddings:9009/v1/models")
                self.assertIsNone(request.get_header("Authorization"))

    def test_tokenless_probe_uses_only_the_verified_host_addresses(self):
        with patch("pi_platform.deployment.native_route.socket.gethostbyname_ex") as dns, patch(
                "pi_platform.deployment.native_route.build_opener") as build:
            build.return_value.open.side_effect = [
                io.BytesIO(b'{"data": [{"id": "pinned"}]}'),
                io.BytesIO(json.dumps({"data": [{"embedding": [0.25] * 768}]}).encode()),
            ]
            result = verify_native_route(port=9009, model="pinned", host_ips=["172.20.0.1"],
                                         key_file=Path("/absent"), auth="none", host_only=True)
            dns.assert_not_called()
            self.assertEqual(result["endpoint"], "http://172.20.0.1:9009")
            for request in build.return_value.open.call_args_list:
                self.assertIsNone(request.args[0].get_header("Authorization"))
