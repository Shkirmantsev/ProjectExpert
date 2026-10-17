"""Docling HybridChunker adapter (E7).

Implements :class:`pi_platform.ports.ingest.chunker.ChunkerPort`
for the PDF family using Docling's
:class:`docling.chunking.hybrid_chunker.HybridChunker`. The
chunker is the production STUB: it implements the
:class:`ChunkerPort` contract and delegates to the existing
structural chunkers (specifically
:class:`pi_platform.adapters.ingest.chunkers.PlainTextChunker`)
so the pipeline driver needs no special-case code path for
PDF.

The real ``docling`` binding is a follow-up: the
``DoclingRealHybridChunker`` will instantiate the
``HybridChunker`` with a ``HybridChunkerConfig`` and combine
Docling's hierarchical document boundaries with
tokenizer-aware splits.
"""

from __future__ import annotations

from typing import Sequence

from pi_platform.core.canonical.value_types import (
    Chunk,
    Document,
    Section,
)
from pi_platform.ports.ingest.chunker import (
    ChunkerContext,
    ChunkerError,
    ChunkerPort,
)
from pi_platform.ports.ingest.source_adapter import SourceContentFamily


__all__ = ["DoclingHybridChunker", "DEFAULT_DOCLING_CHUNKER_VERSION"]


DEFAULT_DOCLING_CHUNKER_VERSION = "docling-hybrid-chunker/v1"


class DoclingHybridChunker(ChunkerPort):
    """Docling HybridChunker adapter (STUB) behind ChunkerPort.

    The stub delegates to :class:`PlainTextChunker` (or any
    structural chunker wired in the pipeline) so the PDF family
    reuses the same chunker pipeline. When the real
    ``docling.HybridChunker`` is wired, this class swaps its
    internal chunker for a real HybridChunker without changing
    the public surface.
    """

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.PDF

    def chunk(
        self,
        document: Document,
        sections: Sequence[Section],
        context: ChunkerContext | None = None,
    ) -> Sequence[Chunk]:
        if not sections:
            return ()
        # Lazy import: the structural chunker lives in the
        # ingest adapter package.
        from pi_platform.adapters.ingest.chunkers import (
            PlainTextChunker,
        )
        # The real Docling HybridChunker would compose:
        #   DoclingDoc → hierarchical boundaries
        #   + tokenizer-aware split
        #   + optional merge of compatible peers
        # The stub delegates to the existing structural chunker,
        # which already respects paragraph boundaries and the
        # byte limit. Token-aware normalization is composed in the
        # pipeline driver via TokenBudgetNormalizer (B3).
        structural = PlainTextChunker()
        return structural.chunk(document, sections, context)
