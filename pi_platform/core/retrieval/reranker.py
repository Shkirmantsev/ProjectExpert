"""Default reranker core.

Implements :class:`pi_platform.ports.retrieval.reranker.RerankerPort`
with a stdlib-only BM25-light fallback so the platform can run on a
machine without a cross-encoder model. The cross-encoder and the
optional ColBERT-style adapter are provided as opt-in adapters
under :mod:`pi_platform.adapters.retrieval`.

The BM25-light scoring reuses the §26 BM25 idea (token overlap,
inverse document frequency approximation) so the reranker behaves
sensibly without a model download while still obeying the bounded
candidate-set invariant.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Mapping, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.reranker import (
    DEFAULT_RERANK_BUDGET,
    RerankerError,
    RerankerPort,
)


__all__ = [
    "Bm25LightRerankerCore",
    "BM25_LIGHT_K1",
    "BM25_LIGHT_B",
    "BM25_LIGHT_VERSION",
    "BM25_LIGHT_LICENSE",
]


BM25_LIGHT_K1 = 1.5
BM25_LIGHT_B = 0.75
BM25_LIGHT_VERSION = "bm25-light-1.0.0"
BM25_LIGHT_LICENSE = "Apache-2.0"
_TOKEN_RE = re.compile(r"[\w\u0400-\u04FF]+", flags=re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


class Bm25LightRerankerCore(RerankerPort):
    """Stdlib-only BM25-light reranker fallback."""

    family_name = "bm25-light"

    def __init__(self, budget: int = DEFAULT_RERANK_BUDGET) -> None:
        self.budget = budget
        self._calls = 0
        self._errors = 0

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]:
        self._calls += 1
        if top_k <= 0:
            raise RerankerError(f"top_k must be positive, got {top_k}")
        bounded = list(candidates[: self.budget])
        scored = [
            (self.score(query, hit), hit) for hit in bounded
        ]
        scored.sort(key=lambda pair: (-pair[0], pair[1].chunkId))
        return [hit for _, hit in scored[:top_k]]

    def score(
        self, query: str, candidate: RetrievalHit,
    ) -> float:
        try:
            q_tokens = _tokens(query)
            if not q_tokens:
                return 0.0
            doc_tokens = _tokens(candidate.snippet)
            if not doc_tokens:
                return 0.0
            tf = Counter(doc_tokens)
            doc_len = len(doc_tokens)
            score = 0.0
            for tok in q_tokens:
                f = tf.get(tok, 0)
                if f == 0:
                    continue
                idf = math.log(1 + (1.0 / max(1, f)))
                numerator = f * (BM25_LIGHT_K1 + 1)
                denominator = (
                    f
                    + BM25_LIGHT_K1
                    * (1 - BM25_LIGHT_B)
                    + BM25_LIGHT_B * doc_len
                )
                score += idf * (numerator / denominator)
            return float(min(max(score / 10.0, 0.0), 1.0))
        except Exception as exc:
            self._errors += 1
            raise RerankerError(
                f"Bm25LightReranker score failed: {exc}"
            ) from exc

    def model_version(self) -> str:
        return BM25_LIGHT_VERSION

    def license_id(self) -> str:
        return BM25_LIGHT_LICENSE

    def family(self) -> str:
        return self.family_name

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "errors": self._errors,
            "budget": self.budget,
        }


def _first_iterable(items: Iterable[RetrievalHit]) -> list[RetrievalHit]:
    return list(items)