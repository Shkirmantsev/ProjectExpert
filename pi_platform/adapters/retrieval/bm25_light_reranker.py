"""BM25-light reranker adapter.

Wraps :class:`pi_platform.core.retrieval.reranker.Bm25LightRerankerCore`
as a thin adapter so the §30 spec's "lighter-weight reranker
fallback" scenario registers consistently with the cross-encoder
and the optional ColBERT-style adapter.
"""

from __future__ import annotations

from pi_platform.core.retrieval.reranker import (
    BM25_LIGHT_LICENSE,
    BM25_LIGHT_VERSION,
    Bm25LightRerankerCore,
)


__all__ = [
    "Bm25LightRerankerAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "bm25-light"


class Bm25LightRerankerAdapter(Bm25LightRerankerCore):
    """Stdlib-only BM25-light reranker fallback adapter."""

    def __init__(self, budget: int = 50) -> None:
        super().__init__(budget=budget)
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name


# Module-level aliases used by the license inventory.
RERANKER_VERSION = BM25_LIGHT_VERSION
RERANKER_LICENSE = BM25_LIGHT_LICENSE
RERANKER_FAMILY = "bm25-light"