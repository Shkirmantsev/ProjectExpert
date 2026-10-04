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


def read_text(uri):
    try:
        from pi_platform.adapters.fs import LocalFilesystemAdapter

        raw = LocalFilesystemAdapter(Path(uri).resolve().parent).read_source_bytes(
            Path(uri)
        )
        if b"\0" in raw[:16384]:
            raise SourceAdapterError("binary source contains NUL bytes")
        return raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except (OSError, UnicodeError) as exc:
        raise SourceAdapterError(f"cannot read text source {uri}: {exc}") from exc


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
        sourcePath=source.uri,
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
