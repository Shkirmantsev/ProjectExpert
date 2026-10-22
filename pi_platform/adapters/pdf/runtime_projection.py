"""Model-specific PDF embedding segments over unchanged canonical chunks."""
from __future__ import annotations

import json

from pi_platform.adapters.pdf.docling_chunker import DoclingHybridChunker
from pi_platform.core.canonical.value_types import (
    Chunk, Document, Section, from_canonical_json,
)

PDF_RUNTIME_PROJECTION_VERSION = "docling-pdf-segments/v1"


class PdfRuntimeProjection:
    """Reuse one model-aligned vendor chunker for an indexing refresh.

    Returned strings are disposable embedding inputs. The input canonical body,
    its identifier and its source anchors are never rewritten.
    """

    def __init__(self, model_id: str, max_tokens: int = 512):
        self._chunker = DoclingHybridChunker(
            embedding_model_id=model_id, max_tokens=max_tokens)

    def __call__(self, body: dict) -> tuple[str, ...]:
        original = from_canonical_json(Chunk, json.dumps(body))
        if not original.rawText.strip():
            return ()
        section = Section(id=original.parentId or f"pdf-runtime:{original.id}",
                          heading=original.metadata.section or "", level=1,
                          chunks=(original,))
        document = Document(id=original.metadata.documentId or original.id,
                            title=original.metadata.section or "PDF",
                            sections=(section,), metadata=original.metadata)
        return tuple(chunk.rawText for chunk in self._chunker.chunk(document, (section,)))


def projection_segments(body: dict, model_id: str, max_tokens: int = 512) -> tuple[str, ...]:
    """Convenience for one chunk; refresh callers should reuse PdfRuntimeProjection."""
    return PdfRuntimeProjection(model_id, max_tokens=max_tokens)(body)
