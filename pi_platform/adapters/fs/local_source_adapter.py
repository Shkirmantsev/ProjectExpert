"""Default LocalSourceAdapter dispatching Markdown, HTML and plain text."""

from __future__ import annotations

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

from pi_platform.adapters.html.html_adapter import HtmlAdapter
from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter

from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterContext,
    SourceAdapterPort,
    SourceContentFamily,
    SourceParseResult,
)


__all__ = [
    "DEFAULT_PLAIN_TEXT_FAMILY",
    "LocalSourceAdapter",
]


DEFAULT_PLAIN_TEXT_FAMILY = SourceContentFamily.PLAIN_TEXT

_MARKDOWN_SUFFIXES = (".md", ".markdown")
_HTML_SUFFIXES = (".html", ".htm")


class LocalSourceAdapter(SourceAdapterPort):
    """Language-neutral default SourceAdapter for local files."""

    @property
    def family(self) -> SourceContentFamily:
        return DEFAULT_PLAIN_TEXT_FAMILY

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        self._read_text(source.uri)
        uri = source.uri.lower()
        if uri.endswith(_MARKDOWN_SUFFIXES):
            return MarkdownAdapter().parse(source, context)
        if uri.endswith(_HTML_SUFFIXES):
            return HtmlAdapter().parse(source, context)
        stem = Path(source.uri).stem
        section = Section(
            id=content_address(
                Metadata(
                    documentId=source.id,
                    version="0.0.0",
                    language="plain_text",
                    section=stem,
                )
            ),
            heading=stem,
            level=0,
            parentId=None,
        )
        document = Document(
            id=content_address(
                Metadata(
                    documentId=source.id,
                    version="0.0.0",
                    language="plain_text",
                )
            ),
            title=stem,
            sections=(section,),
            metadata=Metadata(
                documentId=source.id,
                version="0.0.0",
                language="plain_text",
                sourcePath=source.uri,
            ),
        )
        return SourceParseResult(
            document=document,
            sections=(section,),
            knowledge_state=KnowledgeState.VERIFIED,
            parser_version="local-source-0.1.0",
        )

    @staticmethod
    def _read_text(uri: str) -> str:
        raw = Path(uri).read_bytes()
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("latin-1")
