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

Two properties matter for correctness:

* **The reranker's decision must survive the handover.** The returned
  hits carry the reranker's own score and rank, so the selection stage
  orders by the rerank decision instead of re-sorting by the earlier
  retrieval score and silently undoing the rerank.
* **A text-only reranker must not demote media.** A chunk that was
  embedded together with an image, recording or clip is ranked by the
  multimodal embedding space; BM25-light cannot see its pixels. Media
  candidates therefore keep their retrieval order and are never pushed
  below text candidates because their text representation is empty.
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
    RerankPolicy,
    hit_modality,
    stamp_rerank_order,
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
BM25_LIGHT_VERSION = "bm25-light-1.1.0"
BM25_LIGHT_LICENSE = "Apache-2.0"
_TOKEN_RE = re.compile(r"[\w\u0400-\u04FF]+", flags=re.UNICODE)


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


class Bm25LightRerankerCore(RerankerPort):
    """Stdlib-only BM25-light reranker fallback."""

    family_name = "bm25-light"

    def __init__(
        self, budget: int = DEFAULT_RERANK_BUDGET,
        *, policy: RerankPolicy | None = None,
    ) -> None:
        self.budget = budget
        self.policy = policy or RerankPolicy()
        self._calls = 0
        self._errors = 0
        self._media_preserved = 0

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]:
        self._calls += 1
        if top_k <= 0:
            raise RerankerError(f"top_k must be positive, got {top_k}")
        bounded = list(candidates[: self.budget])
        if not bounded:
            return []
        text_hits = [hit for hit in bounded if hit_modality(hit) == "text"]
        media_hits = [hit for hit in bounded if hit_modality(hit) != "text"]

        # Text candidates are scored by BM25-light.
        scored = [(self.score(query, hit), hit) for hit in text_hits]
        scored.sort(key=lambda pair: (-pair[0], pair[1].chunkId))
        ordered_text = [hit for _, hit in scored]
        text_scores = [score for score, _ in scored]

        # Media candidates keep their retrieval order: the text reranker
        # cannot see their content, so it abstains instead of demoting
        # them. They are ranked against the text group by the position
        # their group held in the retrieval order, never by a text score.
        ordered_media = list(media_hits)
        media_scores = [hit.score for hit in ordered_media]
        if ordered_media:
            self._media_preserved += len(ordered_media)

        ordered, scores = self._merge_groups(
            bounded, ordered_text, text_scores, ordered_media, media_scores,
        )
        stamped = stamp_rerank_order(ordered, scores)
        return stamped[:top_k]

    @staticmethod
    def _merge_groups(
        original: Sequence[RetrievalHit],
        ordered_text: Sequence[RetrievalHit],
        text_scores: Sequence[float],
        ordered_media: Sequence[RetrievalHit],
        media_scores: Sequence[float],
    ) -> tuple[list[RetrievalHit], list[float]]:
        """Merge the text and media groups without demoting either.

        The group whose best candidate came first in the retrieval order
        leads. Inside a group the reranker's own order is used. A media
        candidate is therefore never pushed below a text candidate just
        because its text representation is empty.
        """

        if not ordered_media:
            return list(ordered_text), list(text_scores)
        if not ordered_text:
            return list(ordered_media), list(media_scores)
        original_rank = {hit.chunkId: index for index, hit in enumerate(original)}
        text_anchor = min(original_rank.get(hit.chunkId, 0) for hit in ordered_text)
        media_anchor = min(original_rank.get(hit.chunkId, 0) for hit in ordered_media)
        if media_anchor < text_anchor:
            return (
                list(ordered_media) + list(ordered_text),
                list(media_scores) + list(text_scores),
            )
        return (
            list(ordered_text) + list(ordered_media),
            list(text_scores) + list(media_scores),
        )

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
            "media_preserved": self._media_preserved,
        }


def _first_iterable(items: Iterable[RetrievalHit]) -> list[RetrievalHit]:
    return list(items)