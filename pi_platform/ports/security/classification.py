"""Phase 8 §56 Security Classification port.

The classifier exposes a typed four-level vocabulary
(``PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED``) with a
stable ordered integral rank so source-permission and
egress policies can compare levels directly.

The classifier MUST default unlabelled chunks to
``PUBLIC`` so a missing classification field never
silently leaks ``RESTRICTED`` content.
"""

from __future__ import annotations

import abc
import enum
import json
from dataclasses import dataclass
from typing import Iterable, Optional, Tuple


__all__ = [
    "ClassificationLevel",
    "DEFAULT_LEVEL",
    "RANK",
    "DocumentClassification",
    "SourceClassification",
    "SecurityClassificationPort",
    "UnknownClassificationLevelError",
    "coerce_level",
]


class ClassificationLevel(str, enum.Enum):
    """§56 four-level classification vocabulary.

    The enumeration values are the canonical string
    identifiers used by the rest of the Phase 8 subsystem.
    The :data:`RANK` mapping provides a stable ordered
    integral rank used for direct comparison.
    """

    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


DEFAULT_LEVEL = ClassificationLevel.PUBLIC

# Stable ordered integral rank used for comparison.
# Phase 8 source-permission and egress policies compare
# ranks; the rank MUST NOT change after first adoption.
RANK: dict[ClassificationLevel, int] = {
    ClassificationLevel.PUBLIC: 0,
    ClassificationLevel.INTERNAL: 1,
    ClassificationLevel.CONFIDENTIAL: 2,
    ClassificationLevel.RESTRICTED: 3,
}


@dataclass(frozen=True)
class DocumentClassification:
    """The classification of a single document or chunk.

    Attributes:
        document_id: stable identifier of the document or
            chunk whose classification is being recorded.
        level: the resolved ``ClassificationLevel``.
        source_id: optional originating source identifier;
            used for source-permission decisions.
    """

    document_id: str
    level: ClassificationLevel
    source_id: str = ""


@dataclass(frozen=True)
class SourceClassification:
    """The classification ceiling of a source.

    Attributes:
        source_id: stable source identifier (parser /
            adapter / inbox).
        ceiling: the maximum classification level any
            document from this source can carry.
    """

    source_id: str
    ceiling: ClassificationLevel


class UnknownClassificationLevelError(RuntimeError):
    """Raised when a classification value is not part of
    the documented vocabulary.
    """

    def __init__(self, *, level: str) -> None:
        self.level = level
        super().__init__(
            f"unknown-classification-level: level={level!r}"
        )


def coerce_level(raw: Optional[str]) -> ClassificationLevel:
    """Normalise a free-form string to the documented
    vocabulary.

    Empty and missing values default to ``PUBLIC`` per the
    spec; values that look like a level but are not in the
    vocabulary raise :class:`UnknownClassificationLevelError`.
    """

    if raw is None or raw == "":
        return DEFAULT_LEVEL
    try:
        return ClassificationLevel(raw)
    except ValueError as exc:
        raise UnknownClassificationLevelError(level=raw) from exc


class SecurityClassificationPort(abc.ABC):
    """§56 Security Classification port."""

    def classify_document(
        self, document_id: str, raw_level: Optional[str],
        source_id: str = "",
    ) -> DocumentClassification:
        """Return the resolved classification for the
        ``document_id``, defaulting to :data:`DEFAULT_LEVEL`
        when ``raw_level`` is empty.
        """
        level = coerce_level(raw_level)
        ceiling = self.ceiling_for(source_id)
        if ceiling != DEFAULT_LEVEL and RANK[level] > RANK[ceiling]:
            level = ceiling
        return DocumentClassification(
            document_id=document_id,
            level=level,
            source_id=source_id,
        )

    @abc.abstractmethod
    def classify_source(self, source_id: str) -> ClassificationLevel:
        """Return the configured ceiling classification for
        ``source_id``; default :data:`DEFAULT_LEVEL` when no
        mapping exists.
        """
        raise NotImplementedError

    @abc.abstractmethod
    def ceilings(self) -> Tuple[SourceClassification, ...]:
        """Return the configured source ceilings."""
        raise NotImplementedError

    @abc.abstractmethod
    def ceiling_for(self, source_id: str) -> ClassificationLevel:
        """Return the configured ceiling for ``source_id``;
        default ``PUBLIC`` when no mapping exists.
        """
        raise NotImplementedError

    def serialise(self) -> str:
        """Byte-stable JSON serialisation."""
        payload = {
            "default": DEFAULT_LEVEL.value,
            "sources": [
                {"sourceId": c.source_id, "ceiling": c.ceiling.value}
                for c in sorted(
                    self.ceilings(),
                    key=lambda c: c.source_id,
                )
            ],
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))
