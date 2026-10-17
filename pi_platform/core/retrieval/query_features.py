"""Query features value object for hybrid retrieval routing.

Introduces the additive :class:`QueryFeatures` contract from the
``improve-ingestion-retrieval-local-models`` change package
(``specs/2026-10-04-hybrid-retrieval``): identifiers, quoted phrases,
free-text presence and optional explicit document / symbol targets.
The object is produced by :meth:`QueryFeatures.from_text` and
consumed by :class:`pi_platform.core.retrieval.hybrid_retrieval.HybridRetrievalCore`
to decide between the exact-only fast path and the full hybrid path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pi_platform.core.retrieval.hybrid_retrieval import IDENTIFIER_PATTERN


__all__ = [
    "QueryFeatures",
    "QUOTED_PHRASE_PATTERN",
]


# Quoted-phrase grammar: a double-quoted span of 1–200 characters
# that does not span lines. Quoted phrases are candidate PROTECTED
# evidence per the retrieval-candidate-selection delta spec.
QUOTED_PHRASE_PATTERN = re.compile(r"\"([^\"\n]{1,200})\"")


@dataclass(frozen=True)
class QueryFeatures:
    """Analysed query features used to route hybrid retrieval.

    ``identifiers`` are engineering identifiers matched by the shared
    ``IDENTIFIER_PATTERN`` in first-seen order without duplicates.
    ``quoted_phrases`` are the double-quoted spans. ``has_free_text``
    is true when meaningful prose remains after identifiers and
    quoted phrases are removed. ``target_document`` / ``target_symbol``
    and ``filters`` are additive optional routing hints; they default
    to empty / ``None`` and preserve current behaviour when unset.
    """

    identifiers: tuple[str, ...] = ()
    quoted_phrases: tuple[str, ...] = ()
    has_free_text: bool = False
    target_document: str = ""
    target_symbol: str = ""
    filters: object = field(default=None)

    @classmethod
    def from_text(cls, text: str) -> "QueryFeatures":
        """Build :class:`QueryFeatures` from raw query ``text``.

        Safe for empty strings and ``None``: an empty feature set is
        returned in that case.
        """

        if not text:
            return cls()
        identifiers = tuple(dict.fromkeys(
            match.group(1) for match in IDENTIFIER_PATTERN.finditer(text)
        ))
        quoted_phrases = tuple(
            match.group(1) for match in QUOTED_PHRASE_PATTERN.finditer(text)
        )
        remainder = QUOTED_PHRASE_PATTERN.sub(" ", text)
        remainder = IDENTIFIER_PATTERN.sub(" ", remainder)
        has_free_text = bool(remainder.strip())
        return cls(
            identifiers=identifiers,
            quoted_phrases=quoted_phrases,
            has_free_text=has_free_text,
        )
