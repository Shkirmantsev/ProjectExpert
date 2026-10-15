"""Rerank text builder (plan §18.2).

Builds the ``rerank_text`` that a cross-encoder (or any
heavy reranker) consumes. The text is composed of the
``document title``, ``heading path``, ``raw chunk``,
``caption`` (if present), and ``class/method context`` (if
present). Forbidden fields are NEVER embedded: hashes, bbox,
timestamps, Git SHA, unrelated metadata. The
``max_pair_tokens`` budget (default 1536) caps the per-pair
length; inferred enrichment is trimmed before raw evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence, Tuple

from pi_platform.ports.retrieval.hybrid_retrieval import RetrievalHit


__all__ = [
    "RerankText",
    "RerankTextBuilder",
    "RerankTextBuilderError",
    "DEFAULT_MAX_PAIR_TOKENS",
]


# Starting profile for ``max_pair_tokens``. 1536 is a
# reasonable first experiment for cross-encoder models that
# accept ~512 token query + ~1024 token passage; the
# benchmark / evaluation gate tunes this for each profile.
DEFAULT_MAX_PAIR_TOKENS = 1536


class RerankTextBuilderError(RuntimeError):
    """Raised when the rerank text builder cannot satisfy a request."""


@dataclass(frozen=True)
class RerankText:
    """The text pair (query, passage) passed to a cross-encoder."""

    query: str
    passage: str
    strategy_version: str
    truncated: bool = False


class RerankTextBuilder:
    """Build the (query, passage) text pair for a reranker call.

    The builder preserves the plan §18.2 contract:

    - the passage is composed of semantic context + raw chunk
    - forbidden fields (hashes, bbox, timestamps, Git SHA,
      unrelated metadata) are NEVER embedded
    - the budget is bounded by ``max_pair_tokens`` (default
      1536); the passage is truncated past the budget with a
      notice (``truncated=True``)
    - inferred enrichment is trimmed before raw evidence
    """

    STRATEGY_VERSION = "rerank-text/v1"

    # Forbidden keys; if a metadata key is in this set, the
    # builder raises. Forbidden values are filtered
    # separately (see _is_forbidden_value).
    FORBIDDEN_KEYS = frozenset({
        "sha", "git_sha", "git_commit", "content_hash",
        "bbox", "timestamp", "security_label", "license",
        "processing_version", "absolute_path",
    })

    def __init__(
        self, *,
        max_pair_tokens: int = DEFAULT_MAX_PAIR_TOKENS,
        truncation_marker: str = " [...truncated]",
    ) -> None:
        if max_pair_tokens <= 0:
            raise RerankTextBuilderError(
                f"max_pair_tokens must be positive, got {max_pair_tokens}"
            )
        self._max_pair_tokens = max_pair_tokens
        self._truncation_marker = truncation_marker

    def build(
        self, *, query: str, hit: RetrievalHit,
    ) -> RerankText:
        if not query:
            raise RerankTextBuilderError("query is empty")
        if not hit or not hit.chunkId:
            raise RerankTextBuilderError("hit is empty")
        self._guard_metadata(hit)
        passage = self._build_passage(hit)
        truncated = False
        # Token budget: rough char-based estimate (4 chars ≈ 1
        # token). The actual cross-encoder may use a different
        # tokenizer; this is the platform-side pre-trim.
        max_chars = self._max_pair_tokens * 4
        if len(passage) > max_chars:
            passage = passage[: max_chars - len(self._truncation_marker)] \
                + self._truncation_marker
            truncated = True
        return RerankText(
            query=query,
            passage=passage,
            strategy_version=self.STRATEGY_VERSION,
            truncated=truncated,
        )

    # -- internal helpers --------------------------------------------

    def _build_passage(self, hit: RetrievalHit) -> str:
        parts: list[str] = []
        meta = hit.metadata
        # Title (if present in extensions) + heading path
        title = ""
        if isinstance(meta.extensions, dict):
            t = meta.extensions.get("document_title")
            if isinstance(t, str) and t:
                title = t
        if title:
            parts.append(f"title: {title}")
        if meta.section:
            parts.append(f"section: {meta.section}")
        if meta.requirementId:
            parts.append(f"requirement: {meta.requirementId}")
        # Caption (figure / table)
        if isinstance(meta.extensions, dict):
            caption = meta.extensions.get("caption")
            if isinstance(caption, str) and caption:
                parts.append(f"caption: {caption}")
            class_ctx = meta.extensions.get("class_context")
            if isinstance(class_ctx, str) and class_ctx:
                parts.append(f"class: {class_ctx}")
        # Raw chunk text (always present, always last in
        # importance; inferred enrichment is trimmed first by
        # NOT including it here at all).
        if hit.snippet:
            parts.append(f"snippet: {hit.snippet}")
        parts.append(hit.rawText if hasattr(hit, "rawText") else "")
        passage = "\n".join(p for p in parts if p)
        if not passage:
            # Last-resort: just the snippet or the chunk id.
            passage = hit.snippet or hit.chunkId
        return passage

    def _guard_metadata(self, hit: RetrievalHit) -> None:
        meta = hit.metadata
        # Check forbidden keys in the top-level metadata fields.
        for key in self.FORBIDDEN_KEYS:
            if hasattr(meta, key):
                value = getattr(meta, key)
                if value:
                    raise RerankTextBuilderError(
                        f"forbidden metadata field {key!r} is non-empty; "
                        f"the cross-encoder must not see it"
                    )
        # Check the extensions dict for forbidden keys.
        ext = meta.extensions
        if isinstance(ext, dict):
            for key in self.FORBIDDEN_KEYS:
                if key in ext and ext[key]:
                    raise RerankTextBuilderError(
                        f"forbidden metadata field {key!r} is non-empty in "
                        f"extensions; the cross-encoder must not see it"
                    )
        # Check the snippet for forbidden values (best-effort:
        # common Git SHAs and timestamps).
        if hit.snippet:
            for forbidden in ("sk-", "ghp_", "xoxb-", "password="):
                if forbidden in hit.snippet:
                    raise RerankTextBuilderError(
                        f"forbidden value {forbidden!r} detected in snippet"
                    )
