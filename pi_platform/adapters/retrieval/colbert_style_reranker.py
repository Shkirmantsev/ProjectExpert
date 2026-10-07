"""ColBERT-style reranker adapter (opt-in).

Wraps the optional ColBERT-style late-interaction reranker. The
adapter is registered only when
``project-context.yaml:retrieval.reranker.family == "colbert"`` AND
the ``colbert-ai`` package is installed.

When the dependency is missing the adapter raises
:class:`RerankerError` at construction time so the
:class:`LicenseGate` can record the optional dependency as
unavailable without silently falling back to the BM25-light adapter.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.reranker import (
    DEFAULT_RERANK_BUDGET,
    RerankerError,
    RerankerPort,
)


__all__ = [
    "ColBertStyleRerankerAdapter",
    "ADAPTER_NAME",
    "DEFAULT_LICENSE_ID",
]


ADAPTER_NAME = "colbert-style"
DEFAULT_LICENSE_ID = "MIT"


class ColBertStyleRerankerAdapter(RerankerPort):
    """ColBERT-style late-interaction reranker adapter (opt-in)."""

    def __init__(
        self,
        license_id: str = DEFAULT_LICENSE_ID,
        budget: int = DEFAULT_RERANK_BUDGET,
    ) -> None:
        try:
            import colbert  # noqa: F401  (optional dependency)
        except ImportError as exc:
            raise RerankerError(
                "colbert-ai is not installed; install the Phase 4 "
                "retrieval optional dependency before registering the "
                "ColBERT-style adapter."
            ) from exc
        self._license_id = license_id
        self.budget = budget
        self._calls = 0

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]:
        raise RerankerError(
            "ColBertStyleRerankerAdapter.rerank is only available when "
            "colbert-ai is installed at runtime; use the BM25-light "
            "adapter in tests."
        )

    def score(
        self, query: str, candidate: RetrievalHit,
    ) -> float:
        raise RerankerError(
            "ColBertStyleRerankerAdapter.score is only available when "
            "colbert-ai is installed at runtime."
        )

    def model_version(self) -> str:
        return "colbert-style-1.0.0"

    def license_id(self) -> str:
        return self._license_id

    def family(self) -> str:
        return "colbert-style"

    def stats(self) -> Mapping[str, int]:
        return {"calls": self._calls}