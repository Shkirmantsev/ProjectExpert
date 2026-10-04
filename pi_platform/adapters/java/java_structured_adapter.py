"""Stub for the Phase 2 Java structured SourceAdapter and Chunker.

The real tree-sitter-java backed implementation lands in the next
step. Construction succeeds so the default ``LocalPipelineDriver``
registries can be built; ``parse`` and ``chunk`` raise
``NotImplementedError`` until the real implementation replaces this
module at the documented import path.
"""

from __future__ import annotations

from typing import Optional, Sequence

from pi_platform.core.canonical.value_types import (
    Chunk,
    Document,
    Section,
    Source,
)

from pi_platform.ports.ingest.chunker import ChunkerContext, ChunkerPort
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterContext,
    SourceAdapterPort,
    SourceContentFamily,
    SourceParseResult,
)


__all__ = [
    "JavaStructuredAdapter",
    "JavaStructuredChunker",
]


class JavaStructuredAdapter(SourceAdapterPort):
    """Stub SourceAdapter for Java sources."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.JAVA_SOURCE

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        raise NotImplementedError(
            "stub: pi_platform.adapters.java.java_structured_adapter"
        )


class JavaStructuredChunker(ChunkerPort):
    """Stub Chunker for Java sources."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.JAVA_SOURCE

    def chunk(self, document: Document, sections: Sequence[Section],
              context: Optional[ChunkerContext] = None) -> Sequence[Chunk]:
        raise NotImplementedError(
            "stub: pi_platform.adapters.java.java_structured_adapter"
        )
