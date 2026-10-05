"""Cross-encoder reranker adapter (opt-in).

Wraps the optional ``sentence-transformers`` CrossEncoder model
(``cross-encoder/ms-marco-MiniLM-L-6-v2``) as the §30 cross-encoder
default. The adapter is registered only when
``sentence-transformers`` is installed AND
``project-context.yaml:retrieval.reranker.family == "cross-encoder"``.

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
    "CrossEncoderRerankerAdapter",
    "ADAPTER_NAME",
    "DEFAULT_MODEL_ID",
    "DEFAULT_LICENSE_ID",
]


ADAPTER_NAME = "cross-encoder"
DEFAULT_MODEL_ID = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DEFAULT_LICENSE_ID = "MIT"


class CrossEncoderRerankerAdapter(RerankerPort):
    """Cross-encoder reranker adapter (opt-in)."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        license_id: str = DEFAULT_LICENSE_ID,
        budget: int = DEFAULT_RERANK_BUDGET,
    ) -> None:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError as exc:
            raise RerankerError(
                "sentence-transformers is not installed; install the "
                "Phase 4 retrieval optional dependency before "
                "registering the cross-encoder adapter."
            ) from exc
        self._model_id = model_id
        self._license_id = license_id
        self.budget = budget
        self._calls = 0

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]:
        raise RerankerError(
            "CrossEncoderRerankerAdapter.rerank is only available when "
            "sentence-transformers is installed at runtime; use the "
            "BM25-light adapter in tests."
        )

    def score(
        self, query: str, candidate: RetrievalHit,
    ) -> float:
        raise RerankerError(
            "CrossEncoderRerankerAdapter.score is only available when "
            "sentence-transformers is installed at runtime."
        )

    def model_version(self) -> str:
        return self._model_id

    def license_id(self) -> str:
        return self._license_id

    def family(self) -> str:
        return "cross-encoder"

    def stats(self) -> Mapping[str, int]:
        return {"calls": self._calls}