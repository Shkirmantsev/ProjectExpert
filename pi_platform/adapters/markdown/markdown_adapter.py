"""Shared Markdown parser: headings outside fenced blocks retain their bodies."""

import re
from pi_platform.core.ingest.records import document_result, read_text_with_provenance
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
)


class MarkdownAdapter(SourceAdapterPort):
    family = SourceContentFamily.MARKDOWN

    def parse(self, source, context=None):
        text, decoding = read_text_with_provenance(source.uri, automatic=True)
        attributes = {'textDecoding': decoding} if decoding.get('provenance') else {}
        rows, body = [], []
        heading, level, fence = "", 0, None
        for line in text.splitlines(keepends=True):
            marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
            if marker:
                char = marker[1][0]
                fence = None if fence == char else char if fence is None else fence
            match = (
                re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line)
                if fence is None and not marker
                else None
            )
            if match:
                if body or heading:
                    rows.append((heading, level, "".join(body).strip(), attributes))
                heading, level, body = match[2], len(match[1]), []
            else:
                body.append(line)
        if body or heading or not rows:
            rows.append((heading, level, "".join(body).strip(), attributes))
        return document_result(source, rows, "markdown", "markdown-stdlib-1")
