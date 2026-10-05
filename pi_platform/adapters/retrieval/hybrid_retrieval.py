"""Hybrid retrieval composition adapter.

Binds :class:`pi_platform.core.retrieval.hybrid_retrieval.HybridRetrievalCore`
to the Phase 3 dense / sparse ports and to the
:class:`pi_platform.adapters.retrieval.identifier_query_detector.IdentifierQueryDetector`.

The adapter is the production entry point for the §27 hybrid
retrieval scenario; alternative compositions can be registered by
binding different dense / sparse ports.
"""

from __future__ import annotations

from typing import Callable, Sequence

from pi_platform.core.retrieval.hybrid_retrieval import HybridRetrievalCore
from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit


__all__ = [
    "HybridRetrievalAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "hybrid-rrf"


class HybridRetrievalAdapter(HybridRetrievalCore):
    """Production hybrid retrieval composition adapter."""

    def __init__(
        self,
        dense_query: Callable[[str, int], Sequence[RetrievalHit]],
        sparse_query: Callable[[str, int], Sequence[RetrievalHit]],
        identifier_detector: Callable[[str], bool] | None = None,
        exact_lookup: Callable[[str], Sequence[RetrievalHit]] | None = None,
        fusion_strategy: str = "rrf",
    ) -> None:
        super().__init__(
            dense_query=dense_query,
            sparse_query=sparse_query,
            identifier_detector=identifier_detector,
            exact_lookup=exact_lookup,
            fusion_strategy=fusion_strategy,
            level=0,
        )
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name

    @property
    def fusion_strategy(self) -> str:
        return self._fusion_strategy_value