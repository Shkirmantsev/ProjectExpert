"""Qwen3-Reranker adapter (F2 production STUB).

Implements :class:`pi_platform.ports.retrieval.reranker.RerankerPort`
for the Qwen3-Reranker family. The Qwen3-Reranker has its own
prompt template and inference semantics, so it is a separate
adapter from the cross-encoder — not a parameter swap.

The Qwen3 model artifact is approximately 1.2 GB before
runtime overhead; per plan §18.1 this profile is opt-in and
stays off by default until benchmarks demonstrate acceptable
RAM, startup time, batch latency, and p95 query latency.

This is the production STUB: the real binding (a follow-up
that imports the optional Qwen3 dependency) replaces
``_score_impl`` with a function that calls the model. The
stub's score uses the same deterministic overlap baseline as
the cross-encoder, but applies the Qwen3 prompt template so
the rerank_text shape is the production shape.
"""

from __future__ import annotations

from typing import Callable, Mapping, Optional, Sequence

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit
from pi_platform.ports.retrieval.rerank_text import (
    DEFAULT_MAX_PAIR_TOKENS,
    RerankTextBuilder,
)
from pi_platform.ports.retrieval.reranker import (
    DEFAULT_RERANK_BUDGET,
    RerankerError,
    RerankerPort,
)


__all__ = [
    "Qwen3RerankerAdapter",
    "ADAPTER_NAME",
    "DEFAULT_MODEL_ID",
    "DEFAULT_LICENSE_ID",
    "DEFAULT_PROMPT_VERSION",
]


ADAPTER_NAME = "qwen3-reranker"
DEFAULT_MODEL_ID = "qwen3-reranker-0.6b"
DEFAULT_LICENSE_ID = "Apache-2.0"
DEFAULT_PROMPT_VERSION = "qwen3-reranker-prompt/v1"


class Qwen3RerankerAdapter(RerankerPort):
    """Qwen3-Reranker adapter (production STUB).

    The Qwen3-Reranker has its own prompt template:
        <|im_start|>system
        You are a search relevance judge.<|im_end|>
        <|im_start|>user
        <Instruct>: Given a query and a passage, decide whether
        the passage is relevant to the query. Output 'Yes' or 'No'.
        <Query>: {query}
        <Passage>: {passage}<|im_end|>
    The adapter wraps the prompt template around the
    ``RerankTextBuilder`` output and delegates to a scoring
    function. Until the real Qwen3 binding lands, the scoring
    function is a deterministic overlap baseline; the prompt
    template is the production shape.
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL_ID,
        model_revision: str = "pinned-stub",
        license_id: str = DEFAULT_LICENSE_ID,
        budget: int = DEFAULT_RERANK_BUDGET,
        *,
        max_pair_tokens: int = DEFAULT_MAX_PAIR_TOKENS,
        timeout_seconds: float = 8.0,
        max_batch_size: int = 8,  # Qwen3 is heavier; smaller batch
        prompt_version: str = DEFAULT_PROMPT_VERSION,
        score_impl: Optional[Callable[[str, str], float]] = None,
    ) -> None:
        if max_pair_tokens <= 0:
            raise RerankerError(
                f"max_pair_tokens must be positive, got {max_pair_tokens}"
            )
        if max_batch_size <= 0:
            raise RerankerError(
                f"max_batch_size must be positive, got {max_batch_size}"
            )
        self._model_id = model_id
        self._model_revision = model_revision
        self._license_id = license_id
        self.budget = budget
        self._max_pair_tokens = max_pair_tokens
        self._timeout_seconds = timeout_seconds
        self._max_batch_size = max_batch_size
        self._prompt_version = prompt_version
        self._score_impl = score_impl or self._default_score
        self._text_builder = RerankTextBuilder(
            max_pair_tokens=max_pair_tokens,
        )
        self._calls = 0
        self._timeouts = 0
        self._errors = 0

    @property
    def backend_name(self) -> str:
        return ADAPTER_NAME

    def model_version(self) -> str:
        return f"{self._model_id}@{self._model_revision}"

    def license_id(self) -> str:
        return self._license_id

    def family(self) -> str:
        return "qwen3-reranker"

    def stats(self) -> Mapping[str, int]:
        return {
            "calls": self._calls,
            "timeouts": self._timeouts,
            "errors": self._errors,
            "prompt_version": self._prompt_version,
        }

    def rerank(
        self, query: str, candidates: Sequence[RetrievalHit],
        *, top_k: int = 10,
    ) -> Sequence[RetrievalHit]:
        if not candidates:
            return ()
        if top_k <= 0:
            raise RerankerError(f"top_k must be positive, got {top_k}")
        # Qwen3 is heavier: smaller pool + smaller batch.
        pool = list(candidates[: self.budget])
        scored: list[tuple[RetrievalHit, float]] = []
        batch: list[RetrievalHit] = []
        for hit in pool:
            batch.append(hit)
            if len(batch) >= self._max_batch_size:
                scored.extend(self._score_batch(query, batch))
                batch = []
        if batch:
            scored.extend(self._score_batch(query, batch))
        scored.sort(key=lambda p: (-p[1], p[0].chunkId))
        seen: set[str] = set()
        out: list[RetrievalHit] = []
        for hit, score in scored:
            if hit.chunkId in seen:
                continue
            seen.add(hit.chunkId)
            out.append(self._with_score(hit, score))
            if len(out) >= top_k:
                break
        return tuple(out)

    def score(self, query: str, candidate: RetrievalHit) -> float:
        text = self._text_builder.build(query=query, hit=candidate)
        return self._score_impl(query, self._wrap_prompt(query, text.passage))

    # -- internal helpers --------------------------------------------

    def _score_batch(
        self, query: str, batch: Sequence[RetrievalHit],
    ) -> list[tuple[RetrievalHit, float]]:
        out: list[tuple[RetrievalHit, float]] = []
        for hit in batch:
            text = self._text_builder.build(query=query, hit=hit)
            try:
                raw = self._score_impl(
                    query, self._wrap_prompt(query, text.passage),
                )
            except Exception as exc:
                self._errors += 1
                raise RerankerError(
                    f"qwen3-reranker scoring failed: {exc}"
                ) from exc
            import math
            score = 1.0 / (1.0 + math.exp(-raw))
            self._calls += 1
            out.append((hit, max(0.0, min(1.0, score))))
        return out

    def _wrap_prompt(self, query: str, passage: str) -> str:
        """Wrap the (query, passage) pair in the Qwen3 chat
        template. The real binding decodes the model's
        ``Yes``/``No`` response into the score; the stub
        delegates the wrapped prompt to the score function."""
        return (
            "<|im_start|>system\n"
            "You are a search relevance judge.<|im_end|>\n"
            "<|im_start|>user\n"
            "<Instruct>: Given a query and a passage, decide "
            "whether the passage is relevant to the query. "
            "Output 'Yes' or 'No'.\n"
            f"<Query>: {query}\n"
            f"<Passage>: {passage}<|im_end|>\n"
            "<|im_start|>assistant\n"
        )

    def _with_score(self, hit: RetrievalHit, score: float) -> RetrievalHit:
        from dataclasses import replace
        return replace(hit, score=score)

    @staticmethod
    def _default_score(query: str, wrapped_prompt: str) -> float:
        """Stdlib-only overlap baseline. The real binding
        returns ``+score`` for ``Yes`` and ``-score`` for
        ``No``; the stub returns the deterministic overlap of
        query tokens with the wrapped prompt."""
        import math
        import re
        q_tokens = {t for t in re.findall(r"[A-Za-z0-9]{2,}", query.lower())}
        p_tokens = re.findall(r"[A-Za-z0-9]{2,}", wrapped_prompt.lower())
        if not q_tokens or not p_tokens:
            return 0.0
        overlap = sum(1 for t in p_tokens if t in q_tokens)
        return overlap / max(1.0, math.sqrt(len(p_tokens)))
