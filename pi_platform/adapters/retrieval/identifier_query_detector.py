"""Identifier query detector adapter.

Implements the §26 / §27 identifier-recognition grammar via the
:class:`pi_platform.core.retrieval.hybrid_retrieval.IDENTIFIER_PATTERN`
regex. The detector is exported as a callable so the
:class:`HybridRetrievalCore` can compose it before any vector
search runs.
"""

from __future__ import annotations

import re

from pi_platform.core.retrieval.hybrid_retrieval import IDENTIFIER_PATTERN


__all__ = [
    "IdentifierQueryDetector",
    "ADAPTER_NAME",
    "is_identifier_query",
]


ADAPTER_NAME = "identifier-grammar"


def is_identifier_query(text: str) -> bool:
    """Return ``True`` if ``text`` contains an engineering identifier."""

    if not text:
        return False
    return bool(IDENTIFIER_PATTERN.search(text))


class IdentifierQueryDetector:
    """Callable wrapper around :func:`is_identifier_query`."""

    name = ADAPTER_NAME

    def __call__(self, text: str) -> bool:
        return is_identifier_query(text)

    def match(self, text: str) -> re.Match[str] | None:
        return IDENTIFIER_PATTERN.search(text)