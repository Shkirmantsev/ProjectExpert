"""OpenAI-compatible retrieval adapter, including finite SSE at HTTP transport.

The shim delegates to query orchestration, which may call an explicitly saved
optional chat provider. PI_OPENAI_MODEL names the advertised retrieval
adapter; PI_OPENAI_BASE_URL is legacy configuration metadata only. The HTTP
server frames a computed completion as SSE when requested by Open WebUI.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any, Callable, Optional

__all__ = ["OpenAiCompatShim", "MODEL_ID", "DEFAULT_BASE_URL"]

MODEL_ID = "project-intelligence"
DEFAULT_BASE_URL = "http://localhost:8767/v1"


def env_base_url() -> str:
    """Read legacy endpoint metadata from ``PI_OPENAI_BASE_URL``.

    Returns an empty string when the operator explicitly disables the
    chat path (``PI_OPENAI_SHIM=0``).
    """
    if os.environ.get("PI_OPENAI_SHIM") == "0":
        return ""
    return os.environ.get("PI_OPENAI_BASE_URL", DEFAULT_BASE_URL)


def env_model_name() -> str:
    """Read the advertised model name from ``PI_OPENAI_MODEL``."""
    return os.environ.get("PI_OPENAI_MODEL", MODEL_ID)


class OpenAiCompatShim:
    """Translate the minimal OpenAI chat surface onto the query orchestrator.

    ``base_url`` is retained for configuration compatibility. Neither this
    adapter nor the browser calls it. An empty URL disables the legacy shim.
    """

    def __init__(
        self,
        query: Callable[[str], Any],
        *,
        flag: Optional[Callable[[], bool]] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self._query = query
        self._flag = flag or (lambda: True)
        self._model = model if model is not None else env_model_name()
        self._base_url = base_url if base_url is not None else env_base_url()

    @property
    def enabled(self) -> bool:
        # Enabled when the flag resolves true AND a base URL is configured.
        return bool(self._flag()) and bool(self._base_url)

    @property
    def model(self) -> str:
        return self._model

    @property
    def base_url(self) -> str:
        return self._base_url

    def configuration(self) -> dict[str, Any]:
        """Return the current shim configuration for the UI panel."""
        return {
            "enabled": self.enabled,
            "model": self._model,
            "base_url": self._base_url,
        }

    def handle(self, path: str, payload: Optional[dict] = None) -> tuple[int, Any]:
        """Handle one OpenAI-compatible request.

        Returns ``(status, body)``. A disabled shim answers 404 so the routes
        are simply absent unless the operator enabled the profile.
        """
        if not self.enabled:
            return 404, {"error": {"message": "open-webui-adapter flag is disabled"}}
        if path == "/v1/models" and payload is None:
            # ``GET /v1/models`` also doubles as the configuration endpoint
            # so the UI's "Model settings" panel can introspect the active
            # model id and base URL without a separate route.
            return 200, {
                "object": "list",
                "data": [
                    {
                        "id": self._model,
                        "object": "model",
                        "created": int(time.time()),
                        "owned_by": "project-intelligence",
                    }
                ],
                "pi_base_url": self._base_url,
                "pi_mode": "retrieval-with-optional-chat",
            }
        if path == "/v1/chat/completions":
            messages = (payload or {}).get("messages") or []
            prompt = next(
                (
                    str(message.get("content", ""))
                    for message in reversed(messages)
                    if message.get("role") == "user"
                ),
                "",
            )
            if not prompt:
                return 400, {"error": {"message": "no user message supplied"}}
            result = self._query(prompt)
            content = getattr(result, "answer", None)
            if content is None:
                results = getattr(result, "results", ()) or ()
                evidence = []
                for index, hit in enumerate(results[:10], 1):
                    meta = getattr(hit, "metadata", None)
                    path = getattr(meta, "sourcePath", None) or getattr(meta, "documentId", None) or "unknown source"
                    evidence.append(f"[{index}] {path}\n{getattr(hit, 'snippet', str(hit))}")
                content = "Retrieved project evidence (no generated answer):\n\n" + "\n\n".join(evidence) if evidence else "No matching project evidence found. Try a specific term or identifier."
                diagnostics = tuple(getattr(result, "explanations", ()) or ())
                if diagnostics:
                    content += "\n\n" + "\n".join(diagnostics)
            return 200, {
                "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": self._model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": str(content)},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            }
        return 404, {"error": {"message": f"no such route: {path}"}}
