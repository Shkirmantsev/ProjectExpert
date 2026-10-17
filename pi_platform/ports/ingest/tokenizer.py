"""Tokenizer port for the v0.8 ingestion pipeline (Change Package B).

A tokenizer turns text into an estimated token count so chunking can
respect a model-oriented budget instead of a raw byte budget. The
port is stdlib-only; real model-backed tokenizers are bound later by
Change Package C behind optional dependency groups.
"""

from __future__ import annotations

import abc


__all__ = [
    "TokenizerPort",
    "TokenizerError",
    "DEFAULT_TOKENIZER_ID",
]


DEFAULT_TOKENIZER_ID = "hashing/default"
"""Default tokenizer identity used when a caller does not bind one."""


class TokenizerError(RuntimeError):
    """Raised when a tokenizer cannot satisfy a request."""


class TokenizerPort(abc.ABC):
    """Adapter contract: estimate and enforce token budgets on text."""

    @abc.abstractmethod
    def count(self, text: str) -> int:
        """Return the estimated number of tokens in ``text``."""

    @abc.abstractmethod
    def truncate(self, text: str, max_tokens: int) -> str:
        """Return a prefix of ``text`` whose token count is within ``max_tokens``."""

    @abc.abstractmethod
    def identity(self) -> str:
        """Return a stable identity string, e.g. ``hashing/v1``."""
