"""Phase 10 A2A HTTP transport adapter.

The adapter binds loopback by default and serves the minimum A2A
surface: ``tasks/send`` (JSON-RPC) and the well-known Agent Card
path. The adapter does not import any third-party library beyond
the Python standard library.

The adapter is intentionally small. The bulk of the behaviour lives
in :mod:`pi_platform.core.a2a`; the HTTP layer only translates
between HTTP/JSON and the port's value types.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Mapping, Optional

from pi_platform.ports.a2a import (
    A2aForbidden,
    A2aLimitExceeded,
    A2aNotFound,
    A2aSpecVersion,
    A2aTask,
    A2aTaskResult,
    A2aUnauthorized,
    A2aUnsupported,
    A2aVersionIncompatible,
    AgentCardPort,
    A2aAdapterPort,
)

from .envelope import serialise_task_result


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class A2aHttpServerConfig:
    host: str
    port: int
    well_known_path: str = "/.well-known/agent-card.json"
    tasks_path: str = "/a2a/v1/tasks:send"


class A2aHttpServer:
    """Loopback HTTP transport adapter for the A2A surface.

    The class is the public factory. Tests construct the underlying
    handler with a stub adapter to exercise wire translation in
    isolation.
    """

    def __init__(
        self,
        *,
        adapter: A2aAdapterPort,
        agent_card: AgentCardPort,
        config: A2aHttpServerConfig,
        token_provider: Optional[Callable[[], Optional[str]]] = None,
    ) -> None:
        self._adapter = adapter
        self._card = agent_card
        self._config = config
        self._token = token_provider or (lambda: None)
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    # --- Lifecycle -----------------------------------------------------------

    def start(self) -> tuple[str, int]:
        handler_cls = _build_handler(self)
        self._server = ThreadingHTTPServer((self._config.host, self._config.port), handler_cls)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self._config.host, self._server.server_address[1]

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def config(self) -> A2aHttpServerConfig:
        return self._config


def _build_handler(server: A2aHttpServer) -> type[BaseHTTPRequestHandler]:
    parent = server

    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:  # pragma: no cover - logging
            LOGGER.debug(format, *args)

        def do_GET(self) -> None:  # noqa: N802 - http.server convention
            if self.path == parent._config.well_known_path:
                self._handle_agent_card()
                return
            self._send(404, b"")

        def do_POST(self) -> None:  # noqa: N802 - http.server convention
            if self.path != parent._config.tasks_path:
                self._send(404, b"")
                return
            self._handle_invoke()

        # --- Handlers -----------------------------------------------------

        def _handle_agent_card(self) -> None:
            if not parent._card.is_published():
                self._send(404, b"")
                return
            card = parent._card.build_agent_card()
            payload = json.dumps(card.as_dict(), sort_keys=True)
            self._send(200, payload.encode("utf-8"), content_type="application/json")

        def _handle_invoke(self) -> None:
            token = parent._token()
            if token is not None:
                supplied = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
                if not supplied or supplied != token:
                    self._send(401, b"")
                    return
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0:
                self._send(400, b"")
                return
            raw = self.rfile.read(length)
            try:
                payload = json.loads(raw)
                if not isinstance(payload, Mapping):
                    self._send(400, b"")
                    return
            except (ValueError, json.JSONDecodeError):
                self._send(400, b"")
                return

            try:
                task = _envelope_to_task(payload)
            except A2aVersionIncompatible:
                self._send(410, b"")
                return

            try:
                result = parent._adapter.invoke(
                    actor={
                        "id": self.headers.get("X-Actor-Id", "anonymous"),
                        "capabilities": {
                            "mcp.invoke": True,
                            "a2a.invoke": True,
                            "agent.delegate": False,
                        },
                    },
                    task=task,
                )
            except A2aForbidden:
                self._send(403, b"")
                return
            except A2aUnauthorized:
                self._send(401, b"")
                return
            except A2aLimitExceeded:
                self._send(429, b"")
                return
            except A2aUnsupported:
                self._send(404, b"")
                return

            self._send(200, serialise_task_result(result).encode("utf-8"))

        def _send(self, status: int, body: bytes, *, content_type: str = "application/json") -> None:
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if body:
                    self.wfile.write(body)
            except OSError:
                # Connection dropped; nothing useful to do.
                pass

    return _Handler


# ---------------------------------------------------------------------------
# Wire ↔ port helpers
# ---------------------------------------------------------------------------


def _envelope_to_task(payload: Mapping[str, Any]) -> A2aTask:
    from .envelope import parse_task_envelope

    try:
        return parse_task_envelope(payload)
    except ValueError as exc:
        raise A2aUnsupported(str(exc)) from exc
