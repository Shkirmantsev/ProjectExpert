"""Chunker port for the v0.8 Phase 2 ingestion pipeline.

Covers architecture sections §19 (semantic chunking), §20
(structural chunking) and §21 (chunk model and hierarchy). Every
content family registers a Chunker strategy that splits a
:class:`Document` into a sequence of :class:`Chunk` records with
parent links preserved.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import Chunk, Document, Section

from .source_adapter import SourceContentFamily


__all__ = [
    "ChunkerPort",
    "ChunkerRegistry",
    "ChunkerError",
]


class ChunkerError(RuntimeError):
    """Raised when a chunker cannot split the document into chunks."""


@dataclass
class ChunkerContext:
    """Per-chunk context passed alongside the document being chunked."""

    project_root: object = None  # Path; kept loose to avoid port -> core cycles
    max_chunk_bytes: int = 4096
    extra: Mapping[str, object] = field(default_factory=dict)


class ChunkerPort(abc.ABC):
    """Adapter contract: split a :class:`Document` into :class:`Chunk` records."""

    @property
    @abc.abstractmethod
    def family(self) -> SourceContentFamily: ...

    @abc.abstractmethod
    def chunk(self, document: Document, sections: Sequence[Section],
              context: Optional[ChunkerContext] = None) -> Sequence[Chunk]: ...


class ChunkerRegistry:
    """Map :class:`SourceContentFamily` to the registered chunker."""

    def __init__(self) -> None:
        self._chunkers: dict[SourceContentFamily, ChunkerPort] = {}

    def register(self, chunker: ChunkerPort) -> None:
        self._chunkers[chunker.family] = chunker

    def unregister(self, family: SourceContentFamily) -> None:
        self._chunkers.pop(family, None)

    def resolve(self, family: SourceContentFamily) -> ChunkerPort:
        chunker = self._chunkers.get(family)
        if chunker is None:
            raise ChunkerError(f"no chunker registered for family {family!r}")
        return chunker

    def has(self, family: SourceContentFamily) -> bool:
        return family in self._chunkers
