"""Default local text adapter; unsupported and binary input fails explicitly."""

from pathlib import Path
from pi_platform.core.ingest.records import document_result, read_text_with_provenance
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
)
from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter
from pi_platform.adapters.html.html_adapter import HtmlAdapter

DEFAULT_PLAIN_TEXT_FAMILY = SourceContentFamily.PLAIN_TEXT


class LocalSourceAdapter(SourceAdapterPort):
    family = DEFAULT_PLAIN_TEXT_FAMILY

    def parse(self, source, context=None):
        if source.uri.lower().endswith((".md", ".markdown")):
            return MarkdownAdapter().parse(source, context)
        if source.uri.lower().endswith((".html", ".htm")):
            return HtmlAdapter().parse(source, context)
        from pi_platform.core.canonical.value_types import KnowledgeState
        legacy = Path(source.uri).suffix.lower() in (".txt", ".text", ".csv", ".log", ".xml", ".properties")
        text, decoding = read_text_with_provenance(source.uri, legacy=legacy,
                                                   html=Path(source.uri).suffix.lower() == ".xml")
        return document_result(
            source, [("", 0, text, {"textDecoding": decoding})], "plain_text", "text-stdlib-2",
            state=KnowledgeState.ASSUMPTION if decoding["degraded"] else KnowledgeState.VERIFIED,
            rationale="text decoding required replacement" if decoding["degraded"] else None,
        )
