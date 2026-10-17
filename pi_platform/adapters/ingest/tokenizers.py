"""Stdlib-only tokenizer adapters (Change Package B1).

Implements :class:`pi_platform.ports.ingest.tokenizer.TokenizerPort`
with two deterministic estimators that ship in the default container
and a stub that marks where the optional ``semantic-embeddings``
profile binds a real model tokenizer in Change Package C. No model
weights are downloaded and no third-party package is imported.
"""

from __future__ import annotations

import functools
import hashlib
import re

from pi_platform.ports.ingest.tokenizer import TokenizerError, TokenizerPort


__all__ = [
    "WhitespaceTokenizer",
    "HashingTokenizer",
    "EmbeddingGemma2Tokenizer",
]


_WHITESPACE_TOKEN = re.compile(r"\S+")


class WhitespaceTokenizer(TokenizerPort):
    """Test fallback: one token per whitespace-delimited word."""

    def count(self, text: str) -> int:
        """Return the number of whitespace-delimited tokens in ``text``."""

        return len(text.split())

    def truncate(self, text: str, max_tokens: int) -> str:
        """Return the longest word-aligned prefix within ``max_tokens``."""

        if max_tokens < 0:
            raise TokenizerError(f"max_tokens must be >= 0, got {max_tokens}")
        ends = [m.end() for m in _WHITESPACE_TOKEN.finditer(text)]
        if len(ends) <= max_tokens:
            return text
        if max_tokens == 0:
            return ""
        return text[: ends[max_tokens - 1]]

    def identity(self) -> str:
        return "whitespace/v1"


@functools.lru_cache(maxsize=None)
def _char_weight(character: str) -> int:
    """Deterministic per-character token weight (byte-hash driven).

    Every character contributes one token plus one extra token when the
    first byte of ``sha256(char.encode("utf-8"))`` is odd. The weight is
    a pure function of the UTF-8 bytes, so identical byte sequences
    always yield identical counts (byte-stable) with no model files.
    """

    digest = hashlib.sha256(character.encode("utf-8")).digest()
    return 1 + (digest[0] & 1)


class HashingTokenizer(TokenizerPort):
    """Default deterministic estimator used by the minimal profile."""

    def count(self, text: str) -> int:
        """Return the hashed byte-stable token estimate for ``text``."""

        return sum(_char_weight(ch) for ch in text)

    def truncate(self, text: str, max_tokens: int) -> str:
        """Return a prefix of ``text`` within ``max_tokens``, word-aligned when possible."""

        if max_tokens < 0:
            raise TokenizerError(f"max_tokens must be >= 0, got {max_tokens}")
        budget = 0
        cut = 0
        for index, character in enumerate(text):
            weight = _char_weight(character)
            if budget + weight > max_tokens:
                break
            budget += weight
            cut = index + 1
        else:
            return text
        segment = text[:cut]
        boundary = max(segment.rfind(" "), segment.rfind("\n"))
        if boundary > 0:
            return segment[:boundary]
        return segment

    def identity(self) -> str:
        return "hashing/v1"


class EmbeddingGemma2Tokenizer(TokenizerPort):
    """Stub bound by Change Package C behind the ``semantic-embeddings`` extra."""

    _ERROR = (
        "EmbeddingGemma2Tokenizer is not bound in minimal profile; "
        "install semantic-embeddings extras in C"
    )

    def count(self, text: str) -> int:
        raise TokenizerError(self._ERROR)

    def truncate(self, text: str, max_tokens: int) -> str:
        raise TokenizerError(self._ERROR)

    def identity(self) -> str:
        return "embeddinggemma2/v1-stub"
