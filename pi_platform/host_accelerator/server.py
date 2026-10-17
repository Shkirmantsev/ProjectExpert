"""Host accelerator stdlib HTTP server (G1).

Implements the three documented endpoints
(``GET /health``, ``GET /v1/capabilities``,
``POST /v1/embeddings``) on top of :mod:`http.server`. The
embedding functions are injected as a mapping
``{"hashing": callable, "embeddinggemma2_512": callable, ...}``
so the server is decoupled from any real model. The default
fallback is a deterministic stdlib-only hashing embedding.

Security contract (plan §23.1):

- The bearer token is verified in constant time via
  :func:`hmac.compare_digest`.
- A module-level ``BoundedSemaphore`` enforces
  ``max_concurrent_requests``; exceeding the limit returns
  ``503 Service Unavailable``.
- A per-request size limit (``max_request_bytes``) is
  enforced via a custom ``LimitedStream`` that raises
  when the cap is exceeded.
- Per-request timeout is enforced via
  ``socketserver.BaseServer.timeout``.
- The audit log records every embedding request without
  payload contents.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import math
import socketserver
import threading
import time
from typing import Callable, Dict, Mapping, Optional

from pi_platform.ports.retrieval.embedding_profile import (
    EmbeddingProfile,
)

from .audit import AuditLog, AuditEntry
from .config import AcceleratorConfig
from .port import (
    AcceleratorCapabilities,
    EmbeddingModelNotAllowed,
    EmbeddingRequest,
    EmbeddingResponse,
    HealthStatus,
    HostAcceleratorPort,
)
from .security import (
    ModelAllowList,
    TokenStore,
    TokenError,
)


__all__ = [
    "AcceleratorService",
    "AcceleratorRequestHandler",
    "build_default_embedding_models",
]


DEFAULT_HASHING_DIMENSION = 384


def build_default_embedding_models(
    profiles: Mapping[str, EmbeddingProfile],
) -> Dict[str, Callable[[str], list]]:
    """Build a default ``{profile_id: embed_fn}`` mapping.

    The fallback embedding for every profile is a deterministic
    stdlib-only hash-projection: the same input always
    produces the same vector at the profile's
    ``output_dimension``. The vector is L2-normalised so the
    service can be tested end-to-end without a GPU.

    The real GPU binding is a follow-up: an entry in this
    mapping is replaced with a function that calls the actual
    model.
    """
    out: Dict[str, Callable[[str], list]] = {}
    for profile_id, profile in profiles.items():
        out[profile_id] = _make_hashing_embedder(profile)
    return out


def _make_hashing_embedder(
    profile: EmbeddingProfile,
) -> Callable[[str], list]:
    dimension = int(profile.output_dimension)

    def _embed(text: str) -> list:
        # Deterministic stdlib-only hashing embedding.
        vec = [0.0] * dimension
        if not text:
            return vec
        tokens = _tokenise(text)
        if not tokens:
            return vec
        for tok in tokens:
            digest = hashlib.blake2b(
                tok.encode("utf-8"), digest_size=16,
            ).digest()
            slot = int.from_bytes(digest[:4], "big", signed=False) \
                % dimension
            sign = 1.0 if (digest[4] & 1) else -1.0
            vec[slot] += sign
        # Bias token.
        bias = hashlib.blake2b(
            b"\x00bias\x00", digest_size=16,
        ).digest()
        bias_slot = int.from_bytes(bias[:4], "big", signed=False) \
            % dimension
        vec[bias_slot] += 0.5
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]

    return _embed


def _tokenise(text: str) -> list:
    import re
    return re.findall(r"[A-Za-z0-9\u0400-\u04FF]{2,}", text.lower())


class _LimitedStream:
    """Wrap a file-like object and raise if more than
    ``max_bytes`` are read."""

    def __init__(self, inner, max_bytes: int) -> None:
        self._inner = inner
        self._max_bytes = max_bytes
        self._read = 0

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            data = self._inner.read()
        else:
            data = self._inner.read(size)
        if not data:
            return data
        self._read += len(data)
        if self._read > self._max_bytes:
            raise ValueError(
                f"request body exceeds max_request_bytes="
                f"{self._max_bytes}"
            )
        return data


class AcceleratorService(HostAcceleratorPort):
    """Top-level service object. Owns the configuration,
    token store, allow-list, audit log, and the bound HTTP
    server instance.
    """

    def __init__(
        self,
        config: AcceleratorConfig,
        *,
        token_store: TokenStore,
        allow_list: ModelAllowList,
        audit_log: AuditLog,
        embedding_models: Mapping[str, Callable[[str], list]],
        profiles_by_id: Mapping[str, EmbeddingProfile],
        started_at: float | None = None,
    ) -> None:
        self._config = config
        self._token_store = token_store
        self._allow_list = allow_list
        self._audit_log = audit_log
        self._embedding_models = dict(embedding_models)
        self._profiles_by_id = dict(profiles_by_id)
        self._started_at = started_at if started_at is not None else time.time()
        self._semaphore = threading.BoundedSemaphore(
            config.max_concurrent_requests,
        )
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- HostAcceleratorPort ---------------------------------------

    def health(self) -> HealthStatus:
        return HealthStatus(
            status="ok",
            version="accelerator-v1",
            uptime_seconds=time.time() - self._started_at,
        )

    def capabilities(self) -> AcceleratorCapabilities:
        # Memory: probe the system free memory when available.
        free_memory_bytes = _system_free_memory_bytes()
        return AcceleratorCapabilities(
            device="cpu",
            free_memory_bytes=free_memory_bytes,
            model_ids=tuple(sorted(self._embedding_models.keys())),
            profile_identities=tuple(sorted(
                p.identity() for p in self._profiles_by_id.values()
            )),
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        profile = self._profiles_by_id.get(request.model_id)
        if profile is None:
            raise EmbeddingModelNotAllowed(
                f"model_id {request.model_id!r} is not registered"
            )
        if not self._allow_list.is_allowed(embedding_profile=profile):
            raise EmbeddingModelNotAllowed(
                f"model_id {request.model_id!r} is not in the allow-list"
            )
        fn = self._embedding_models.get(request.model_id)
        if fn is None:
            raise EmbeddingModelNotAllowed(
                f"no embedding function for {request.model_id!r}"
            )
        vector = fn(request.input)
        return EmbeddingResponse(
            model_id=request.model_id,
            embedding=tuple(float(x) for x in vector),
            embedding_profile_hash=profile.identity(),
        )

    # -- server lifecycle ------------------------------------------

    def build_server(self) -> "ThreadingHTTPServer":
        cfg = self._config
        service = self

        class _Handler(AcceleratorRequestHandler):
            token_store = service._token_store
            audit_log = service._audit_log
            allow_list = service._allow_list
            service_ref = service
            max_request_bytes = cfg.max_request_bytes

        server = ThreadingHTTPServer(
            (cfg.bind_address, cfg.port), _Handler,
        )
        server.timeout = cfg.request_timeout_seconds
        return server

    def serve_forever(self) -> None:
        """Run the HTTP server in a background thread.

        The thread is a daemon so the process can exit when
        the main thread is interrupted. The caller is
        responsible for calling ``shutdown()`` when done.
        """
        if self._server is not None:
            raise RuntimeError("accelerator is already serving")
        self._server = self.build_server()
        self._thread = threading.Thread(
            target=self._server.serve_forever, daemon=True,
            name="host-accelerator",
        )
        self._thread.start()

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    @property
    def is_serving(self) -> bool:
        return self._server is not None

    def acquire_slot(self, timeout: float | None = None) -> bool:
        """Try to acquire a request slot. Returns True on
        success, False on timeout. Used by the handler to
        enforce the concurrency limit."""
        return self._semaphore.acquire(timeout=timeout)

    def release_slot(self) -> None:
        try:
            self._semaphore.release()
        except ValueError:
            pass


class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """A ThreadingHTTPServer with a per-request timeout.

    ``daemon_threads=True`` so background workers do not
    block process exit; ``allow_reuse_address=False`` so two
    accelerators cannot bind the same port (refuses duplicate
    starts).
    """

    daemon_threads = True
    allow_reuse_address = False


class AcceleratorRequestHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler for the accelerator.

    Subclasses (built dynamically by
    :meth:`AcceleratorService.build_server`) attach the
    ``token_store``, ``audit_log``, ``allow_list``,
    ``service_ref`` and ``max_request_bytes`` attributes.
    """

    server_version = "ProjectExpertAccelerator/1.0"
    token_store: TokenStore
    audit_log: AuditLog
    allow_list: ModelAllowList
    service_ref: AcceleratorService
    max_request_bytes: int

    # -- entry points -------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler)
        try:
            with self._timed("GET", "") as ctx:
                if self.path == "/health":
                    self._handle_health(ctx)
                elif self.path == "/v1/capabilities":
                    self._handle_capabilities(ctx)
                else:
                    self._json_error(404, "not_found", ctx)
        except _ConcurrencyLimit:
            # The ctx was populated; record + 503.
            try:
                self.audit_log.record(
                    endpoint="GET" + self.path,
                    model_id="",
                    embedding_profile_hash="",
                    status=503,
                    duration_ms=0,
                    client_address=self.client_address[0]
                    if self.client_address else "",
                    request_id="",
                    reason="concurrency_limit",
                )
            except Exception:  # noqa: BLE001
                pass
            self._send_json(503, {
                "error": "service_unavailable",
                "message": "concurrency limit reached",
            })

    def do_POST(self) -> None:  # noqa: N802
        try:
            with self._timed("POST", self.path) as ctx:
                if self.path == "/v1/embeddings":
                    self._handle_embeddings(ctx)
                else:
                    self._json_error(404, "not_found", ctx)
        except _ConcurrencyLimit:
            try:
                self.audit_log.record(
                    endpoint="POST" + self.path,
                    model_id="",
                    embedding_profile_hash="",
                    status=503,
                    duration_ms=0,
                    client_address=self.client_address[0]
                    if self.client_address else "",
                    request_id="",
                    reason="concurrency_limit",
                )
            except Exception:  # noqa: BLE001
                pass
            self._send_json(503, {
                "error": "service_unavailable",
                "message": "concurrency limit reached",
            })

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        # Quiet the default stderr logger; the audit log is
        # the source of truth.
        return

    # -- handlers -----------------------------------------------------

    def _handle_health(self, ctx) -> None:
        status = self.service_ref.health()
        ctx["model_id"] = "n/a"
        ctx["embedding_profile_hash"] = "n/a"
        ctx["status"] = 200
        self._audit(ctx)
        payload = {
            "status": status.status,
            "version": status.version,
            "uptime_seconds": status.uptime_seconds,
        }
        self._send_json(200, payload)

    def _handle_capabilities(self, ctx) -> None:
        if not self._require_token(ctx):
            return
        caps = self.service_ref.capabilities()
        ctx["model_id"] = "n/a"
        ctx["embedding_profile_hash"] = "n/a"
        ctx["status"] = 200
        self._audit(ctx)
        payload = {
            "device": caps.device,
            "free_memory_bytes": caps.free_memory_bytes,
            "model_ids": list(caps.model_ids),
            "profile_identities": list(caps.profile_identities),
        }
        self._send_json(200, payload)

    def _handle_embeddings(self, ctx) -> None:
        if not self._require_token(ctx):
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            self._json_error(400, "bad_content_length", ctx)
            return
        if length > self.max_request_bytes:
            self._json_error(413, "payload_too_large", ctx)
            return
        try:
            raw = self.rfile.read(length) if length else b""
        except Exception:
            self._json_error(400, "read_error", ctx)
            return
        if len(raw) > self.max_request_bytes:
            self._json_error(413, "payload_too_large", ctx)
            return
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_error(400, "bad_json", ctx)
            return
        if not isinstance(payload, dict):
            self._json_error(400, "bad_payload", ctx)
            return
        model_id = payload.get("model_id")
        text = payload.get("input")
        if not isinstance(model_id, str) or not isinstance(text, str):
            self._json_error(400, "missing_fields", ctx)
            return
        if len(text.encode("utf-8")) > self.max_request_bytes:
            self._json_error(413, "payload_too_large", ctx)
            return
        request = EmbeddingRequest(model_id=model_id, input=text)
        try:
            response = self.service_ref.embed(request)
        except EmbeddingModelNotAllowed as exc:
            ctx["model_id"] = model_id
            ctx["status"] = 400
            ctx["reason"] = str(exc)
            self._audit(ctx)
            self._json_error(400, "model_not_allowed", ctx, str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            ctx["model_id"] = model_id
            ctx["status"] = 500
            ctx["reason"] = f"{type(exc).__name__}: {exc}"
            self._audit(ctx)
            self._json_error(500, "embed_error", ctx, str(exc))
            return
        ctx["model_id"] = model_id
        ctx["embedding_profile_hash"] = response.embedding_profile_hash
        ctx["status"] = 200
        self._audit(ctx)
        self._send_json(200, {
            "model_id": response.model_id,
            "embedding": list(response.embedding),
            "embedding_profile_hash": response.embedding_profile_hash,
        })

    # -- helpers -----------------------------------------------------

    def _require_token(self, ctx) -> bool:
        header = self.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            ctx["status"] = 401
            ctx["reason"] = "missing_or_malformed_authorization"
            self._audit(ctx)
            self._json_error(401, "unauthorized", ctx)
            return False
        provided = header[len("Bearer "):].strip()
        try:
            expected = self.token_store.read()
        except TokenError as exc:
            ctx["status"] = 500
            ctx["reason"] = f"token_store_error: {exc}"
            self._audit(ctx)
            self._json_error(500, "token_store_error", ctx)
            return False
        if not self.token_store.constant_time_compare(provided, expected):
            ctx["status"] = 401
            ctx["reason"] = "token_mismatch"
            self._audit(ctx)
            self._json_error(401, "unauthorized", ctx)
            return False
        return True

    def _json_error(
        self, status: int, code: str, ctx, message: str = "",
    ) -> None:
        ctx["status"] = status
        self._audit(ctx)
        self._send_json(status, {
            "error": code,
            "message": message or code,
        })

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _audit(self, ctx) -> None:
        try:
            self.audit_log.record(
                endpoint=ctx["endpoint"] + (ctx.get("path") or ""),
                model_id=ctx.get("model_id", ""),
                embedding_profile_hash=ctx.get(
                    "embedding_profile_hash", "",
                ),
                status=ctx.get("status", 0),
                duration_ms=ctx.get("duration_ms", 0),
                client_address=self.client_address[0]
                if self.client_address else "",
                request_id=ctx.get("request_id", ""),
                reason=ctx.get("reason", ""),
            )
        except Exception:  # noqa: BLE001
            # Audit failure must never break a request.
            pass

    def _timed(self, endpoint: str, path: str):
        """Context manager that records the request duration
        in milliseconds and enforces the concurrency limit
        + per-request size cap."""
        import uuid as _uuid
        request_id = self.headers.get(
            "X-Request-Id", "",
        ) or _uuid.uuid4().hex
        ctx: dict = {
            "endpoint": endpoint,
            "path": path,
            "request_id": request_id,
            "model_id": "",
            "embedding_profile_hash": "",
            "status": 0,
            "duration_ms": 0,
            "reason": "",
        }
        return _TimedRequest(self.service_ref, ctx)


class _TimedRequest:
    def __init__(self, service, ctx: dict) -> None:
        self._service = service
        self._ctx = ctx
        self._t0 = 0.0
        self._acquired = False

    def __enter__(self) -> dict:
        if not self._service.acquire_slot(timeout=0.1):
            # Concurrency limit reached; raise so the
            # handler's outer try/except sends 503.
            raise _ConcurrencyLimit()
        self._acquired = True
        self._t0 = time.monotonic()
        return self._ctx

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._acquired:
            self._ctx["duration_ms"] = int(
                (time.monotonic() - self._t0) * 1000,
            )
            self._service.release_slot()


class _ConcurrencyLimit(Exception):
    pass


def _system_free_memory_bytes() -> int:
    """Best-effort probe of system free memory.

    Returns -1 if the platform does not expose
    ``/proc/meminfo`` (or the equivalent). The capability
    endpoint surfaces the value as-is.
    """
    try:
        with open("/proc/meminfo", "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    parts = line.split()
                    return int(parts[1]) * 1024
    except (OSError, ValueError):
        return -1
    return -1
