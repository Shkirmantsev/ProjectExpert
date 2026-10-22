"""Real model-aligned PDF chunking over neutral document projections."""
from __future__ import annotations

from dataclasses import replace
from typing import Sequence

from pi_platform.core.canonical.value_types import Chunk, Document, Section
from pi_platform.ports.ingest.chunker import ChunkerContext, ChunkerError, ChunkerPort
from pi_platform.ports.ingest.source_adapter import SourceContentFamily
from pi_platform.adapters.pdf.real_docling import build_docling_chunker

__all__ = ["DoclingHybridChunker", "PdfStructuralChunker", "DEFAULT_DOCLING_CHUNKER_VERSION"]
DEFAULT_DOCLING_CHUNKER_VERSION = "docling-hybrid-chunker/v2"


class DoclingHybridChunker(ChunkerPort):
    """Use the vendor chunker; structural fixture mode requires explicit opt-in."""

    def __init__(self, *, embedding_model_id="google/embeddinggemma-2",
                 max_tokens=512, allow_synthetic=False, real_chunker=None):
        self._embedding_model_id = embedding_model_id
        self._max_tokens = max_tokens
        self._allow_synthetic = allow_synthetic
        self._real_chunker = real_chunker or build_docling_chunker(
            embedding_model_id=embedding_model_id, max_tokens=max_tokens)

    @property
    def tokenizer_alignment(self):
        return self._real_chunker.tokenizer_alignment

    @property
    def family(self):
        return SourceContentFamily.PDF

    def chunk(self, document: Document, sections: Sequence[Section],
              context: ChunkerContext | None = None) -> Sequence[Chunk]:
        if not sections:
            return ()
        if self._allow_synthetic:
            from pi_platform.adapters.ingest.chunkers import PlainTextChunker
            return PlainTextChunker().chunk(document, sections, context)
        from pi_platform.core.ingest.records import make_chunk
        try:
            from docling_core.types.doc import DoclingDocument, DocItemLabel, TableData, TableCell
            result = []
            for section in sections:
                # Each neutral structural unit keeps its exact canonical anchors.
                for original in section.chunks:
                    if not original.rawText.strip():
                        continue
                    vendor_doc = DoclingDocument(name=document.title or document.id)
                    table = original.metadata.extensions.get("table")
                    if table:
                        if table["headers"]:
                            vendor_doc.add_heading(text=" | ".join(table["headers"]), level=1)
                        rows = [tuple(table["headers"])] if table["headers"] else []
                        rows.extend(tuple(row) for row in table["rows"])
                        cells = [TableCell(text=str(text), column_header=bool(table["headers"] and r == 0),
                                           start_row_offset_idx=r, end_row_offset_idx=r + 1,
                                           start_col_offset_idx=c, end_col_offset_idx=c + 1)
                                 for r, row in enumerate(rows) for c, text in enumerate(row)]
                        vendor_doc.add_table(data=TableData(num_rows=len(rows),
                            num_cols=max((len(row) for row in rows), default=0), table_cells=cells))
                    else:
                        vendor_doc.add_text(label=DocItemLabel.TEXT, text=original.rawText)
                    vendor_chunks = self._real_chunker.chunk(vendor_doc)
                    budget = self._max_tokens
                    while True:
                        texts = [(self._real_chunker.contextualize(chunk)
                                  if table else chunk.text) for chunk in vendor_chunks]
                        overflow = max((self._real_chunker.count_tokens(text) - self._max_tokens
                                        for text in texts), default=0)
                        if overflow <= 0:
                            break
                        # Older vendor serializers undercount repeated table context.
                        # Reuse the actual chunker with enough room reserved for it.
                        budget -= overflow + 1
                        if budget < 1:
                            raise ChunkerError("PDF structural unit and repeated header cannot fit token budget")
                        vendor_chunks = self._real_chunker.chunk_with_budget(vendor_doc, budget)
                    for i, text in enumerate(texts):
                        if not text.strip():
                            continue
                        chunk = make_chunk(document, section, text,
                            parser_version=DEFAULT_DOCLING_CHUNKER_VERSION,
                            extensions=dict(original.metadata.extensions), index=i)
                        result.append(replace(chunk, anchors=original.anchors))
            return tuple(result)
        except Exception as exc:
            raise ChunkerError(f"PDF chunking failed for {document.id!r}: {exc}") from exc


class PdfStructuralChunker(ChunkerPort):
    """Keep neutral source units and anchors canonical; split only at embedding time."""

    @property
    def family(self):
        return SourceContentFamily.PDF

    def chunk(self, document, sections, context=None):
        return tuple(chunk for section in sections for chunk in section.chunks
                     if chunk.rawText.strip())
