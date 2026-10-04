"""Chunker adapters for Markdown, HTML and plain text.

Covers architecture sections §19 (semantic chunking), §20
(structural chunking) and §21 (chunk model and hierarchy). The
chunkers split a :class:`Document` into a sequence of
:class:`Chunk` records with parent links preserved.

The Java and OpenSpec chunkers are delegated to
:mod:`pi_platform.adapters.java.java_structured_adapter` and
:mod:`pi_platform.adapters.openspec.openspec_change_adapter`
respectively; they live in those adapter modules so the chunker
logic shares state with the corresponding SourceAdapter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence

from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    Chunk,
    Document,
    Evidence,
    KnowledgeState,
    Metadata,
    Section,
    Source,
)

from pi_platform.ports.ingest.chunker import (
    ChunkerContext,
    ChunkerError,
    ChunkerPort,
)
from pi_platform.ports.ingest.source_adapter import SourceContentFamily


__all__ = [
    "MarkdownChunker",
    "HtmlChunker",
    "PlainTextChunker",
]


_PARAGRAPH_RE = re.compile(r"\n\s*\n")


def _parent_id_for(section: Section, document: Document) -> Optional[str]:
    if section.parentId is not None:
        return section.parentId
    if section.level <= 0:
        return document.id
    return document.id


def _make_chunk(*, document: Document, section: Section, raw_text: str,
                chunk_index: int, parser_version: str,
                source: Optional[Source] = None) -> Chunk:
    parent_id = _parent_id_for(section, document)
    metadata = Metadata(
        documentId=document.id,
        version="0.0.0",
        language=document.metadata.language or "und",
        section=section.heading or None,
        sourcePath=document.metadata.sourcePath or None,
        contentHash=content_address_bytes_for(raw_text),
    )
    chunk_id = content_address(
        Chunk(
            id="placeholder",
            rawText=raw_text,
            contextualText=raw_text,
            metadata=metadata,
            sourceReference=document.id,
            contentHash=metadata.contentHash or "",
            parentId=parent_id,
            childIds=(),
            entityIds=(),
            provenance=Evidence(
                knowledgeState=KnowledgeState.VERIFIED,
                parserVersion=parser_version,
            ),
        )
    )
    return Chunk(
        id=chunk_id,
        rawText=raw_text,
        contextualText=raw_text,
        metadata=metadata,
        sourceReference=document.id,
        contentHash=metadata.contentHash or "",
        parentId=parent_id,
        childIds=(),
        entityIds=(),
        provenance=Evidence(
            knowledgeState=KnowledgeState.VERIFIED,
            parserVersion=parser_version,
        ),
    )


def content_address_bytes_for(text: str) -> str:
    """SHA-256 hex digest of the chunk's raw text."""

    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class MarkdownChunker(ChunkerPort):
    """Split Markdown documents on heading boundaries."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.MARKDOWN

    def chunk(self, document: Document, sections: Sequence[Section],
              context: Optional[ChunkerContext] = None) -> Sequence[Chunk]:
        if not sections:
            return ()
        max_bytes = (context.max_chunk_bytes if context else 4096)
        chunks: List[Chunk] = []
        for section in sections:
            paragraphs = _PARAGRAPH_RE.split(_section_body(document, section))
            buffer: List[str] = []
            for paragraph in paragraphs:
                if not paragraph.strip():
                    continue
                if sum(len(p) for p in buffer) + len(paragraph) > max_bytes and buffer:
                    chunks.append(_emit_paragraph(
                        document, section, "\n\n".join(buffer), len(chunks),
                        parser_version="markdown-chunker-0.1.0",
                    ))
                    buffer = [paragraph]
                else:
                    buffer.append(paragraph)
            if buffer:
                chunks.append(_emit_paragraph(
                    document, section, "\n\n".join(buffer), len(chunks),
                    parser_version="markdown-chunker-0.1.0",
                ))
        _link_parent_child(chunks)
        return tuple(chunks)


class HtmlChunker(ChunkerPort):
    """Split HTML documents on ``<h1>``-``<h6>`` / ``<section>`` / ``<article>`` boundaries."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.HTML

    def chunk(self, document: Document, sections: Sequence[Section],
              context: Optional[ChunkerContext] = None) -> Sequence[Chunk]:
        chunks: List[Chunk] = []
        for section in sections:
            chunks.append(_emit_paragraph(
                document, section, section.heading or "(html section body)",
                len(chunks), parser_version="html-chunker-0.1.0",
            ))
        _link_parent_child(chunks)
        return tuple(chunks)


class PlainTextChunker(ChunkerPort):
    """Paragraph-boundary fallback chunker."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.PLAIN_TEXT

    def chunk(self, document: Document, sections: Sequence[Section],
              context: Optional[ChunkerContext] = None) -> Sequence[Chunk]:
        chunks: List[Chunk] = []
        for section in sections:
            body = _section_body(document, section)
            for idx, paragraph in enumerate(_PARAGRAPH_RE.split(body)):
                if not paragraph.strip():
                    continue
                chunks.append(_emit_paragraph(
                    document, section, paragraph, len(chunks),
                    parser_version="plain-text-chunker-0.1.0",
                ))
        _link_parent_child(chunks)
        return tuple(chunks)


def _section_body(document: Document, section: Section) -> str:
    # Phase 1 Document does not store section bodies; we use the
    # heading as a placeholder. Phase 3 will store the body and
    # this helper will switch to the canonical body.
    return section.heading or ""


def _emit_paragraph(document: Document, section: Section, text: str,
                    index: int, *, parser_version: str) -> Chunk:
    return _make_chunk(
        document=document,
        section=section,
        raw_text=text,
        chunk_index=index,
        parser_version=parser_version,
    )


def _link_parent_child(chunks: List[Chunk]) -> None:
    """Populate childIds so each non-leaf chunk has a non-empty list."""

    if not chunks:
        return
    for parent_idx, parent in enumerate(chunks):
        children = [
            child.id for child in chunks
            if child.parentId == parent.id
        ]
        if children:
            object.__setattr__(parent, "childIds", tuple(children))
