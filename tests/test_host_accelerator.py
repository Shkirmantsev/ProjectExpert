"""Tests for the host accelerator (G)."""

from __future__ import annotations

import http.client
import json
import os
import socket
import tempfile
import threading
import time
import unittest
from typing import Optional

from pi_platform.host_accelerator.audit import AuditLog, AuditEntry
from pi_platform.host_accelerator.bootstrap import (
    bootstrap_all,
    bootstrap_token,
    ensure_allow_list_file,
    ensure_audit_log,
)
from pi_platform.host_accelerator.config import (
    AcceleratorConfig,
    BindAddressError,
    DEFAULT_AUDIT_LOG_PATH,
    DEFAULT_TOKEN_PATH,
)
from pi_platform.host_accelerator.security import (
    AllowListError,
    DEFAULT_ALLOWED_IDENTITIES,
    ModelAllowList,
    TokenError,
    TokenStore,
)
from pi_platform.host_accelerator.server import (
    AcceleratorService,
    build_default_embedding_models,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    HASHING_DEFAULT,
    EmbeddingProfile,
)


def _free_port() -> int:
    """Find a free TCP port by binding to 0."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _tmp_root() -> str:
    tmp = tempfile.mkdtemp(prefix="accel-test-")
    return tmp


class AcceleratorConfigTests(unittest.TestCase):
    def test_defaults(self) -> None:
        cfg = AcceleratorConfig()
        self.assertEqual(cfg.bind_address, "127.0.0.1")
        self.assertEqual(cfg.port, 8791)

    def test_loopback_allowed(self) -> None:
        cfg = AcceleratorConfig(bind_address="127.0.0.1")
        self.assertEqual(cfg.bind_address, "127.0.0.1")

    def test_public_bind_rejected(self) -> None:
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(bind_address="8.8.8.8")

    def test_private_bind_requires_allow_wide_bind(self) -> None:
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(bind_address="10.0.0.1")
        # allow_wide_bind=True permits private binds.
        cfg = AcceleratorConfig(
            bind_address="10.0.0.1", allow_wide_bind=True,
        )
        self.assertEqual(cfg.bind_address, "10.0.0.1")

    def test_invalid_ip_rejected(self) -> None:
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(bind_address="not-an-ip")

    def test_invalid_port_rejected(self) -> None:
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(port=0)
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(port=70000)

    def test_negative_params_rejected(self) -> None:
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(max_request_bytes=0)
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(request_timeout_seconds=0)
        with self.assertRaises(BindAddressError):
            AcceleratorConfig(max_concurrent_requests=0)


class TokenStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))
        self._path = os.path.join(self._tmp, "token")

    def test_write_read_round_trip(self) -> None:
        s = TokenStore(self._path)
        s.write("abc123def456")
        self.assertEqual(s.read(), "abc123def456")

    def test_missing_token_raises(self) -> None:
        s = TokenStore(self._path)
        with self.assertRaises(TokenError):
            s.read()

    def test_rotate_generates_new_token(self) -> None:
        s = TokenStore(self._path)
        original = s.rotate()
        self.assertGreater(len(original), 30)
        # Second rotation produces a different token.
        rotated = s.rotate()
        self.assertNotEqual(original, rotated)
        # The new value is the persisted one.
        self.assertEqual(s.read(), rotated)

    def test_delete_removes_file(self) -> None:
        s = TokenStore(self._path)
        s.write("x")
        self.assertTrue(s.exists())
        s.delete()
        self.assertFalse(s.exists())
        # Idempotent.
        s.delete()

    def test_empty_token_raises(self) -> None:
        s = TokenStore(self._path)
        with self.assertRaises(TokenError):
            s.write("")

    def test_constant_time_compare(self) -> None:
        s = TokenStore(self._path)
        self.assertTrue(s.constant_time_compare("abc", "abc"))
        self.assertFalse(s.constant_time_compare("abc", "abd"))
        # Different lengths.
        self.assertFalse(s.constant_time_compare("a", "ab"))


class ModelAllowListTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))
        self._path = os.path.join(self._tmp, "allow.json")

    def test_default_contains_builtins(self) -> None:
        al = ModelAllowList(self._path)
        # The default is the three built-in identities.
        self.assertIn(HASHING_DEFAULT.identity(), al.identities)
        self.assertIn(EMBEDDINGGEMMA2_512.identity(), al.identities)
        # The third is QWEN3.
        self.assertEqual(len(al.identities), 3)
        # Persisted to disk.
        self.assertTrue(os.path.isfile(self._path))

    def test_is_allowed_default(self) -> None:
        al = ModelAllowList(self._path)
        self.assertTrue(al.is_allowed(embedding_profile=HASHING_DEFAULT))
        self.assertFalse(al.is_allowed(embedding_profile=EmbeddingProfile(
            provider="custom", model_id="x", model_revision="v",
            modality="text", output_dimension=128, normalization="l2",
            instruction_profile="default", tokenizer_id="x/v",
            strategy_version="x",
        )))

    def test_register_and_persist(self) -> None:
        al = ModelAllowList(self._path)
        custom = EmbeddingProfile(
            provider="custom", model_id="custom-1",
            model_revision="r1", modality="text",
            output_dimension=256, normalization="l2",
            instruction_profile="default",
            tokenizer_id="custom/v1",
            strategy_version="custom-v1",
        )
        al.register(custom)
        self.assertTrue(al.is_allowed(embedding_profile=custom))
        # Reload from disk: the new identity is persisted.
        al2 = ModelAllowList(self._path)
        self.assertIn(custom.identity(), al2.identities)

    def test_unregister(self) -> None:
        al = ModelAllowList(self._path)
        al.unregister(HASHING_DEFAULT)
        self.assertNotIn(HASHING_DEFAULT.identity(), al.identities)


class AuditLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))
        self._path = os.path.join(self._tmp, "audit.jsonl")

    def test_record_writes_jsonl(self) -> None:
        log = AuditLog(self._path)
        entry = log.record(
            endpoint="POST/v1/embeddings", model_id="hashing",
            embedding_profile_hash=HASHING_DEFAULT.identity(),
            status=200, duration_ms=12,
            client_address="127.0.0.1",
        )
        self.assertTrue(os.path.isfile(self._path))
        with open(self._path, "r", encoding="utf-8") as f:
            line = f.read().strip()
        self.assertEqual(json.loads(line)["status"], 200)
        self.assertEqual(json.loads(line)["model_id"], "hashing")

    def test_record_omits_payload_fields(self) -> None:
        log = AuditLog(self._path)
        log.record(
            endpoint="POST/v1/embeddings", model_id="hashing",
            embedding_profile_hash=HASHING_DEFAULT.identity(),
            status=200, duration_ms=1,
            client_address="127.0.0.1",
        )
        with open(self._path, "r", encoding="utf-8") as f:
            line = f.read().strip()
        # The audit entry must NOT contain payload-bearing
        # fields as top-level keys. The endpoint string
        # itself may contain the substring ``embedding`` as
        # part of the route name, so the test inspects the
        # parsed JSON.
        entry = json.loads(line)
        self.assertNotIn("input", entry)
        self.assertNotIn("embedding", entry)
        self.assertNotIn("payload", entry)
        self.assertNotIn("body", entry)

    def test_read_recent(self) -> None:
        log = AuditLog(self._path)
        for i in range(3):
            log.record(
                endpoint="GET/health", model_id="",
                embedding_profile_hash="", status=200,
                duration_ms=1, client_address="127.0.0.1",
            )
        recent = log.read_recent(limit=10)
        self.assertEqual(len(recent), 3)


class BootstrapTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))
        self._config = AcceleratorConfig(
            token_path=os.path.join(self._tmp, "token"),
            audit_log_path=os.path.join(self._tmp, "audit.jsonl"),
            allow_list_path=os.path.join(self._tmp, "allow.json"),
        )

    def test_bootstrap_token_creates_file_when_missing(self) -> None:
        token = bootstrap_token(self._config)
        self.assertGreater(len(token), 30)
        self.assertTrue(os.path.isfile(self._config.token_path))
        # Reading again returns the same token.
        self.assertEqual(bootstrap_token(self._config), token)

    def test_bootstrap_token_is_idempotent(self) -> None:
        token1 = bootstrap_token(self._config)
        token2 = bootstrap_token(self._config)
        self.assertEqual(token1, token2)

    def test_ensure_audit_log_creates_directory(self) -> None:
        log = ensure_audit_log(self._config)
        self.assertTrue(
            os.path.isdir(os.path.dirname(self._config.audit_log_path)),
        )
        # Recording works.
        log.record(
            endpoint="GET/health", model_id="", embedding_profile_hash="",
            status=200, duration_ms=1, client_address="127.0.0.1",
        )

    def test_ensure_allow_list_file_registers_defaults(self) -> None:
        al = ensure_allow_list_file(self._config)
        self.assertEqual(len(al.identities), 3)
        self.assertTrue(os.path.isfile(self._config.allow_list_path))

    def test_bootstrap_all(self) -> None:
        token, log, al = bootstrap_all(self._config)
        self.assertGreater(len(token), 30)
        self.assertIsNotNone(log)
        self.assertEqual(len(al.identities), 3)


class AcceleratorHttpTests(unittest.TestCase):
    """In-process HTTP server tests using a real
    ThreadingHTTPServer on a random port."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = _tmp_root()
        cls.addClassCleanup(lambda: __import__("shutil").rmtree(
            cls._tmp, ignore_errors=True,
        ))
        port = _free_port()
        cls._port = port
        cls._base_url = f"http://127.0.0.1:{port}"
        config = AcceleratorConfig(
            bind_address="127.0.0.1",
            port=port,
            token_path=os.path.join(cls._tmp, "token"),
            audit_log_path=os.path.join(cls._tmp, "audit.jsonl"),
            allow_list_path=os.path.join(cls._tmp, "allow.json"),
            max_request_bytes=4096,
            max_concurrent_requests=2,
        )
        token, log, al = bootstrap_all(config)
        profiles = {
            HASHING_DEFAULT.identity(): HASHING_DEFAULT,
            EMBEDDINGGEMMA2_512.identity(): EMBEDDINGGEMMA2_512,
        }
        embedding_models = build_default_embedding_models(profiles)
        cls._token = token
        cls._token_path = config.token_path
        cls._audit_log = log
        cls._service = AcceleratorService(
            config=config, token_store=TokenStore(config.token_path),
            allow_list=al, audit_log=log,
            embedding_models=embedding_models,
            profiles_by_id=profiles,
        )
        cls._service.serve_forever()
        # Give the server a moment to start.
        time.sleep(0.05)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._service.shutdown()

    def _get(self, path: str, headers: Optional[dict] = None) -> tuple:
        h = dict(headers or {})
        if "Authorization" not in h:
            h["Authorization"] = "Bearer " + self._token
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=5)
        conn.request("GET", path, headers=h)
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def _post(self, path: str, payload: dict, headers: Optional[dict] = None) -> tuple:
        h = {"Content-Type": "application/json"}
        if headers:
            h.update(headers)
        if "Authorization" not in h:
            h["Authorization"] = "Bearer " + self._token
        body = json.dumps(payload).encode("utf-8")
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=5)
        conn.request("POST", path, body=body, headers=h)
        resp = conn.getresponse()
        resp_body = resp.read()
        conn.close()
        return resp.status, resp_body

    def test_health_no_auth_required(self) -> None:
        conn = http.client.HTTPConnection("127.0.0.1", self._port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        self.assertEqual(resp.status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["version"], "accelerator-v1")
        self.assertGreaterEqual(payload["uptime_seconds"], 0.0)

    def test_capabilities_requires_token(self) -> None:
        status, body = self._get(
            "/v1/capabilities", headers={"Authorization": ""},
        )
        self.assertEqual(status, 401)

    def test_capabilities_wrong_token_rejected(self) -> None:
        status, _ = self._get(
            "/v1/capabilities", headers={"Authorization": "Bearer wrong"},
        )
        self.assertEqual(status, 401)

    def test_capabilities_with_token(self) -> None:
        status, body = self._get("/v1/capabilities")
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["device"], "cpu")
        self.assertIn(HASHING_DEFAULT.identity(), payload["profile_identities"])
        self.assertIn(HASHING_DEFAULT.identity(), payload["model_ids"])

    def test_embeddings_with_token(self) -> None:
        status, body = self._post("/v1/embeddings", {
            "model_id": HASHING_DEFAULT.identity(),
            "input": "hello world",
        })
        self.assertEqual(status, 200)
        payload = json.loads(body)
        self.assertEqual(payload["model_id"], HASHING_DEFAULT.identity())
        self.assertEqual(payload["embedding_profile_hash"],
                         HASHING_DEFAULT.identity())
        self.assertEqual(len(payload["embedding"]), HASHING_DEFAULT.output_dimension)

    def test_embeddings_disallowed_model(self) -> None:
        status, body = self._post("/v1/embeddings", {
            "model_id": "unknown-model",
            "input": "hello",
        })
        self.assertEqual(status, 400)
        payload = json.loads(body)
        self.assertEqual(payload["error"], "model_not_allowed")

    def test_embeddings_missing_token(self) -> None:
        status, body = self._post(
            "/v1/embeddings",
            {"model_id": HASHING_DEFAULT.identity(), "input": "x"},
            headers={"Authorization": ""},
        )
        self.assertEqual(status, 401)

    def test_404_not_found(self) -> None:
        status, _ = self._get("/does-not-exist")
        self.assertEqual(status, 404)

    def test_audit_log_records_requests(self) -> None:
        # Issue a few requests, then read the audit log.
        self._get("/health")
        self._get("/v1/capabilities")
        self._post("/v1/embeddings", {
            "model_id": HASHING_DEFAULT.identity(),
            "input": "hello",
        })
        recent = self._audit_log.read_recent(limit=10)
        # At least three entries since the start.
        self.assertGreaterEqual(len(recent), 3)
        # No entry contains the input text or the embedding.
        for entry in recent:
            self.assertNotIn("input", entry)
            self.assertNotIn("embedding", entry)


class HostEmbeddingClientTests(unittest.TestCase):
    """The container-side client (G4)."""

    def setUp(self) -> None:
        self._tmp = _tmp_root()
        self.addCleanup(lambda: __import__("shutil").rmtree(
            self._tmp, ignore_errors=True,
        ))

    def _bootstrap_accelerator(self) -> tuple:
        port = _free_port()
        config = AcceleratorConfig(
            bind_address="127.0.0.1",
            port=port,
            token_path=os.path.join(self._tmp, f"token-{port}"),
            audit_log_path=os.path.join(
                self._tmp, f"audit-{port}.jsonl",
            ),
            allow_list_path=os.path.join(
                self._tmp, f"allow-{port}.json",
            ),
        )
        token, log, al = bootstrap_all(config)
        profiles = {
            HASHING_DEFAULT.identity(): HASHING_DEFAULT,
        }
        embedding_models = build_default_embedding_models(profiles)
        service = AcceleratorService(
            config=config, token_store=TokenStore(config.token_path),
            allow_list=al, audit_log=log,
            embedding_models=embedding_models,
            profiles_by_id=profiles,
        )
        service.serve_forever()
        time.sleep(0.05)
        return service, config, token

    def test_uses_accelerator_when_reachable(self) -> None:
        from pi_platform.adapters.retrieval.hashing_embedding_model import (
            HashingEmbeddingModel,
        )
        service, config, _ = self._bootstrap_accelerator()
        self.addCleanup(service.shutdown)
        # Build a CPU fallback (used only if accelerator fails).
        fallback = HashingEmbeddingModel()
        from pi_platform.adapters.retrieval.host_embedding_client import (
            HostEmbeddingClient,
        )
        client = HostEmbeddingClient(
            accelerator_url=f"http://127.0.0.1:{config.port}",
            token_path=config.token_path,
            allow_list_path=config.allow_list_path,
            profile=HASHING_DEFAULT,
            fallback=fallback,
        )
        vec = client.embed("hello world")
        self.assertEqual(len(vec), HASHING_DEFAULT.output_dimension)
        stats = client.stats()
        self.assertEqual(stats["requests"], 1)
        self.assertEqual(stats["fallbacks"], 0)

    def test_falls_back_on_missing_token(self) -> None:
        from pi_platform.adapters.retrieval.hashing_embedding_model import (
            HashingEmbeddingModel,
        )
        fallback = HashingEmbeddingModel()
        from pi_platform.adapters.retrieval.host_embedding_client import (
            HostEmbeddingClient,
        )
        client = HostEmbeddingClient(
            accelerator_url="http://127.0.0.1:9999",
            token_path=os.path.join(self._tmp, "no-token"),
            allow_list_path=os.path.join(self._tmp, "no-allow.json"),
            profile=HASHING_DEFAULT,
            fallback=fallback,
        )
        vec = client.embed("hello")
        self.assertEqual(len(vec), HASHING_DEFAULT.output_dimension)
        self.assertEqual(client.stats()["fallbacks"], 1)

    def test_raises_when_no_fallback_and_token_missing(self) -> None:
        from pi_platform.adapters.retrieval.host_embedding_client import (
            HostEmbeddingClient,
        )
        from pi_platform.ports.retrieval.embedding_model import (
            EmbeddingModelError,
        )
        client = HostEmbeddingClient(
            accelerator_url="http://127.0.0.1:9999",
            token_path=os.path.join(self._tmp, "no-token"),
            allow_list_path=os.path.join(self._tmp, "no-allow.json"),
            profile=HASHING_DEFAULT,
            fallback=None,
        )
        with self.assertRaises(EmbeddingModelError):
            client.embed("hello")

    def test_falls_back_on_unreachable_accelerator(self) -> None:
        from pi_platform.adapters.retrieval.hashing_embedding_model import (
            HashingEmbeddingModel,
        )
        from pi_platform.adapters.retrieval.host_embedding_client import (
            HostEmbeddingClient,
        )
        # Write a token file so the client does not fall back
        # for the wrong reason.
        token_path = os.path.join(self._tmp, "token")
        TokenStore(token_path).write("some-token")
        fallback = HashingEmbeddingModel()
        client = HostEmbeddingClient(
            accelerator_url="http://127.0.0.1:1",  # not listening
            token_path=token_path,
            allow_list_path=os.path.join(self._tmp, "no-allow.json"),
            profile=HASHING_DEFAULT,
            fallback=fallback,
            timeout_seconds=0.5,
        )
        vec = client.embed("hello")
        self.assertEqual(len(vec), HASHING_DEFAULT.output_dimension)
        self.assertEqual(client.stats()["fallbacks"], 1)
        self.assertGreaterEqual(client.stats()["errors"], 1)

    def test_dimension_and_model_version(self) -> None:
        from pi_platform.adapters.retrieval.host_embedding_client import (
            HostEmbeddingClient,
        )
        client = HostEmbeddingClient(
            accelerator_url="http://127.0.0.1:1",
            token_path=os.path.join(self._tmp, "no-token"),
            allow_list_path=os.path.join(self._tmp, "no-allow.json"),
            profile=HASHING_DEFAULT,
            fallback=None,
        )
        self.assertEqual(client.dimension(), 384)
        self.assertEqual(
            client.model_version(), HASHING_DEFAULT.identity(),
        )

    def test_stats_after_fallback(self) -> None:
        from pi_platform.adapters.retrieval.hashing_embedding_model import (
            HashingEmbeddingModel,
        )
        from pi_platform.adapters.retrieval.host_embedding_client import (
            HostEmbeddingClient,
        )
        client = HostEmbeddingClient(
            accelerator_url="http://127.0.0.1:1",
            token_path=os.path.join(self._tmp, "no-token"),
            allow_list_path=os.path.join(self._tmp, "no-allow.json"),
            profile=HASHING_DEFAULT,
            fallback=HashingEmbeddingModel(),
        )
        client.embed("a")
        client.embed("b")
        stats = client.stats()
        self.assertEqual(stats["fallbacks"], 2)
        self.assertEqual(stats["accelerator_url"], "http://127.0.0.1:1")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
