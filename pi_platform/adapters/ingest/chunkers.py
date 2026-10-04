"""Structural chunkers retain bodies, parent links and UTF-8 byte budgets."""

import logging
import re
from dataclasses import replace
from pi_platform.core.ingest.records import make_chunk
from pi_platform.ports.ingest.chunker import ChunkerPort, ChunkerError
from pi_platform.ports.ingest.source_adapter import SourceContentFamily

log = logging.getLogger(__name__)


def _split_bytes(text, maximum):
    pieces = []
    while len(text.encode("utf-8")) > maximum:
        prefix = text.encode("utf-8")[:maximum].decode("utf-8", errors="ignore")
        if not prefix:
            raise ChunkerError("maxChunkBytes cannot fit a source character")
        cut = max(prefix.rfind("\n"), prefix.rfind(" "))
        cut = cut + 1 if cut > len(prefix) // 2 else len(prefix)
        pieces.append(text[:cut])
        text = text[cut:]
    if text:
        pieces.append(text)
    return pieces


class PlainTextChunker(ChunkerPort):
    family = SourceContentFamily.PLAIN_TEXT

    def chunk(self, document, sections, context=None):
        maximum = context.max_chunk_bytes if context else 4096
        minimum = int(context.extra.get("min_chunk_bytes", 256)) if context else 256
        if maximum <= 0 or minimum < 0:
            raise ChunkerError("invalid chunk byte budget")
        result = []
        for section in sections:
            body = "\n\n".join(c.rawText for c in section.chunks)
            paragraphs = [p for p in re.split(r"\n\s*\n", body) if p.strip()]
            pieces = []
            for p in paragraphs:
                parts = _split_bytes(p, maximum)
                for part in parts:
                    if (
                        pieces
                        and len(pieces[-1].encode()) < minimum
                        and len((pieces[-1] + "\n\n" + part).encode()) <= maximum
                    ):
                        pieces[-1] += "\n\n" + part
                        log.info(
                            "chunk merge source=%s section=%s", document.id, section.id
                        )
                    else:
                        pieces.append(part)
            for i, text in enumerate(pieces):
                decision = (
                    "split"
                    if len(body.encode()) > maximum
                    else "merge" if len(pieces) < len(paragraphs) else "structural"
                )
                attrs = (
                    dict(section.chunks[0].metadata.extensions)
                    if section.chunks
                    else {}
                )
                attrs["mergeOrSplit"] = {
                    "decision": decision,
                    "boundary": "paragraph/word",
                    "maxChunkBytes": maximum,
                }
                if decision == "split":
                    log.info(
                        "chunk split source=%s section=%s", document.id, section.id
                    )
                chunk = make_chunk(
                    document,
                    section,
                    text,
                    parser_version="structural-chunker-1",
                    extensions=attrs,
                    index=i,
                )
                directive = re.search(r"<!--\s*requirement:\s*([^\s>]+)", body)
                if directive:
                    chunk = replace(
                        chunk,
                        metadata=replace(chunk.metadata, requirementId=directive[1]),
                    )
                result.append(chunk)
        return tuple(result)


class MarkdownChunker(PlainTextChunker):
    family = SourceContentFamily.MARKDOWN


class HtmlChunker(PlainTextChunker):
    family = SourceContentFamily.HTML


class RequirementIdChunker(PlainTextChunker):
    """Explicit requirement-id strategy, selected by the caller's registry."""

    def chunk(self, document, sections, context=None):
        from pi_platform.core.canonical.value_types import Section

        split = []
        for s in sections:
            for c in s.chunks:
                for i, part in enumerate(
                    re.split(r"(?=\b(?:REQ|SHALL|MUST)-\d+\b)", c.rawText)
                ):
                    if part.strip():
                        split.append(
                            replace(
                                s, id=f"{s.id}-{i}", chunks=(replace(c, rawText=part),)
                            )
                        )
        return super().chunk(document, split, context)


class ProtocolMessageChunker(PlainTextChunker):
    """Split message declarations, preserving their source section parents."""

    def chunk(self, document, sections, context=None):
        split = []
        for s in sections:
            body = "\n\n".join(c.rawText for c in s.chunks)
            for i, part in enumerate(
                re.split(r"(?m)(?=^\s*(?:message|Message)\s+\w+)", body)
            ):
                if part.strip() and s.chunks:
                    split.append(
                        replace(
                            s,
                            id=f"{s.id}-message-{i}",
                            chunks=(replace(s.chunks[0], rawText=part),),
                        )
                    )
        return super().chunk(document, split, context)


class TableChunker(PlainTextChunker):
    """Keep the table header in every budgeted table fragment."""

    def chunk(self, document, sections, context=None):
        maximum = context.max_chunk_bytes if context else 4096
        output = []
        for section in sections:
            lines = "\n".join(c.rawText for c in section.chunks).splitlines()
            if not lines:
                continue
            header = lines[0]
            if len(header.encode()) >= maximum:
                raise ChunkerError("table header exceeds chunk budget")
            groups = []
            buffer = [header]
            for line in lines[1:]:
                if len(("\n".join(buffer + [line])).encode()) > maximum:
                    if len(buffer) > 1:
                        groups.append("\n".join(buffer))
                        buffer = [header]
                    for fragment in _split_bytes(
                        line, maximum - len(header.encode()) - 1
                    ):
                        groups.append(header + "\n" + fragment)
                else:
                    buffer.append(line)
            if len(buffer) > 1 or not groups:
                groups.append("\n".join(buffer))
            for i, text in enumerate(groups):
                output.append(
                    make_chunk(
                        document,
                        section,
                        text,
                        parser_version="table-chunker-1",
                        index=i,
                        extensions={
                            "tableHeader": header,
                            "tableFingerprint": content_address_for_text(
                                "\n".join(lines)
                            ),
                            "mergeOrSplit": {
                                "decision": (
                                    "split" if len(groups) > 1 else "structural"
                                ),
                                "boundary": "table-row",
                            },
                        },
                    )
                )
        return tuple(output)


class ArchitectureUnitChunker(PlainTextChunker):
    """Architecture units follow section structure; dependent units retain child links."""

    def chunk(self, document, sections, context=None):
        chunks = super().chunk(document, sections, context)
        owners = {
            s.id: next((c.id for c in chunks if c.parentId == s.id), None)
            for s in sections
        }
        by_section = {s.id: s for s in sections}
        linked = []
        for c in chunks:
            section = by_section[c.parentId]
            parent = owners.get(section.parentId) or document.id
            linked.append(replace(c, parentId=parent))
        return tuple(
            replace(c, childIds=tuple(x.id for x in linked if x.parentId == c.id))
            for c in linked
        )


def content_address_for_text(text):
    from pi_platform.core.canonical.content_address import content_address_bytes

    return content_address_bytes(text.encode("utf-8"))
