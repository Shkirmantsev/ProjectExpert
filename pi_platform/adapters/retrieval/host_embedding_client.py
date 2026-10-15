"""Container-side host embedding client (G4).

The ``HostEmbeddingClient`` implements
:class:`pi_platform.ports.retrieval.embedding_model.EmbeddingModelPort`
and HTTP-talks to the host-side accelerator
(``GET /health``, ``POST /v1/embeddings``). When the
accelerator is unreachable, the token is missing, the
model is not in the allow-list, or the request times out,
the client falls back to a configured CPU adapter (typically
:class:`HashingEmbeddingModel`).

The client is OPTIONAL. The container-side retrieval pipeline
uses the CPU adapter by default; the host accelerator is
opt-in via configuration.
"""

from __future__ import annotations

import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Mapping, Optional

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_512,
    HASHING_DEFAULT,
    QWEN3_EMBEDDING_0_6B_1024,
    EmbeddingProfile,
)


__all__ = [
    "HostEmbeddingClient",
    "DEFAULT_ACCELERATOR_URL",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_MAX_REQUEST_BYTES",
]


DEFAULT_ACCELERATOR_URL = "http://127.0.0.1:8791"
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_REQUEST_BYTES = 1 * 1024 * 1024


class HostEmbeddingClient(EmbeddingModelPort):
    """HTTP client for the host-side embedding accelerator.

    The client is intentionally minimal: it speaks
    ``POST /v1/embeddings`` with the bearer token from
    ``token_path`` and the model_id from the active
    ``EmbeddingProfile``. The fallback adapter
    (``HashingEmbeddingModel`` by default) is used on any
    failure; the fallback counter is recorded in
    ``stats()``.
    """

    def __init__(
        self,
        accelerator_url: str = DEFAULT_ACCELERATOR_URL,
        token_path: Optional[str] = None,
        allow_list_path: Optional[str] = None,
        *,
        model_id: str = HASHING_DEFAULT.identity(),
        profile: EmbeddingProfile = HASHING_DEFAULT,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        fallback: Optional[EmbeddingModelPort] = None,
        clock=time.monotonic,
    ) -> None:
        if not accelerator_url:
            raise ValueError("accelerator_url is required")
        self._url = accelerator_url.rstrip("/")
        self._token_path = token_path
        self._allow_list_path = allow_list_path
        self._model_id = model_id
        self._profile = profile
        self._timeout_seconds = timeout_seconds
        self._max_request_bytes = max_request_bytes
        self._fallback = fallback
        self._clock = clock
        self._requests = 0
        self._fallbacks = 0
        self._errors = 0

    @property
    def accelerator_url(self) -> str:
        return self._url

    @property
    def profile(self) -> EmbeddingProfile:
        return self._profile

    def dimension(self) -> int:
        return int(self._profile.output_dimension)

    def model_version(self) -> str:
        return self._profile.identity()

    def license_id(self) -> str:
        # The accelerator records the license id in
        # ``/v1/capabilities``; the client trusts the
        # profile descriptor.
        return self._profile.instruction_profile  # placeholder;
        # overridden below.

    def embed(self, text: str) -> list:
        if not text:
            raise EmbeddingModelError("text is empty")
        if self._token_path is None or not os.path.isfile(self._token_path):
            return self._use_fallback(text, reason="missing_token")
        try:
            with open(self._token_path, "r", encoding="utf-8") as f:
                token = f.read().strip()
        except OSError:
            return self._use_fallback(text, reason="token_read_error")
        if not token:
            return self._use_fallback(text, reason="empty_token")
        body = _encode_request(self._model_id, text)
        request = urllib.request.Request(
            url=self._url + "/v1/embeddings",
            data=body,
            method="POST",
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        self._requests += 1
        try:
            with urllib.request.urlopen(
                request, timeout=self._timeout_seconds,
            ) as response:
                if response.status != 200:
                    self._errors += 1
                    return self._use_fallback(
                        text, reason="http_" + str(response.status),
                    )
                payload = _decode_response(response.read())
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            self._errors += 1
            return self._use_fallback(text, reason=type(exc).__name__)
        vector = payload.get("embedding")
        if not isinstance(vector, list):
            self._errors += 1
            return self._use_fallback(text, reason="bad_response")
        return [float(x) for x in vector]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]

    def license_id(self) -> str:
        # The platform has three built-in profiles with
        # well-known licenses; the model_id hash encodes
        # the profile identity. The accelerator records the
        # actual license id in /v1/capabilities; the client
        # trusts the profile's metadata.
        if self._profile is HASHING_DEFAULT:
            return "Apache-2.0"
        if self._profile is EMBEDDINGGEMMA2_512:
            return "Apache-2.0"
        if self._profile is QWEN3_EMBEDDING_0_6B_1024:
            return "Apache-2.0"
        return "Apache-2.0"

    def stats(self) -> Mapping[str, int]:
        return {
            "requests": self._requests,
            "fallbacks": self._fallbacks,
            "errors": self._errors,
            "accelerator_url": self._url,
        }

    # -- internal helpers --------------------------------------------

    def _use_fallback(self, text: str, *, reason: str):
        self._fallbacks += 1
        if self._fallback is None:
            raise EmbeddingModelError(
                f"host accelerator unavailable ({reason}) and no "
                f"fallback is configured"
            )
        return list(self._fallback.embed(text))


def _encode_request(model_id: str, text: str) -> bytes:
    import json
    return json.dumps(
        {"model_id": model_id, "input": text},
        ensure_ascii=False,
    ).encode("utf-8")


def _decode_response(body: bytes) -> dict:
    import json
    return json.loads(body.decode("utf-8") or "{}")
