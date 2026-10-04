"""MarkdownAdapter — shared Markdown SourceAdapter.

Covers architecture §3 source coverage. The adapter splits a
Markdown document into a :class:`Document` plus a sequence of
:class:`Section` records using the stdlib-only heuristic
documented in
``.ai/wiki/interfaces/source-adapters.md``. No third-party
dependency is required.

The adapter is shared with :class:`OpenSpecChangeAdapter` so the
Markdown parsing logic is not duplicated.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

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


__all__ = ["MarkdownAdapter"]


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)


class MarkdownAdapter(SourceAdapterPort):
    """Stdlib-only Markdown SourceAdapter."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.MARKDOWN

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        text = self._read_text(source.uri)
        sections = self._split_sections(text)
        document = self._build_document(source, text, sections)
        return SourceParseResult(
            document=document,
            sections=tuple(sections),
            knowledge_state=KnowledgeState.VERIFIED,
            parser_version="markdown-stdlib-0.1.0",
        )

    @staticmethod
    def _read_text(uri: str) -> str:
        try:
            return Path(uri).read_text(encoding="utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            return ""

    @staticmethod
    def _split_sections(text: str) -> list[Section]:
        matches = list(_HEADING_RE.finditer(text))
        if not matches:
            return [
                Section(
                    id=content_address(
                        Metadata(
                            documentId="md-body",
                            version="0.0.0",
                            language="und",
                        )
                    ),
                    heading="",
                    level=0,
                    parentId=None,
                )
            ]
        sections: list[Section] = []
        for idx, match in enumerate(matches):
            level = len(match.group(1))
            heading = match.group(2).strip()
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
            body = text[start:end]
            section_id = content_address(
                Metadata(
                    documentId=f"md-heading-{idx}",
                    version="0.0.0",
                    language="und",
                    section=heading,
                )
            )
            parent = sections[-1].id if sections and sections[-1].level < level else None
            sections.append(
                Section(
                    id=section_id,
                    heading=heading,
                    level=level,
                    parentId=parent,
                )
            )
            _ = body  # the body is captured by the next section's start
        return sections

    @staticmethod
    def _build_document(source: Source, text: str,
                        sections: list[Section]) -> Document:
        title = ""
        for section in sections:
            if section.level == 1 and section.heading:
                title = section.heading
                break
        if not title:
            title = Path(source.uri).stem
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
                language="markdown",
                sourcePath=source.uri,
            ),
        )
