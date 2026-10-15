"""Token-budget normalizer composing after structural chunkers (B3).

Change Package B3 keeps every structural chunker and wraps it with a
:class:`TokenBudgetNormalizer` that enforces the model-oriented token
budget (plan §8.1 / §9):

1. oversized candidates are split at token boundaries, preserving
   paragraph, sentence and word structure when possible;
2. compatible peer chunks below ``min_tokens`` are merged when
   ``merge_peers`` is enabled and the result fits both budgets;
3. ``max_chunk_bytes`` is never violated — it stays the hard UTF-8
   safety limit inherited from :class:`ChunkerContext`.

The normalizer is stdlib-only and deterministic: the same input, the
same strategy and the same tokenizer always produce the same chunks.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Optional, Sequence

from pi_platform.core.canonical.value_types import Chunk
from pi_platform.ports.ingest.chunker import ChunkerContext, ChunkerError, ChunkerPort
from pi_platform.ports.ingest.tokenizer import TokenizerPort


__all__ = [
    "TokenBudgetNormalizer",
    "TokenBudgetWrappedChunker",
]


_SENTENCE_END = re.compile(r"[.!?][\"')\]]?\s*")


class TokenBudgetNormalizer:
    """Split and merge chunk texts so each piece respects the token budget."""

    def __init__(
        self,
        tokenizer: TokenizerPort,
        *,
        max_chunk_bytes: int = 16384,
        target_tokens: int = 768,
        max_tokens: int = 900,
        min_tokens: int = 160,
        merge_peers: bool = True,
    ) -> None:
        if max_chunk_bytes <= 0:
            raise ValueError(f"max_chunk_bytes must be > 0, got {max_chunk_bytes}")
        if max_tokens <= 0:
            raise ValueError(f"max_tokens must be > 0, got {max_tokens}")
        if target_tokens <= 0:
            raise ValueError(f"target_tokens must be > 0, got {target_tokens}")
        if min_tokens < 0:
            raise ValueError(f"min_tokens must be >= 0, got {min_tokens}")
        self._tokenizer = tokenizer
        self._max_chunk_bytes = max_chunk_bytes
        self._target_tokens = min(target_tokens, max_tokens)
        self._max_tokens = max_tokens
        self._min_tokens = min_tokens
        self._merge_peers = merge_peers

    @property
    def tokenizer(self) -> TokenizerPort:
        return self._tokenizer

    @property
    def max_chunk_bytes(self) -> int:
        return self._max_chunk_bytes

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def target_tokens(self) -> int:
        return self._target_tokens

    @property
    def min_tokens(self) -> int:
        return self._min_tokens

    @property
    def merge_peers_enabled(self) -> bool:
        return self._merge_peers

    def fits(self, text: str) -> bool:
        """Return whether ``text`` satisfies both hard budgets."""

        return (
            len(text.encode("utf-8")) <= self._max_chunk_bytes
            and self._tokenizer.count(text) <= self._max_tokens
        )

    def normalize(self, text: str) -> tuple[str, ...]:
        """Split ``text`` into budget-respecting pieces.

        The pieces reconstruct ``text`` exactly when concatenated:
        splits only cut at existing positions, so no byte is lost.
        """

        if not text:
            return ()
        if self.fits(text):
            return (text,)
        pieces: list[str] = []
        rest = text
        while True:
            if self.fits(rest):
                pieces.append(rest)
                break
            prefix = self._budgeted_prefix(rest)
            cut = self._choose_cut(rest, prefix)
            pieces.append(rest[:cut])
            rest = rest[cut:]
        return tuple(pieces)

    def can_merge(self, left: str, right: str) -> bool:
        """Return whether two adjacent peer texts may be merged."""

        if not self._merge_peers:
            return False
        if self._tokenizer.count(left) >= self._min_tokens:
            return False
        combined = f"{left}\n\n{right}"
        return self.fits(combined)

    def effective_for(
        self, context: Optional[ChunkerContext]
    ) -> Optional["TokenBudgetNormalizer"]:
        """Derive the active normalizer for ``context``.

        Returns ``None`` when the context carries no token fields, so
        the wrapped chunker stays byte-identical to the legacy path.
        """

        if context is None:
            return None
        has_token_context = (
            context.target_tokens is not None
            or context.max_tokens is not None
            or context.min_tokens is not None
            or bool(context.tokenizer_id)
        )
        if not has_token_context:
            return None
        byte_limit = (
            min(context.max_chunk_bytes, self._max_chunk_bytes)
            if context.max_chunk_bytes > 0
            else self._max_chunk_bytes
        )
        return TokenBudgetNormalizer(
            self._tokenizer,
            max_chunk_bytes=byte_limit,
            target_tokens=(
                context.target_tokens
                if context.target_tokens is not None
                else self._target_tokens
            ),
            max_tokens=(
                context.max_tokens if context.max_tokens is not None else self._max_tokens
            ),
            min_tokens=(
                context.min_tokens if context.min_tokens is not None else self._min_tokens
            ),
            merge_peers=self._merge_peers and context.merge_peers,
        )

    def wrap(self, structural_chunker: ChunkerPort) -> ChunkerPort:
        """Return a :class:`ChunkerPort` wrapper enforcing this budget."""

        return TokenBudgetWrappedChunker(structural_chunker, self)

    def _budgeted_prefix(self, text: str) -> str:
        """Return the longest usable prefix within both hard budgets."""

        budget = 0
        cut = 0
        for index, character in enumerate(text):
            size = len(character.encode("utf-8"))
            if budget + size > self._max_chunk_bytes:
                break
            budget += size
            cut = index + 1
        bounded = text[:cut]
        if not bounded:
            return ""
        return self._tokenizer.truncate(bounded, self._max_tokens)

    def _choose_cut(self, text: str, prefix: str) -> int:
        """Pick a semantic cut point inside ``prefix`` (a positive offset)."""

        if not prefix:
            if len(text[0].encode("utf-8")) > self._max_chunk_bytes:
                raise ChunkerError("maxChunkBytes cannot fit a source character")
            raise ChunkerError("chunk budget cannot fit a source word")
        n = len(prefix)
        half = n // 2
        # 1) paragraph boundary
        paragraph = prefix.rfind("\n\n")
        if paragraph >= 0 and paragraph + 2 > half:
            return paragraph + 2
        # 2) sentence end (the last one past the midpoint)
        sentence = 0
        for match in _SENTENCE_END.finditer(prefix):
            sentence = match.end()
        if sentence > half:
            return sentence
        # 3) word / line boundary (mirrors the legacy byte splitter)
        word = max(prefix.rfind("\n"), prefix.rfind(" "))
        if word >= 0 and word + 1 > half:
            return word + 1
        # No boundary in the latter half: fall back to the earliest
        # semantic boundary, then to a hard cut at the prefix end.
        if paragraph < 0 and sentence == 0 and word < 0:
            raise ChunkerError("chunk budget cannot fit a source word")
        if sentence > 0:
            return sentence
        if paragraph >= 0:
            return paragraph + 2
        if word >= 0:
            return word + 1
        return n

    def _apply(self, chunks: Sequence[Chunk]) -> tuple[Chunk, ...]:
        """Split then merge peer chunks, preserving identity metadata."""

        # Split pass: normalise every chunk's rawText into pieces.
        items: list[tuple[Chunk, int, str]] = []
        for chunk in chunks:
            texts = self.normalize(chunk.rawText) or (chunk.rawText,)
            for index, text in enumerate(texts):
                items.append((chunk, index, text))
        # Merge pass: adjacent peers that share a parent and fit.
        merged: list[tuple[Chunk, int, str]] = []
        for chunk, index, text in items:
            if merged:
                prev_chunk, prev_index, prev_text = merged[-1]
                if prev_chunk.parentId == chunk.parentId and self.can_merge(
                    prev_text, text
                ):
                    merged[-1] = (prev_chunk, prev_index, f"{prev_text}\n\n{text}")
                    continue
            merged.append((chunk, index, text))
        # Materialise chunks: the leading piece keeps the original id.
        result: list[Chunk] = []
        for chunk, index, text in merged:
            if index == 0 and text == chunk.rawText:
                result.append(chunk)
            elif index == 0:
                result.append(replace(chunk, rawText=text))
            else:
                result.append(
                    replace(chunk, id=f"{chunk.id}#t{index}", rawText=text)
                )
        return tuple(result)


class TokenBudgetWrappedChunker(ChunkerPort):
    """Structural chunker + token-budget post-processing composition."""

    def __init__(self, inner: ChunkerPort, normalizer: TokenBudgetNormalizer) -> None:
        self._inner = inner
        self._normalizer = normalizer

    @property
    def family(self):
        return self._inner.family

    def chunk(self, document, sections, context=None):
        chunks = self._inner.chunk(document, sections, context)
        effective = self._normalizer.effective_for(context)
        if effective is None:
            return chunks
        return effective._apply(chunks)
