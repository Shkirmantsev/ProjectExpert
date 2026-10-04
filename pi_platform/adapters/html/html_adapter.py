"""HTML headings and semantic containers with body text, excluding active content."""

from html.parser import HTMLParser
from pi_platform.core.ingest.records import document_result, read_text
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
)


class _SectionParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows, self.body, self.heading_buf = [], [], []
        self.heading, self.level, self.in_heading, self.ignored = "", 0, False, 0

    def flush(self):
        text = "".join(self.body).strip()
        if text or self.heading:
            self.rows.append((self.heading, self.level, text, {}))
        self.body = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "head"):
            self.ignored += 1
        if self.ignored:
            return
        if tag in ("section", "article") or tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.flush()
            self.heading = tag if tag in ("section", "article") else ""
            self.level = int(tag[1]) if tag.startswith("h") else 2
            self.in_heading = tag.startswith("h")
            self.heading_buf = []
        elif tag in ("p", "div", "br", "tr"):
            self.body.append("\n\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "head"):
            self.ignored = max(0, self.ignored - 1)
            return
        if self.ignored:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self.heading = "".join(self.heading_buf).strip()
            self.in_heading = False
        elif tag in ("p", "div", "tr"):
            self.body.append("\n\n")
        elif tag in ("td", "th"):
            self.body.append(" | ")

    def handle_data(self, data):
        if not self.ignored:
            (self.heading_buf if self.in_heading else self.body).append(data)


class HtmlAdapter(SourceAdapterPort):
    family = SourceContentFamily.HTML

    def parse(self, source, context=None):
        parser = _SectionParser()
        parser.feed(read_text(source.uri))
        parser.close()
        parser.flush()
        return document_result(source, parser.rows, "html", "html-stdlib-1")
