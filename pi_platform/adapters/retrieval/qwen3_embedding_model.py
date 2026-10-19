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
PINNED_REVISION = os.environ.get(
    "PI_QWEN3_REVISION",
    "unset-pin-via-model-licenses-json",
)
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
INSTRUCTION_PROFILE_VERSION = "project-expert-qwen-query-v1"


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
    ) -> None:
        # Plan §11 / §101: the adapter's default model id and
        # revision come from the EmbeddingProfile so the runtime
        # binding always matches the profile identity. Explicit
        # ``model_id`` / ``revision`` arguments override the
        # profile for tests only.
        self._profile = profile
        if (device or "auto").strip().lower() == "auto":
            try:
                import torch
                self._device = "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                self._device = "cpu"
        else:
            self._device = device.strip().lower()
        self._model_id = model_id or profile.model_id
        self._revision = (
            revision
            or os.environ.get("PI_QWEN3_REVISION")
            or profile.model_revision
        )
        self._calls = 0
        self._tokens = 0
        self._errors = 0
        self._model = None
        self._load_failed: bool = False
        self._load_error: str | None = None

    # -- lazy loading -----------------------------------------------------

    def _ensure_loaded(self):
        if self._model is not None or self._load_failed:
            return
        try:
            from sentence_transformers import SentenceTransformer
            import torch
        except Exception as exc:  # pragma: no cover - import guard
            self._load_failed = True
            self._load_error = f"{_NOT_BOUND_MESSAGE} (cause: {exc})"
            raise EmbeddingModelError(self._load_error) from exc

        try:
            torch_dtype = torch.float32 if self._device == "cpu" else torch.bfloat16
            try:
                self._model = SentenceTransformer(
                    self._model_id,
                    revision=self._revision,
                    device=self._device,
                    tokenizer_kwargs={"padding_side": "left"},
                    model_kwargs={"torch_dtype": torch_dtype},
                )
            except TypeError:
                # Older sentence-transformers (e.g. 2.7) do not
                # accept ``model_kwargs``; fall back to the
                # minimal constructor.
                self._model = SentenceTransformer(
                    self._model_id,
                    revision=self._revision,
                    device=self._device,
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
            texts_to_encode = [QUERY_INSTRUCTION + " " + request.text]
        else:
            texts_to_encode = [request.text]

        try:
            vectors = model.encode(
                texts_to_encode,
                prompt=None,
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

        # Plan §10.2 / §10.3: split the batch by role so the query
        # side can carry the instruction while the document side
        # stays un-instructed. The order of results is preserved
        # by the call site; we return a per-request list.
        results: list[Sequence[float]] = []
        for r in requests:
            try:
                if r.role == EmbeddingRole.QUERY:
                    vectors = model.encode(
                        [QUERY_INSTRUCTION + " " + r.text],
                        prompt=None,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )
                else:
                    vectors = model.encode(
                        [r.text],
                        prompt=None,
                        convert_to_numpy=True,
                        normalize_embeddings=True,
                        show_progress_bar=False,
                    )
            except Exception as exc:  # pragma: no cover - runtime
                self._errors += 1
                raise EmbeddingModelError(
                    f"Qwen3 batch encode failed: {exc}"
                ) from exc
            v = vectors[0]
            self._validate_vector(v)
            results.append(v.tolist())
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
