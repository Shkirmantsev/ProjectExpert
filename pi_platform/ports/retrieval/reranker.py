"""Reranker port for the v0.8 Phase 4 retrieval layer.

Covers architecture section §30 (Optional Advanced Reranking). The
:class:`RerankerPort` exposes the cross-encoder default, the BM25-
light fallback and the optional ColBERT-style adapter behind a
single pluggable surface that the multi-stage retrieval pipeline
invokes on the bounded candidate set produced by the candidate
generation, fusion, metadata filter and graph/hierarchy expansion
stages.

Rerankers operate on bounded candidate sets only. The pipeline
MUST enforce a :attr:`RerankerPort.budget` cap so a runaway
candidate set never reaches the reranker.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit


__all__ = [
    "RerankerPort",
    "RerankerError",
    "RerankPolicy",
    "MEDIA_MODALITIES",
    "RERANK_FALLBACK_RRF",
    "RERANK_FALLBACK_FAIL",
    "hit_modality",
    "stamp_rerank_order",
    "ensure_rerank_order",
]


class RerankerError(RuntimeError):
    """Raised when a reranker cannot satisfy a request."""


# Maximum candidates a reranker is allowed to see in a single call.
# The multi-stage pipeline MUST pre-trim its candidate set to this
# budget before calling :meth:`RerankerPort.rerank`.
DEFAULT_RERANK_BUDGET = 50

#: Media modalities the platform can index. A text-only reranker MUST NOT
#: demote a media candidate that the multimodal embedding space ranked
#: highly: it cannot see the pixels.
MEDIA_MODALITIES = frozenset({"image", "audio", "video"})

#: On reranker failure, keep the pre-rerank (fusion) order.
RERANK_FALLBACK_RRF = "rrf"
#: On reranker failure, propagate the error.
RERANK_FALLBACK_FAIL = "fail"


@dataclass(frozen=True)
class RerankPolicy:
    """Operator-controllable reranking policy.

    The policy is the single place that decides whether reranking runs,
    which family runs it, how many candidates it may reorder and what
    happens when it fails.

    ``enabled`` is the default-on behaviour: BM25-light reranking is cheap
    and improves precision, so it is active on the first retrieval phase.
    It can be switched off explicitly for deployments that prefer the raw
    fusion order or that will later use a more expensive reranker.
    """

    enabled: bool = True
    family: str = "bm25-light"
    top_n: int = 10
    timeout_ms: int = 2000
    fallback: str = RERANK_FALLBACK_RRF

    def __post_init__(self) -> None:
        if self.top_n <= 0:
            raise ValueError(
                f"RerankPolicy.top_n must be positive, got {self.top_n}"
            )
        if self.timeout_ms <= 0:
            raise ValueError(
                f"RerankPolicy.timeout_ms must be positive, got {self.timeout_ms}"
            )
        if self.fallback not in (RERANK_FALLBACK_RRF, RERANK_FALLBACK_FAIL):
            raise ValueError(
                f"RerankPolicy.fallback must be {RERANK_FALLBACK_RRF!r} or "
                f"{RERANK_FALLBACK_FAIL!r}, got {self.fallback!r}"
            )


def hit_modality(hit: RetrievalHit) -> str:
    """Return the modality of ``hit``: ``"text"`` or a media modality.

    The modality is carried in the chunk metadata so it survives indexing
    and retrieval. A chunk that was embedded together with an image,
    recording or clip is a media candidate.
    """

    try:
        extensions = hit.metadata.extensions or {}
    except AttributeError:  # pragma: no cover - defensive
        return "text"
    marker = extensions.get("media") if isinstance(extensions, Mapping) else None
    if isinstance(marker, str) and marker.lower() in MEDIA_MODALITIES:
        return marker.lower()
    return "text"


def stamp_rerank_order(
    hits: Sequence[RetrievalHit], scores: Sequence[float],
) -> list[RetrievalHit]:
    """Attach the reranker's own score and rank to the returned hits.

    The reranker's decision MUST survive the handover to the selection
    stage. The original retrieval score is preserved on the hit so it stays
    available for fallback and diagnostics.
    """

    stamped: list[RetrievalHit] = []
    for rank, (hit, score) in enumerate(zip(hits, scores), start=1):
        stamped.append(
            replace(hit, rerankScore=float(score), rerankRank=rank)
        )
    return stamped


def ensure_rerank_order(hits: Sequence[RetrievalHit]) -> list[RetrievalHit]:
    """Guarantee that every hit carries an explicit rerank rank.

    A reranker that does not stamp its own scores still expresses its
    decision through the ORDER of the returned candidates. This helper
    records that order so the selection stage can honour it.
    """

    out: list[RetrievalHit] = []
    for position, hit in enumerate(hits, start=1):
        if hit.rerankRank > 0:
            out.append(hit)
            continue
        out.append(replace(hit, rerankRank=position))
    return out


class RerankerPort(abc.ABC):
    """Abstract pluggable reranker port."""

    #: Default candidate budget for the multi-stage pipeline.
    budget: int = DEFAULT_RERANK_BUDGET

    @abc.abstractmethod
    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]: ...

    @abc.abstractmethod
    def score(
        self, query: str, candidate: RetrievalHit,
    ) -> float: ...

    @abc.abstractmethod
    def model_version(self) -> str: ...

    @abc.abstractmethod
    def license_id(self) -> str: ...

    @abc.abstractmethod
    def family(self) -> str: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...