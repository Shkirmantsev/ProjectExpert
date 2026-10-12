"""HTTP adapter for the UI API (architecture §57, §44.3).

This module is an adapter: it translates HTTP into ``RestApiPort`` calls and
never owns domain behaviour. It uses the Python standard library only, binds to
the loopback interface by default and refuses every request that does not
present the configured bearer token.
"""

from __future__ import annotations

import dataclasses
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Optional
from urllib.parse import parse_qs, urlparse

from pi_platform.core.ui.rest_service import UiOperationDenied
from pi_platform.ports.ui.rest_api import (
    AgentDelegationRequest,
    GraphRequest,
    MaterializeRequest,
    QueryRequest,
    RestApiPort,
    RetrieveRequest,
    UiActor,
    WikiRequest,
)

__all__ = ["UiHttpServer", "DEFAULT_HOST", "STATIC_ROOT"]

DEFAULT_HOST = "127.0.0.1"
STATIC_ROOT = Path(__file__).resolve().parent / "static"

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}


def _jsonable(value: Any) -> Any:
    """Convert a result payload into JSON-serialisable primitives."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _jsonable(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _jsonable(
            {k: v for k, v in vars(value).items() if not k.startswith("_")}
        )
    return str(value)


class UiHttpServer:
    """Threaded stdlib HTTP server exposing the UI API and the static UI."""

    def __init__(
        self,
        service: RestApiPort,
        *,
        host: str = DEFAULT_HOST,
        port: int = 0,
        token: Optional[str] = None,
        static_root: Optional[Path] = None,
        readiness: Optional[Callable[[], bool]] = None,
        actor: Optional[UiActor] = None,
        openai_compat: Optional[Any] = None,
    ) -> None:
        self.service = service
        self.host = host
        self._requested_port = port
        self.token = token if token is not None else os.environ.get("PI_UI_TOKEN") or None
        self.static_root = Path(static_root) if static_root else STATIC_ROOT
        self._readiness = readiness or (lambda: False)
        self.openai_compat = openai_compat
        self.actor = actor or UiActor(
            actor_type="human",
            actor_id=os.environ.get("PI_UI_ACTOR_ID", "operator"),
            role=os.environ.get("PI_UI_ROLE", "viewer"),
        )
        self._httpd: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # -- lifecycle -----------------------------------------------------
    def start_background(self) -> "UiHttpServer":
        if self._httpd is not None:
            raise RuntimeError("server already started")
        handler = _build_handler(self)
        self._httpd = ThreadingHTTPServer((self.host, self._requested_port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever, name="pi-ui-server", daemon=True
        )
        self._thread.start()
        return self

    def serve_forever(self) -> None:  # pragma: no cover - blocking entry point
        handler = _build_handler(self)
        self._httpd = ThreadingHTTPServer((self.host, self._requested_port), handler)
        self._httpd.serve_forever()

    def stop(self) -> None:
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    @property
    def port(self) -> int:
        return self._httpd.server_address[1] if self._httpd else self._requested_port

    @property
    def address(self) -> str:
        return f"http://{self.host}:{self.port}"

    def __enter__(self) -> "UiHttpServer":  # pragma: no cover - convenience
        return self.start_background()

    def __exit__(self, *exc: object) -> None:  # pragma: no cover - convenience
        self.stop()


def _build_handler(server: UiHttpServer) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "ProjectExpertUI/1.0"

        # -- plumbing ---------------------------------------------------
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            return  # keep the container log free of per-request noise

        def _send(self, status: HTTPStatus, payload: Any, *, content_type: str | None = None) -> None:
            if content_type is None:
                body = json.dumps(_jsonable(payload), indent=2).encode("utf-8")
                content_type = "application/json; charset=utf-8"
            else:
                body = payload if isinstance(payload, bytes) else str(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _authorised(self) -> bool:
            if not server.token:
                return True
            header = self.headers.get("Authorization", "")
            expected = f"Bearer {server.token}"
            return header == expected

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0:
                return {}
            raw = self.rfile.read(length)
            try:
                parsed = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                return {}
            return parsed if isinstance(parsed, dict) else {}

        def _dispatch(self, fn: Callable[[], Any]) -> None:
            try:
                self._send(HTTPStatus.OK, fn())
            except UiOperationDenied as denied:
                self._send(
                    HTTPStatus.FORBIDDEN,
                    {"error": "denied", "operation": denied.operation, "reason": denied.reason},
                )
            except NotImplementedError as exc:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found", "detail": str(exc)})
            except Exception as exc:  # noqa: BLE001 - adapter boundary
                self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

        # -- routes -----------------------------------------------------
        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path.startswith("/v1/") and server.openai_compat is not None:
                # The OpenAI-compatible shim is auth-gated by the same
                # bearer token as ``/api/v1/*`` when a token is configured.
                # Without a configured token the open-webui-adapter profile is
                # itself disabled, so the shim is unreachable.
                if not self._authorised():
                    self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                status, body = server.openai_compat.handle(path)
                self._send(HTTPStatus(status), body)
                return
            if path == "/health":
                self._send(HTTPStatus.OK, {"status": "ok", "ready": bool(server._readiness())})
                return
            if path == "/health/ready":
                ready = bool(server._readiness())
                self._send(
                    HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                    {"ready": ready},
                )
                return
            if path.startswith("/api/v1/"):
                if not self._authorised():
                    self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                self._dispatch(lambda: _get_route(server, self, path))
                return
            self._serve_static(path)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path.startswith("/v1/") and server.openai_compat is not None:
                if not self._authorised():
                    self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                    return
                status, body = server.openai_compat.handle(path, self._body())
                self._send(HTTPStatus(status), body)
                return
            if not path.startswith("/api/v1/"):
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found", "path": path})
                return
            if not self._authorised():
                self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
                return
            body = self._body()
            self._dispatch(lambda: _post_route(server, self, path, body))

        # -- static -----------------------------------------------------
        def _serve_static(self, path: str) -> None:
            relative = "index.html" if path in ("/", "") else path.lstrip("/")
            target = (server.static_root / relative).resolve()
            try:
                target.relative_to(server.static_root.resolve())
            except ValueError:
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found", "path": path})
                return
            if not target.is_file():
                self._send(HTTPStatus.NOT_FOUND, {"error": "not found", "path": path})
                return
            content_type = _CONTENT_TYPES.get(target.suffix, "application/octet-stream")
            self._send(HTTPStatus.OK, target.read_bytes(), content_type=content_type)

    return Handler


def _get_route(server: UiHttpServer, handler: BaseHTTPRequestHandler, path: str) -> Any:
    query = parse_qs(urlparse(handler.path).query)
    if path == "/api/v1/sources":
        return server.service.sources(server.actor)
    if path == "/api/v1/project-version":
        return server.service.project_version(server.actor)
    if path == "/api/v1/indexing-status":
        return server.service.indexing_status(server.actor)
    if path == "/api/v1/knowledge-status":
        return server.service.knowledge_status(server.actor)
    raise NotImplementedError(f"no such route: GET {path}")


def _post_route(
    server: UiHttpServer, handler: BaseHTTPRequestHandler, path: str, body: dict
) -> Any:
    actor = server.actor
    if path == "/api/v1/query":
        return server.service.query(
            actor,
            QueryRequest(
                text=str(body.get("text", "")),
                top_k=int(body.get("top_k", 10)),
                filters=body.get("filters"),
            ),
        )
    if path == "/api/v1/retrieve":
        return server.service.retrieve(
            actor,
            RetrieveRequest(
                text=str(body.get("text", "")),
                top_k=int(body.get("top_k", 10)),
                filters=body.get("filters"),
            ),
        )
    if path == "/api/v1/graph":
        return server.service.graph(
            actor, GraphRequest(entity=str(body.get("entity", "")), depth=int(body.get("depth", 1)))
        )
    if path == "/api/v1/wiki":
        return server.service.wiki(
            actor, WikiRequest(query=body.get("query"), id=body.get("id"))
        )
    if path == "/api/v1/materialize":
        return server.service.materialize(
            actor, MaterializeRequest(approval_token=body.get("approval_token"))
        )
    if path == "/api/v1/agent-delegation":
        return server.service.agent_delegation(
            actor,
            AgentDelegationRequest(
                task=str(body.get("task", "")), target=body.get("target")
            ),
        )
    raise NotImplementedError(f"no such route: POST {path}")