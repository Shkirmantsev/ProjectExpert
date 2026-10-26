"""Multilingual sentence-transformer embedding adapter (opt-in).

.. note::
   Superseded by the profile-aware bindings
   (:class:`pi_platform.adapters.retrieval.embeddinggemma2_embedding_model.EmbeddingGemma2EmbeddingModel`
   and the native EmbeddingGemma 2 binding).
   This class remains as the pre-change placeholder for callers
   that need the legacy ``multilingual-st`` alias.

The adapter wraps the optional ``sentence-transformers`` package
and is registered only when the package is installed. When the
dependency is missing the adapter raises
:class:`EmbeddingModelError` at construction time so the
:class:`pi_platform.core.licensing.license_gate.LicenseGate` can
record the optional dependency as unavailable without silently
falling back to the hashing adapter.

The adapter conforms to the role-aware
:class:`EmbeddingModelPort` (open spec change PR 2) and the text
encoding is delegated to the underlying ``encode`` call; the
adapter does not apply any model-specific prompt because the
underlying ``paraphrase-multilingual-MiniLM-L12-v2`` model is
trained for un-instructed symmetric retrieval.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
    EmbeddingRequest,
    EmbeddingRole,
)
from pi_platform.ports.retrieval.embedding_profile import (
    HASHING_DEFAULT,
    EmbeddingProfile,
)


__all__ = [
    "MultilingualSentenceTransformerEmbeddingModel",
    "ADAPTER_NAME",
    "DEFAULT_MODEL_ID",
    "DEFAULT_LICENSE_ID",
    "EXPECTED_DIMENSION",
]


ADAPTER_NAME = "multilingual-st"
DEFAULT_MODEL_ID = "paraphrase-multilingual-MiniLM-L12-v2"
DEFAULT_LICENSE_ID = "Apache-2.0"
EXPECTED_DIMENSION = 384


class MultilingualSentenceTransformerEmbeddingModel(EmbeddingModelPort):
    """Multilingual sentence-transformer embedding adapter (opt-in)."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        license_id: str = DEFAULT_LICENSE_ID,
    ) -> None:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError as exc:
            raise EmbeddingModelError(
                "sentence-transformers is not installed; install the "
                "Phase 4 retrieval optional dependency before "
                "registering the multilingual-st adapter."
            ) from exc
        self._model_id = model_id
        self._license_id = license_id
        self._dimension = EXPECTED_DIMENSION
        self._model_version = model_id
        self._calls = 0
        self._tokens = 0
        self._errors = 0
        self._model = None
        self._load_failed = False

    def _ensure_loaded(self):
        if self._model is not None or self._load_failed:
            return
        try:
            from sentence_transformers import SentenceTransformer
        except Exception as exc:  # pragma: no cover
            self._load_failed = True
            raise EmbeddingModelError(
                f"sentence-transformers import failed: {exc}"
            ) from exc
        try:
            self._model = SentenceTransformer(self._model_id)
        except Exception as exc:  # pragma: no cover
            self._load_failed = True
            raise EmbeddingModelError(
                f"multilingual-st model load failed: {exc}"
            ) from exc

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
        try:
            v = self._model.encode(
                [request.text],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )[0]
        except Exception as exc:  # pragma: no cover
            self._errors += 1
            raise EmbeddingModelError(
                f"multilingual-st encode failed: {exc}"
            ) from exc
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
        try:
            vectors = self._model.encode(
                [r.text for r in requests],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        except Exception as exc:  # pragma: no cover
            self._errors += 1
            raise EmbeddingModelError(
                f"multilingual-st batch encode failed: {exc}"
            ) from exc
        return [v.tolist() for v in vectors]

    def dimension(self) -> int:
        return self._dimension

    def model_version(self) -> str:
        return self._model_version

    def license_id(self) -> str:
        return self._license_id

    def profile(self) -> EmbeddingProfile:
        return HASHING_DEFAULT  # legacy alias; not the production profile

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "tokens": self._tokens,
            "errors": self._errors,
            "backend": ADAPTER_NAME,
            "real_binding": "1" if self._model is not None else "0",
        }
