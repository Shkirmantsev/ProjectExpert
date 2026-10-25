"""Role-aware pinned EmbeddingGemma 2 embeddings over a local llama.cpp server.

This is the production binding of the one production embedding model. It
speaks to a supervised ``llama-server`` that was started with the pinned
``Q8_0`` backbone and the pinned ``Q8_0`` multimodal projector, so text,
image, audio and video inputs are available.

The adapter never assumes a modality works: it reads the input modalities the
runtime advertises through ``/v1/models`` and refuses a request for a
modality the runtime does not advertise. It never substitutes a text-only
representation, a hash vector or a zero vector for a media input.

The vector contract: the runtime returns 768 dimensions with mean pooling and
L2 normalisation; the adapter applies the Matryoshka truncation to the
profile's 512 dimensions and re-normalises afterwards.
"""

from __future__ import annotations

import base64
import json
import math
import mimetypes
import os
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
    EmbeddingRequest,
    EmbeddingRole,
    EmbeddingTask,
)
from pi_platform.ports.retrieval.embedding_profile import (
    EMBEDDINGGEMMA2_GGUF_512,
    EmbeddingProfile,
)

from .embeddinggemma2_embedding_model import TASK_PROMPTS, _format_document_text
from .gguf_artifacts import (
    GEMMA_FULL_DIMENSION,
    GEMMA_MODEL_ALIAS,
    GEMMA_PROJECTOR_SHA256,
    GEMMA_SHA256,
)


__all__ = [
    "LlamaCppEmbeddingModel",
    "GEMMA_GGUF_PROFILE",
    "MAX_IMAGE_BYTES",
    "MAX_AUDIO_BYTES",
    "MAX_VIDEO_BYTES",
]


# The profile identity is owned by the ports layer so the registry and this
# adapter cannot drift apart.
GEMMA_GGUF_PROFILE = EMBEDDINGGEMMA2_GGUF_512

# Bounded media inputs. The runtime is local, but an unbounded payload is
# still a denial-of-service and an out-of-memory risk.
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_AUDIO_BYTES = 32 * 1024 * 1024
MAX_VIDEO_BYTES = 64 * 1024 * 1024

_MAX_RESPONSE_BYTES = 8 * 1024 * 1024

# Media input kinds mapped to the runtime content-part type and to the
# runtime-advertised modality name.
_MEDIA_KINDS = {
    "image_path": ("image_url", "image", MAX_IMAGE_BYTES),
    "audio_path": ("input_audio", "audio", MAX_AUDIO_BYTES),
    "video_path": ("input_video", "video", MAX_VIDEO_BYTES),
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Runtime redirects are not permitted")


class LlamaCppEmbeddingModel(EmbeddingModelPort):
    """Pinned EmbeddingGemma 2 (Q8_0) adapter behind the role-aware port."""

    def __init__(
        self,
        *,
        device: str = "auto",
        endpoint: str | None = None,
        key_file: str | None = None,
        timeout: int = 120,
        model_alias: str | None = None,
    ) -> None:
        if device not in {"cpu", "cuda", "vulkan", "auto"}:
            raise EmbeddingModelError(
                "the GGUF binding supports cpu, cuda, vulkan or auto"
            )
        self.device = device
        self.runtime_alias = model_alias or GEMMA_MODEL_ALIAS
        self._profile = GEMMA_GGUF_PROFILE
        self.endpoint = (
            endpoint or os.environ.get("PI_LLAMA_ENDPOINT", "http://127.0.0.1:8769")
        ).rstrip("/")
        parsed = urllib.parse.urlparse(self.endpoint)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise EmbeddingModelError(
                "PI_LLAMA_ENDPOINT must be an HTTP(S) endpoint without credentials or query"
            )
        self.key_file = key_file or os.environ.get(
            "PI_LLAMA_API_KEY_FILE", "/models/llama-api-key"
        )
        self.timeout = timeout
        self._calls = 0
        self._ready = False
        self._modalities: frozenset[str] | None = None
        self._runtime_model_id: str | None = None

    # -- transport ---------------------------------------------------------

    def _request(self, path, payload=None):
        try:
            token = Path(self.key_file).read_text().strip()
            if len(token) < 32:
                raise ValueError("invalid runtime key")
            body = None if payload is None else json.dumps(payload).encode()
            req = urllib.request.Request(
                self.endpoint + path,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + token,
                },
            )
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as response:
                raw = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(raw) > _MAX_RESPONSE_BYTES:
                    raise ValueError("embedding response exceeds size limit")
                return json.loads(raw)
        except (OSError, ValueError) as exc:
            # Never include headers, tokens, remote error bodies or query text.
            self._ready = False
            raise EmbeddingModelError(
                "GGUF runtime unavailable or invalid "
                f"({type(exc).__name__}); start the selected accelerator deployment"
            ) from exc

    # -- capabilities ------------------------------------------------------

    def _load_runtime_identity(self) -> frozenset[str]:
        """Read the runtime's advertised model identity and modalities.

        The result is cached for the lifetime of the adapter: the runtime is
        a supervised child whose identity cannot change without a restart,
        and a probe per request would double the request cost.
        """

        if self._modalities is not None:
            return self._modalities
        models = self._request("/v1/models")
        try:
            entries = models["data"]
            identities = set()
            modalities: set[str] = set()
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                identifier = entry.get("id")
                if isinstance(identifier, str):
                    identities.add(identifier)
                architecture = entry.get("architecture")
                if isinstance(architecture, dict):
                    advertised = architecture.get("input_modalities")
                    if isinstance(advertised, list):
                        modalities.update(
                            item for item in advertised if isinstance(item, str)
                        )
        except (KeyError, TypeError) as exc:
            self._ready = False
            raise EmbeddingModelError("Invalid GGUF model identity response") from exc
        if self.runtime_alias not in identities:
            self._ready = False
            raise EmbeddingModelError(
                "GGUF runtime model identity differs from the selected pinned GGUF profile"
            )
        if not modalities:
            # A runtime that does not advertise its input modalities is
            # treated as text-only. It is never treated as multimodal.
            modalities = {"text"}
        self._runtime_model_id = self.runtime_alias
        self._modalities = frozenset(modalities)
        return self._modalities

    def capabilities(self) -> dict:
        """Return the runtime identity and the modalities it advertises."""

        modalities = self._load_runtime_identity()
        return {
            "model_id": self._runtime_model_id,
            "model_sha256": GEMMA_SHA256,
            "projector_sha256": GEMMA_PROJECTOR_SHA256,
            "quantization": "Q8_0",
            "pooling": "mean",
            "full_dimension": GEMMA_FULL_DIMENSION,
            "index_dimension": self._profile.output_dimension,
            "input_modalities": sorted(modalities),
        }

    # -- request shaping ---------------------------------------------------

    def _media_part(self, request: EmbeddingRequest) -> dict | None:
        """Build the runtime content part for the attached media, if any."""

        for attribute, (part_type, modality, limit) in _MEDIA_KINDS.items():
            path_value = getattr(request, attribute)
            if not path_value:
                continue
            path = Path(path_value)
            if not path.is_file():
                raise EmbeddingModelError(
                    f"{modality} embedding input does not exist"
                )
            size = path.stat().st_size
            if size <= 0:
                raise EmbeddingModelError(
                    f"{modality} embedding input is empty"
                )
            if size > limit:
                raise EmbeddingModelError(
                    f"{modality} embedding input exceeds the {limit // (1024 * 1024)} MiB limit"
                )
            payload = base64.b64encode(path.read_bytes()).decode("ascii")
            if attribute == "image_path":
                mime = mimetypes.guess_type(path.name)[0] or "image/png"
                return {
                    "type": "image_url",
                    "image_url": {"url": "data:" + mime + ";base64," + payload},
                }
            if attribute == "audio_path":
                fmt = (mimetypes.guess_type(path.name)[0] or "audio/wav").split("/")[-1]
                return {
                    "type": "input_audio",
                    "input_audio": {"data": payload, "format": fmt},
                }
            return {"type": "input_video", "input_video": {"data": payload}}
        return None

    @staticmethod
    def _modality_of(request: EmbeddingRequest) -> str:
        for attribute, (_part_type, modality, _limit) in _MEDIA_KINDS.items():
            if getattr(request, attribute):
                return modality
        return "text"

    # -- port surface ------------------------------------------------------

    def embed_requests(self, requests):
        if not requests:
            return []
        modalities = self._load_runtime_identity()
        for request in requests:
            modality = self._modality_of(request)
            if modality not in modalities:
                self._ready = False
                raise EmbeddingModelError(
                    f"the GGUF runtime does not support {modality} input; "
                    f"it advertises {sorted(modalities)}"
                )
        output = []
        # Bound one request per sequence: avoids server context/batch overflow
        # and preserves exact document order for mixed-role inputs.
        for request in requests:
            text = request.text
            if request.role == EmbeddingRole.QUERY:
                text = (
                    TASK_PROMPTS.get(request.task, TASK_PROMPTS[EmbeddingTask.SEARCH])
                    + text
                )
            else:
                text = _format_document_text(text, request.title)
            media = self._media_part(request)
            if media is not None:
                text = {
                    "content": [
                        {"type": "text", "text": text},
                        media,
                    ]
                }
            result = self._request(
                "/v1/embeddings",
                {
                    "model": self.runtime_alias,
                    "input": [text],
                    "encoding_format": "float",
                },
            )
            try:
                data = result["data"]
                if len(data) != 1 or data[0]["index"] != 0:
                    raise ValueError("invalid response cardinality")
                vector = data[0]["embedding"]
                if len(vector) != GEMMA_FULL_DIMENSION or any(
                    isinstance(x, bool)
                    or not isinstance(x, (int, float))
                    or not math.isfinite(x)
                    for x in vector
                ):
                    raise ValueError("invalid embedding values or dimensions")
                # Matryoshka truncation first, then re-normalisation.
                vector = vector[: self.dimension()]
                norm = math.sqrt(sum(x * x for x in vector))
                if not math.isfinite(norm) or norm <= 0:
                    raise ValueError("invalid embedding norm")
                output.append([x / norm for x in vector])
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                self._ready = False
                raise EmbeddingModelError("Invalid GGUF embedding response") from exc
            self._calls += 1
        self._ready = True
        return output

    def embed_request(self, request):
        return self.embed_requests([request])[0]

    def embed(self, text):
        return self.embed_request(EmbeddingRequest(text, EmbeddingRole.DOCUMENT))

    def embed_batch(self, texts):
        return self.embed_requests(
            [EmbeddingRequest(text, EmbeddingRole.DOCUMENT) for text in texts]
        )

    def dimension(self):
        return self._profile.output_dimension

    def model_version(self):
        return self._profile.identity()

    def license_id(self):
        return "Apache-2.0"

    def profile(self):
        return self._profile

    def stats(self):
        return {
            "calls": self._calls,
            "backend": "llama.cpp",
            "real_binding": "1" if self._ready else "0",
            "requested_device": self.device,
            "model_id": self.runtime_alias,
            "input_modalities": (
                ",".join(sorted(self._modalities)) if self._modalities else ""
            ),
        }
