"""Qwen3-Embedding-0.6B embedding adapter (Change Package C1, STUB).

Placeholder for the second production profile behind
:class:`pi_platform.ports.retrieval.embedding_model.EmbeddingModelPort`.
Its vectors are persisted in a separate
``embedding_profile_hash`` namespace and never mixed with the
EmbeddingGemma 2 namespace. The real binding requires the optional
``sentence-transformers`` package (``semantic-embeddings`` dependency
group) and the pinned Qwen3-Embedding-0.6B weights; this build is
stdlib-only, so the adapter preserves the production contract —
``dimension()``, ``model_version()``, ``license_id()``,
``profile()`` — and raises :class:`EmbeddingModelError` from
``embed()`` / ``embed_batch()`` with a clear "not bound" message.
The stub is replaced by a real adapter in a follow-up (C.1.5) that
imports sentence-transformers and pins a real model revision in
``distribution/licenses/model-licenses.json``.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)
from pi_platform.ports.retrieval.embedding_profile import (
    QWEN3_EMBEDDING_0_6B_1024,
    EmbeddingProfile,
)


__all__ = [
    "Qwen3EmbeddingModel",
    "ADAPTER_NAME",
    "DEFAULT_LICENSE_ID",
]


ADAPTER_NAME = "qwen3-embedding-0.6b"
# Recorded license for the Qwen3-Embedding model family; the real
# binding reads the pinned entry from
# distribution/licenses/model-licenses.json.
DEFAULT_LICENSE_ID = "Apache-2.0"

_NOT_BOUND_MESSAGE = (
    "Qwen3-Embedding-0.6B is not bound in this build; install "
    "semantic-embeddings extras and pin a real model revision in "
    "distribution/licenses/model-licenses.json"
)


class Qwen3EmbeddingModel(EmbeddingModelPort):
    """Stub adapter for the Qwen3-Embedding-0.6B profile.

    The real binding requires ``sentence-transformers`` and the pinned
    Qwen3-Embedding-0.6B weights; this stub preserves the production
    contract — ``model_version()``, ``license_id()``, ``dimension()``,
    ``profile()`` — and raises :class:`EmbeddingModelError` from
    ``embed()`` and ``embed_batch()`` with a clear "not bound in C1
    stub" message. The stub will be replaced by a real adapter in a
    follow-up that imports sentence-transformers.
    """

    def __init__(
        self, profile: EmbeddingProfile = QWEN3_EMBEDDING_0_6B_1024,
    ) -> None:
        self._profile = profile
        self._calls = 0
        self._tokens = 0
        self._errors = 0

    def embed(self, text: str) -> Sequence[float]:
        del text
        self._calls += 1
        self._errors += 1
        raise EmbeddingModelError(_NOT_BOUND_MESSAGE)

    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        del texts
        self._calls += 1
        self._errors += 1
        raise EmbeddingModelError(_NOT_BOUND_MESSAGE)

    def dimension(self) -> int:
        return self._profile.output_dimension

    def model_version(self) -> str:
        return self._profile.identity()

    def license_id(self) -> str:
        return DEFAULT_LICENSE_ID

    def profile(self) -> EmbeddingProfile:
        """Return the :class:`EmbeddingProfile` this adapter was built for."""

        return self._profile

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "tokens": self._tokens,
            "errors": self._errors,
        }
