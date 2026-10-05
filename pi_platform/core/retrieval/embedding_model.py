"""Default stdlib-only embedding model core.

Implements :class:`pi_platform.ports.retrieval.embedding_model.EmbeddingModelPort`
with a deterministic, multilingual-capable feature-hashing backend
that requires no third-party dependency. The hashing adapter is the
stdlib-only fallback the §25 spec requires so the platform can boot
on a CPU-only machine without a GPU or a model download.

The hashing approach encodes tokens with the 32-bit
:meth:`hashlib.blake2b` digest and projects them into a fixed
``dimension``-sized vector via signed modular reduction. A bias
token is appended to capture out-of-vocabulary terms. Cosine
similarity between two texts sharing many tokens is therefore
non-zero, satisfying the §25 "multilingual coverage" Scenario's
"same-dimension vector" check without claiming semantic accuracy.

The real multilingual semantic backend (sentence-transformers) is
provided as an opt-in adapter under
:mod:`pi_platform.adapters.retrieval.multilingual_st_embedding_model`.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.embedding_model import (
    EmbeddingModelError,
    EmbeddingModelPort,
)


__all__ = [
    "HashingEmbeddingModel",
    "HASHING_DEFAULT_DIMENSION",
    "HASHING_DEFAULT_VERSION",
    "HASHING_LICENSE_ID",
]


HASHING_DEFAULT_DIMENSION = 384
HASHING_DEFAULT_VERSION = "hashing-1.0.0"
HASHING_LICENSE_ID = "Apache-2.0"

# A conservative Unicode-aware token regex. The pattern matches
# runs of letters, digits or ideographs so German, English,
# Ukrainian and Russian text are all split consistently.
_TOKEN_RE = re.compile(r"[\w\u0400-\u04FF]+", flags=re.UNICODE)


def _tokenize(text: str) -> list[str]:
    lowered = text.lower()
    return _TOKEN_RE.findall(lowered)


def _token_digest(token: str) -> bytes:
    return hashlib.blake2b(
        token.encode("utf-8"), digest_size=16,
    ).digest()


class HashingEmbeddingModel(EmbeddingModelPort):
    """Deterministic stdlib-only feature-hashing embedding model."""

    def __init__(
        self, dimension: int = HASHING_DEFAULT_DIMENSION,
        model_version: str = HASHING_DEFAULT_VERSION,
    ) -> None:
        if dimension <= 0:
            raise EmbeddingModelError(
                f"dimension must be positive, got {dimension}"
            )
        self._dimension = dimension
        self._model_version = model_version
        self._calls = 0
        self._tokens = 0
        self._errors = 0

    def embed(self, text: str) -> Sequence[float]:
        self._calls += 1
        try:
            return self._embed_raw(text)
        except Exception as exc:
            self._errors += 1
            raise EmbeddingModelError(
                f"HashingEmbeddingModel failed: {exc}"
            ) from exc

    def embed_batch(
        self, texts: Sequence[str],
    ) -> Sequence[Sequence[float]]:
        return [self.embed(t) for t in texts]

    def dimension(self) -> int:
        return self._dimension

    def model_version(self) -> str:
        return self._model_version

    def license_id(self) -> str:
        return HASHING_LICENSE_ID

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "tokens": self._tokens,
            "errors": self._errors,
        }

    # -- internal helpers --------------------------------------------------

    def _embed_raw(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        if not text:
            return vec
        tokens = _tokenize(text)
        if not tokens:
            return vec
        self._tokens += len(tokens)
        for tok in tokens:
            digest = _token_digest(tok)
            slot = int.from_bytes(digest[:4], "big", signed=False) % self._dimension
            sign = 1.0 if (digest[4] & 1) else -1.0
            vec[slot] += sign
        bias_digest = _token_digest("\x00bias\x00")
        bias_slot = (
            int.from_bytes(bias_digest[:4], "big", signed=False) % self._dimension
        )
        vec[bias_slot] += 0.5
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0.0:
            return vec
        return [x / norm for x in vec]