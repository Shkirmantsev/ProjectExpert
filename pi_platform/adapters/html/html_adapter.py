"""HtmlAdapter — stdlib HTML SourceAdapter.

Covers architecture §3 source coverage for HTML documents. The
adapter uses the Python stdlib :mod:`html.parser` to split the
document into a :class:`Document` plus a sequence of
:class:`Section` records by ``<h1>``-``<h6>``, ``<section>`` and
``<article>`` boundaries. No third-party dependency is required.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path
from typing import List, Optional, Tuple

from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    Document,
    KnowledgeState,
    Metadata,
    Section,
    Source,
)

from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterContext,
    SourceAdapterPort,
    SourceContentFamily,
    SourceParseResult,
)


__all__ = ["HtmlAdapter"]


_BOUNDARY_TAGS = {
    "h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6,
    "section": 2, "article": 2,
}


class _SectionParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._sections: List[Tuple[int, str]] = []
        self._stack: List[Tuple[str, int]] = []
        self._current_heading: Optional[Tuple[int, str]] = None
        self._heading_buffer: List[str] = []
        self._title: str = ""

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "title":
            return
        if tag in _BOUNDARY_TAGS:
            level = _BOUNDARY_TAGS[tag]
            self._current_heading = (level, "")
            self._heading_buffer = []
            self._stack.append((tag, level))

    def handle_data(self, data: str) -> None:
        if not self._stack:
            if not self._title:
                stripped = data.strip()
                if stripped:
                    self._title = stripped[:200]
            return
        if self._current_heading is not None:
            self._heading_buffer.append(data)
            self._current_heading = (
                self._current_heading[0],
                "".join(self._heading_buffer).strip(),
            )

    def handle_endtag(self, tag: str) -> None:
        if self._stack and self._stack[-1][0] == tag:
            _, level = self._stack[-1]
            heading = ""
            if self._current_heading is not None and self._current_heading[1]:
                heading = self._current_heading[1]
            elif self._heading_buffer:
                heading = "".join(self._heading_buffer).strip()
            if heading or tag in {"section", "article"}:
                self._sections.append((level, heading or tag))
            self._stack.pop()
            self._current_heading = None
            self._heading_buffer = []


class HtmlAdapter(SourceAdapterPort):
    """Stdlib-only HTML SourceAdapter."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.HTML

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        text = self._read_text(source.uri)
        parser = _SectionParser()
        try:
            parser.feed(text)
            parser.close()
        except Exception:  # noqa: BLE001
            return SourceParseResult(
                document=self._empty_document(source),
                sections=(),
                knowledge_state=KnowledgeState.UNKNOWN,
                parser_version="html-stdlib-0.1.0",
                rationale="HTML parse failed; emitting empty document",
            )
        sections = self._build_sections(parser._sections, parser._title)
        document = self._build_document(source, parser._title or "Untitled", sections)
        return SourceParseResult(
            document=document,
            sections=tuple(sections),
            knowledge_state=KnowledgeState.VERIFIED,
            parser_version="html-stdlib-0.1.0",
        )

    @staticmethod
    def _read_text(uri: str) -> str:
        try:
            return Path(uri).read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            return ""

    @staticmethod
    def _build_sections(levels: List[Tuple[int, str]], title: str) -> List[Section]:
        sections: List[Section] = []
        if title:
            sections.append(
                Section(
                    id=content_address(
                        Metadata(
                            documentId="html-title",
                            version="0.0.0",
                            language="und",
                            section=title,
                        )
                    ),
                    heading=title,
                    level=0,
                    parentId=None,
                )
            )
        for idx, (level, heading) in enumerate(levels):
            parent = None
            for prev in reversed(sections):
                if prev.level < level:
                    parent = prev.id
                    break
            section_id = content_address(
                Metadata(
                    documentId=f"html-section-{idx}",
                    version="0.0.0",
                    language="und",
                    section=heading,
                )
            )
            sections.append(
                Section(
                    id=section_id,
                    heading=heading,
                    level=level,
                    parentId=parent,
                )
            )
        return sections

    @staticmethod
    def _build_document(source: Source, title: str,
                        sections: list) -> Document:
        return Document(
            id=content_address(
                Metadata(
                    documentId=source.id,
                    version="0.0.0",
                    language="und",
                )
            ),
            title=title,
            sections=tuple(sections),
            metadata=Metadata(
                documentId=source.id,
                version="0.0.0",
                language="html",
                sourcePath=source.uri,
            ),
        )

    @staticmethod
    def _empty_document(source: Source) -> Document:
        return Document(
            id=content_address(
                Metadata(
                    documentId=source.id or "html-empty",
                    version="0.0.0",
                    language="und",
                )
            ),
            title="(empty)",
            sections=(),
            metadata=Metadata(
                documentId=source.id or "html-empty",
                version="0.0.0",
                language="html",
                sourcePath=source.uri,
            ),
        )
