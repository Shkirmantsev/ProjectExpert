"""HashingEmbeddingModel adapter.

Wraps :class:`pi_platform.core.retrieval.embedding_model.HashingEmbeddingModel`
as a thin adapter so the registry / CLI can introspect the same
shape across the hashing and multilingual sentence-transformer
backends. The adapter is the stdlib-only fallback the §25 spec
mandates.
"""

from __future__ import annotations

from typing import Mapping

from pi_platform.core.retrieval.embedding_model import (
    HASHING_DEFAULT_DIMENSION,
    HASHING_DEFAULT_VERSION,
    HASHING_LICENSE_ID,
    HashingEmbeddingModel,
)


__all__ = [
    "HashingEmbeddingAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "hashing"


class HashingEmbeddingAdapter(HashingEmbeddingModel):
    """Adapter alias so registry lookups stay backend-neutral."""

    def __init__(
        self, dimension: int = HASHING_DEFAULT_DIMENSION,
        model_version: str = HASHING_DEFAULT_VERSION,
    ) -> None:
        super().__init__(
            dimension=dimension, model_version=model_version,
        )
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name

    def stats(self) -> Mapping[str, int]:
        base = dict(super().stats())
        base["backend"] = ADAPTER_NAME
        return base


# Module-level aliases used by the license inventory.
DIMENSION = HASHING_DEFAULT_DIMENSION
VERSION = HASHING_DEFAULT_VERSION
LICENSE_ID = HASHING_LICENSE_ID