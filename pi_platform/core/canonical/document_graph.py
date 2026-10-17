"""Rich canonical document graph types (v0.8 refinement).

Covers plan §3.2, §19, §20, §22. The existing canonical model
(``Document``, ``Section``, ``Chunk``, ``Entity``, ``Relation``,
``Evidence``) is the generic public surface; this module adds an
additive neutral submodel that captures page geometry, reading
order, tables, figures, captions, formulas, page-level OCR
provenance, and binary asset references.

Docling (or any other vendor) types MUST NOT appear here; the
core knows only ProjectExpert-neutral types. The rich submodel
is projected into the existing ``Document`` / ``Section`` /
``Chunk`` types by the ingestion pipeline.

Schema version: this module is part of canonical knowledge
schema v2 (``KNOWLEDGE_SCHEMA_VERSION == "0.8.0"``). The v1
record types remain readable; new fields default to empty.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional, Sequence, Tuple


__all__ = [
    "ElementKind",
    "SourceAnchor",
    "AssetRef",
    "DocumentRevision",
    "Page",
    "DocumentElement",
    "TableGrid",
    "IngestionCheckpoint",
    "IngestionState",
]


class IngestionState(str, enum.Enum):
    """Documented ingestion job states (plan §21.3)."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_PERMANENT = "FAILED_PERMANENT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ElementKind(str, enum.Enum):
    """Discriminator for :class:`DocumentElement`."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    FIGURE = "figure"
    FORMULA = "formula"

    @classmethod
    def is_recognised(cls, value: str) -> bool:
        return value in {member.value for member in cls}


@dataclass(frozen=True)
class SourceAnchor:
    """An exact pointer to a page element (plan §20)."""

    revision_id: str
    page: int = 0
    element_id: str = ""
    bbox: Tuple[float, ...] = ()
    line: int = 0
    asset_id: str = ""


@dataclass(frozen=True)
class AssetRef:
    """A binary asset reference (image, attached file)."""

    asset_id: str
    byte_hash: str
    mime_type: str
    cas_path: str
    page: int = 0
    bbox: Tuple[float, ...] = ()


@dataclass(frozen=True)
class DocumentRevision:
    """A specific byte-content version of a source (plan §19)."""

    revision_id: str
    source_id: str
    byte_hash: str
    strategy_version: str
    ingested_at: str
    page_count: int = 0
    language: str = "und"
    author: str = ""


@dataclass(frozen=True)
class Page:
    """A single page within a :class:`DocumentRevision`."""

    page_no: int
    bbox: Tuple[float, ...] = ()
    native_text_present: bool = True
    ocr_used: bool = False
    rotation: int = 0
    language_hint: str = "und"


@dataclass(frozen=True)
class DocumentElement:
    """A single page element (heading, paragraph, list, table,
    figure, or formula)."""

    element_id: str
    kind: ElementKind
    page: int
    bbox: Tuple[float, ...] = ()
    content_hash: str = ""
    semantic_key: str = ""
    text: str = ""

    def __post_init__(self) -> None:
        if not ElementKind.is_recognised(
            self.kind.value if isinstance(self.kind, ElementKind) else str(self.kind),
        ):
            raise ValueError(
                f"DocumentElement.kind must be one of "
                f"{[m.value for m in ElementKind]}, got {self.kind!r}"
            )


@dataclass(frozen=True)
class TableGrid:
    """A structured table with cells and a Markdown serialisation."""

    headers: Tuple[str, ...] = ()
    rows: Tuple[Tuple[str, ...], ...] = ()
    serialised_markdown: str = ""
    repeat_header: bool = True


@dataclass(frozen=True)
class IngestionCheckpoint:
    """The resumable state of a single ingestion run (plan §21.3)."""

    job_id: str
    source_id: str
    revision_id: str
    strategy_version: str
    state: str
    next_page: int = 1
    completed_ranges: Tuple[Tuple[int, int], ...] = ()
    failed_range: Tuple[int, int] = ()
    error: str = ""
    started_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not IngestionState.is_recognised(self.state):
            raise ValueError(
                f"IngestionCheckpoint.state must be one of "
                f"{[m.value for m in IngestionState]}, got {self.state!r}"
            )


# Convenience: register the IngestionState.is_recognised classmethod.
IngestionState.is_recognised = classmethod(  # type: ignore[attr-defined]
    lambda cls, value: value in {member.value for member in cls}
)
