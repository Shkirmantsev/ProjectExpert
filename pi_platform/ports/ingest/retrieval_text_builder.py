"""RetrievalTextBuilder port (Change Package B4).

Separates the three semantic texts mandated by the context-enrichment
delta (plan §10 / §10.1):

- ``raw_text`` — the exact source text (``Chunk.rawText``);
- ``retrieval_text`` — the deterministic embedding input built by a
  :class:`RetrievalTextBuilderPort` as
  ``context_prefix + "\\n\\n" + raw_text``;
- ``metadata`` — filters, provenance, version and security fields,
  which are never embedded into ``retrieval_text``.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Optional

from pi_platform.core.canonical.value_types import Chunk, Document, Metadata, Section


__all__ = [
    "RetrievalText",
    "RetrievalTextBuilderPort",
    "RetrievalTextBuilderError",
    "DEFAULT_STRATEGY_VERSION",
]


DEFAULT_STRATEGY_VERSION = "retrieval-text-v1"
"""Canonical strategy version for the deterministic retrieval text."""


@dataclass(frozen=True)
class RetrievalText:
    """The built embedding input plus its deterministic provenance."""

    text: str
    strategy_version: str = DEFAULT_STRATEGY_VERSION
    deterministic_parts: tuple[str, ...] = ()
    inferred_parts: tuple[str, ...] = ()
    content_hash: str = ""


class RetrievalTextBuilderError(RuntimeError):
    """Raised when the builder cannot produce a safe retrieval text."""


class RetrievalTextBuilderPort(abc.ABC):
    """Adapter contract: build the deterministic embedding input."""

    @abc.abstractmethod
    def build(
        self,
        *,
        chunk: Chunk,
        document: Optional[Document],
        section: Optional[Section],
        metadata: Optional[Metadata],
        local_enrichment: Optional[Any] = None,
    ) -> RetrievalText: ...