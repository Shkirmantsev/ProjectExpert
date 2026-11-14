"""Deterministic source-to-record helpers shared by ingestion adapters."""

from dataclasses import replace
from pathlib import Path
from pi_platform.core.canonical.content_address import (
    content_address,
    content_address_bytes,
)
from pi_platform.core.canonical.value_types import (
    Chunk,
    Document,
    Evidence,
    KnowledgeState,
    Metadata,
    Section,
)
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterError,
    SourceParseResult,
)


def read_text_with_provenance(uri, *, legacy=False, html=False):
    """Decode known text deterministically; never reinterpret binary as legacy text."""
    import codecs
    import re
    try:
        from pi_platform.adapters.fs import LocalFilesystemAdapter
        raw = LocalFilesystemAdapter(Path(uri).resolve().parent).read_source_bytes(Path(uri))
        encoding, replacements = None, 0
        for bom, codec in ((codecs.BOM_UTF32_LE, "utf-32"),
                           (codecs.BOM_UTF32_BE, "utf-32"),
                           (codecs.BOM_UTF16_LE, "utf-16"),
                           (codecs.BOM_UTF16_BE, "utf-16"),
                           (codecs.BOM_UTF8, "utf-8-sig")):
            if raw.startswith(bom):
                encoding = codec
                break
        if encoding is None:
            sample = raw[:16384]
            controls = sum(c < 32 and c not in (9, 10, 12, 13) for c in sample)
            if b"\0" in raw or (sample and controls / len(sample) > 0.01):
                raise SourceAdapterError("binary source is not text")
            try:
                text = raw.decode("utf-8")
                encoding = "utf-8"
            except UnicodeDecodeError:
                if html:
                    declaration = re.search(
                        br"(?:charset\s*=\s*[\"']?([A-Za-z0-9_-]+)|encoding\s*=\s*[\"']([A-Za-z0-9_-]+))",
                        raw[:4096], re.I)
                    if declaration:
                        declared = (declaration[1] or declaration[2]).decode("ascii").lower()
                        allowed = {"windows-1252": "cp1252", "cp1252": "cp1252",
                                   "iso-8859-1": "iso-8859-1", "latin-1": "iso-8859-1",
                                   "utf-8": "utf-8"}
                        encoding = allowed.get(declared)
                if encoding is None:
                    if not legacy:
                        raise
                    encoding = "cp1252"
                try:
                    text = raw.decode(encoding)
                except UnicodeDecodeError:
                    if not legacy:
                        raise
                    text = raw.decode(encoding, errors="replace")
                    replacements = text.count("\ufffd")
        else:
            text = raw.decode(encoding)
        if "\0" in text:
            raise SourceAdapterError("binary source contains NUL characters")
        return text.replace("\r\n", "\n").replace("\r", "\n"), {
            "encoding": encoding, "replacementCount": replacements,
            "degraded": bool(replacements),
        }
    except (OSError, UnicodeError) as exc:
        raise SourceAdapterError(f"cannot read text source {uri}: {exc}") from exc


def read_text(uri):
    return read_text_with_provenance(uri)[0]


def make_chunk(
    document,
    section,
    text,
    *,
    parent_id=None,
    parser_version="stdlib-1",
    extensions=None,
    index=0,
):
    parent = parent_id or section.id
    reference = document.metadata.sourcePath or document.id
    digest = content_address_bytes(text.encode("utf-8"))
    metadata = replace(
        document.metadata,
        documentId=document.id,
        section=section.heading or None,
        contentHash=digest,
        extensions={**document.metadata.extensions, **(extensions or {})},
    )
    key = content_address(
        {
            "rawText": text,
            "sourceReference": reference,
            "parentId": parent,
            "position": index,
        }
    )
    policy = metadata.policy
    state = {
        "LOCAL_ONLY": KnowledgeState.UNKNOWN,
        "REFERENCE": KnowledgeState.ASSUMPTION,
    }.get(policy, KnowledgeState.VERIFIED)
    evidence = Evidence(
        state,
        parser_version,
        document.metadata.contentHash,
        rationale=reference if policy else None,
    )
    return Chunk(
        key,
        text,
        text,
        metadata,
        reference,
        digest,
        parentId=parent,
        provenance=evidence,
    )


def document_result(
    source,
    rows,
    language,
    parser_version,
    *,
    entities=(),
    relations=(),
    evidence=(),
    state=KnowledgeState.VERIFIED,
    rationale=None,
):
    """Rows are (heading, level, body, attributes); bodies live in Section.chunks."""
    doc_id = source.id
    meta = replace(
        source.metadata,
        documentId=doc_id,
        language=language,
        sourcePath=(source.metadata.sourcePath if source.metadata.extensions.get("portable_identity") == "v2"
                    else source.uri),
        contentHash=source.contentHash,
    )
    doc = Document(doc_id, Path(source.uri).stem, metadata=meta)
    sections = []
    stack = []
    for i, (heading, level, body, attrs) in enumerate(rows):
        while stack and stack[-1].level >= level:
            stack.pop()
        sid = content_address({"document": doc_id, "heading": heading, "position": i})
        section = Section(sid, heading, level, parentId=stack[-1].id if stack else None)
        chunk = make_chunk(
            doc, section, body, parser_version=parser_version, extensions=attrs, index=i
        )
        if state is not KnowledgeState.VERIFIED:
            chunk = replace(chunk, provenance=Evidence(
                state, parser_version, source.contentHash, rationale=rationale))
        section = replace(section, chunks=(chunk,))
        sections.append(section)
        stack.append(section)
    title = next((s.heading for s in sections if s.level == 1 and s.heading), doc.title)
    doc = replace(doc, title=title, sections=tuple(sections))
    return SourceParseResult(
        doc,
        tuple(sections),
        state,
        parser_version,
        rationale,
        tuple(entities),
        tuple(relations),
        tuple(evidence),
        source,
    )
