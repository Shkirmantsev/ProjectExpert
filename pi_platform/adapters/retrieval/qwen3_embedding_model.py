"""Qwen3-Embedding-0.6B embedding adapter.

Production profile
:class:`pi_platform.ports.retrieval.embedding_profile.QWEN3_EMBEDDING_0_6B_1024`
behind the role-aware :class:`EmbeddingModelPort` (open spec change
``production-semantic-search-and-branch-reconciliation``, PR 4).

Two execution modes are supported (open spec change PR 4):

* **Real binding.** When the optional ``sentence-transformers``
  package and the pinned :attr:`PINNED_REVISION` of
  ``Qwen/Qwen3-Embedding-0.6B`` are both available, the adapter
  loads the real model with the documented Qwen3 query instruction
  (plan §10.2) and document-side un-instructed encoding
  (plan §10.3).
* **Diagnostic stub.** When either dependency is missing the
  adapter remains constructible and raises
  :class:`EmbeddingModelError` from every embedding call with an
  actionable message. This honours plan §2.1: a production
  component is either ``real-and-available``,
  ``real-and-not-installed`` or ``disabled`` — never "looks
  enabled but runs a stub" silently.

Plan §10.4 fixes the default dimension at 1024d with L2
normalization; the validator enforces the constraint on every
returned vector (plan §10.4 validation rules).
"""

from __future__ import annotations

import math
import os
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
    EmbeddingRequest,
    EmbeddingRole,
    EmbeddingTask,
)
from pi_platform.ports.retrieval.embedding_profile import (
    QWEN3_EMBEDDING_0_6B_1024,
    EmbeddingProfile,
)


__all__ = [
    "Qwen3EmbeddingModel",
    "ADAPTER_NAME",
    "DEFAULT_LICENSE_ID",
    "DEFAULT_MODEL_ID",
    "DEFAULT_OUTPUT_DIMENSION",
    "PINNED_REVISION",
    "QUERY_INSTRUCTION",
    "INSTRUCTION_PROFILE_VERSION",
    "is_real_binding_available",
]


ADAPTER_NAME = "qwen3-embedding-0.6b"
DEFAULT_MODEL_ID = "Qwen/Qwen3-Embedding-0.6B"
# Public pinned revision. Updated together with
# ``distribution/licenses/model-licenses.json``.
PINNED_REVISION = QWEN3_EMBEDDING_0_6B_1024.model_revision

DEFAULT_LICENSE_ID = "Apache-2.0"
DEFAULT_OUTPUT_DIMENSION = 1024  # Plan §6.2 / §10.4

# Plan §10.2 — one stable ProjectExpert instruction string for
# Qwen3 query embedding. Stored under
# ``profile.instruction_profile`` so a change to this string
# changes the profile identity and forces a separate vector
# namespace (plan §2.4 / §2.5).
QUERY_INSTRUCTION = (
    "Given a software-engineering query, retrieve the most relevant "
    "source code, tests, requirements, architecture, specifications, "
    "protocols, and documentation needed to answer the query."
)
INSTRUCTION_PROFILE_VERSION = "project-expert-qwen-query-v2"


_NOT_BOUND_MESSAGE = (
    "Qwen3-Embedding-0.6B is not bound in this build; install "
    "sentence-transformers and a pinned Qwen/Qwen3-Embedding-0.6B "
    "revision (see distribution/licenses/model-licenses.json), "
    "or run 'project-intelligence models pull qwen'."
)


def is_real_binding_available() -> bool:
    """Return True if the optional real binding is importable.

    The check returns True only if both ``sentence_transformers``
    and ``torch`` are importable. Missing either means the
    binding cannot satisfy a request and the adapter will raise
    :class:`EmbeddingModelError` per plan §2.1.
    """

    try:
        import sentence_transformers  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        return False
    return True


class Qwen3EmbeddingModel(EmbeddingModelPort):
    """Qwen3-Embedding-0.6B (1024d) adapter behind the role-aware port.

    Construct with ``device='cpu'`` (default) for the plan §6.2
    float32 CPU profile or ``device='cuda'`` for a bf16 GPU
    profile. ``device='auto'`` (plan §13) defers the choice to
    :class:`pi_platform.adapters.config.runtime_device.RuntimeDeviceSelector`.
    """

    def __init__(
        self,
        profile: EmbeddingProfile = QWEN3_EMBEDDING_0_6B_1024,
        *,
        device: str = "cpu",
        model_id: str | None = None,
        revision: str | None = None,
        cache_folder: str | None = None,
    ) -> None:
        # Plan §11 / §101: the adapter's default model id and
        # revision come from the EmbeddingProfile so the runtime
        # binding always matches the profile identity. Explicit
        # ``model_id`` / ``revision`` arguments override the
        # profile for tests only.
        self._profile = profile
        from pi_platform.adapters.config.runtime_device import select_device
        selection = select_device(device)
        self._device = selection.device
        self.device_selection_reason = selection.reason
        self._model_id = model_id or profile.model_id
        self._revision = (
            revision
            or os.environ.get("PI_QWEN3_REVISION")
            or profile.model_revision
        )
        self._cache_folder = cache_folder or os.environ.get("PI_MODEL_CACHE")
        self._calls = 0
        self._tokens = 0
        self._errors = 0
        self._model = None
        self._load_failed: bool = False
        self._load_error: str | None = None

    # -- lazy loading -----------------------------------------------------

    def _ensure_loaded(self):
        if self._model is not None:
            return
        if self._load_failed:
            raise EmbeddingModelError(self._load_error or _NOT_BOUND_MESSAGE)
        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except Exception as exc:  # pragma: no cover - import guard
            self._load_failed = True
            self._load_error = f"{_NOT_BOUND_MESSAGE} (cause: {exc})"
            raise EmbeddingModelError(self._load_error) from exc

        try:
            torch_dtype = (torch.bfloat16 if self._device == "cuda" and torch.cuda.is_bf16_supported() else torch.float32)
            self._model = SentenceTransformer(
                    self._model_id,
                    revision=self._revision,
                    device=self._device,
                    cache_folder=self._cache_folder,
                    tokenizer_kwargs={"padding_side": "left"},
                    model_kwargs={"torch_dtype": torch_dtype},
                )
        except Exception as exc:  # pragma: no cover - network/runtime
            self._load_failed = True
            self._load_error = (
                f"Qwen3 failed to load from {self._model_id}"
                f"@{self._revision} on device {self._device}: {exc}"
            )
            raise EmbeddingModelError(self._load_error) from exc

    # -- port surface -----------------------------------------------------

    def embed(self, text: str) -> Sequence[float]:
        return self.embed_request(
            EmbeddingRequest(text=text, role=EmbeddingRole.DOCUMENT),
        )

    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        return self.embed_requests(
            [EmbeddingRequest(text=t, role=EmbeddingRole.DOCUMENT)
             for t in texts],
        )

    def embed_request(self, request: EmbeddingRequest) -> Sequence[float]:
        if request.image_path:
            raise EmbeddingModelError("Qwen text embeddings cannot encode images; select Gemma")
        self._calls += 1
        try:
            self._ensure_loaded()
        except EmbeddingModelError:
            self._errors += 1
            raise

        model = self._model
        if model is None:  # pragma: no cover - defensive
            self._errors += 1
            raise EmbeddingModelError(_NOT_BOUND_MESSAGE)

        # Plan §10.2 / §10.3: query side gets the instruction;
        # document side is encoded un-instructed.
        if request.role == EmbeddingRole.QUERY:
            texts_to_encode = [f"Instruct: {QUERY_INSTRUCTION}\nQuery:{request.text}"]
        else:
            texts_to_encode = [request.text]

        try:
            vectors = model.encode(
                texts_to_encode,
                prompt="",
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        except Exception as exc:  # pragma: no cover - runtime
            self._errors += 1
            raise EmbeddingModelError(
                f"Qwen3 encode failed: {exc}"
            ) from exc

        v = vectors[0]
        self._validate_vector(v)
        return v.tolist()

    def embed_requests(
        self, requests: Sequence[EmbeddingRequest],
    ) -> Sequence[Sequence[float]]:
        if any(request.image_path for request in requests):
            raise EmbeddingModelError("Qwen is text-only; select Gemma for images")
        if not requests:
            return []
        try:
            self._ensure_loaded()
        except EmbeddingModelError:
            for _ in requests:
                self._errors += 1
            raise
        model = self._model
        if model is None:  # pragma: no cover - defensive
            for _ in requests:
                self._errors += 1
            raise EmbeddingModelError(_NOT_BOUND_MESSAGE)

        texts = [
            f"Instruct: {QUERY_INSTRUCTION}\nQuery:{r.text}"
            if r.role == EmbeddingRole.QUERY else r.text
            for r in requests
        ]
        try:
            vectors = model.encode(
                texts, prompt="", convert_to_numpy=True,
                normalize_embeddings=True, show_progress_bar=False,
            )
        except Exception as exc:
            self._errors += 1
            raise EmbeddingModelError(f"Qwen3 batch encode failed: {exc}") from exc
        results = []
        for vector in vectors:
            self._validate_vector(vector)
            results.append(vector.tolist())
        return results

    def _validate_vector(self, vec) -> None:
        """Plan §10.4 — fail closed on malformed vectors."""
        if len(vec) != DEFAULT_OUTPUT_DIMENSION:
            self._errors += 1
            raise EmbeddingModelError(
                f"Qwen3 returned a vector of length {len(vec)}, "
                f"expected {DEFAULT_OUTPUT_DIMENSION}"
            )
        for x in vec:
            if not math.isfinite(float(x)):
                self._errors += 1
                raise EmbeddingModelError(
                    "Qwen3 returned a non-finite value"
                )

    def dimension(self) -> int:
        return self._profile.output_dimension

    def model_version(self) -> str:
        return self._profile.identity()

    def license_id(self) -> str:
        return DEFAULT_LICENSE_ID

    def profile(self) -> EmbeddingProfile:
        return self._profile

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "tokens": self._tokens,
            "errors": self._errors,
            "backend": ADAPTER_NAME,
            "real_binding": "1" if self._model is not None else "0",
        }
