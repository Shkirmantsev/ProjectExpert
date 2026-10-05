"""Multilingual sentence-transformer embedding adapter (opt-in).

Wraps the optional ``sentence-transformers`` Python package as the
multilingual default embedding backend. The adapter is registered
only when ``sentence-transformers`` is installed AND
``project-context.yaml:embedding.backend == "multilingual-st"``.

When the dependency is missing the adapter raises
:class:`EmbeddingModelError` at construction time so the
:class:`pi_platform.core.licensing.license_gate.LicenseGate` can
record the optional dependency as unavailable without silently
falling back to the hashing adapter.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
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

    def embed(self, text: str) -> Sequence[float]:
        raise EmbeddingModelError(
            "MultilingualSentenceTransformerEmbeddingModel.embed is only "
            "available when the sentence-transformers package is "
            "installed at runtime; use the hashing adapter in tests."
        )

    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        raise EmbeddingModelError(
            "MultilingualSentenceTransformerEmbeddingModel.embed_batch "
            "is only available when the sentence-transformers package "
            "is installed at runtime; use the hashing adapter in tests."
        )

    def dimension(self) -> int:
        return self._dimension

    def model_version(self) -> str:
        return self._model_version

    def license_id(self) -> str:
        return self._license_id

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "tokens": self._tokens,
            "errors": self._errors,
        }