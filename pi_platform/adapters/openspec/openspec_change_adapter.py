"""OpenSpecChangeAdapter for openspec/specs and openspec/changes trees."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path
from typing import Optional, Sequence

from pi_platform.core.canonical.content_address import (
    content_address,
    content_address_bytes,
)
from pi_platform.core.canonical.value_types import (
    Chunk,
    Document,
    Entity,
    Evidence,
    KnowledgeState,
    Metadata,
    Relation,
    Section,
    Source,
)

from pi_platform.ports.ingest.chunker import ChunkerContext, ChunkerPort
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterContext,
    SourceAdapterPort,
    SourceContentFamily,
    SourceParseResult,
)


__all__ = [
    "OpenSpecChangeAdapter",
    "OpenSpecChunker",
    "OpenSpecEntityExtractor",
]


_OPENSPEC_ARTIFACTS = frozenset({
    "proposal.md",
    "design.md",
    "context-impact.md",
    "tasks.md",
    "spec.md",
})

_REQUIREMENT_RE = re.compile(r"^#{0,6}\s*Requirement:\s*(\S.*)$")
_PURPOSE_RE = re.compile(r"^#{0,6}\s*Purpose:\s*(\S.*)$")


def _is_archived(uri: str) -> bool:
    parts = Path(uri).parts
    return any(
        parts[i] == "openspec"
        and parts[i + 1] == "changes"
        and parts[i + 2] == "archive"
        for i in range(len(parts) - 2)
    )


class OpenSpecChangeAdapter(SourceAdapterPort):
    """SourceAdapter delegating OpenSpec Markdown to MarkdownAdapter."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.OPENSPEC

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        from pi_platform.adapters.markdown.markdown_adapter import (
            MarkdownAdapter,
        )

        result = MarkdownAdapter().parse(source, context)
        if Path(source.uri).name in _OPENSPEC_ARTIFACTS:
            document = replace(
                result.document,
                metadata=replace(result.document.metadata, language="openspec"),
            )
            result = replace(result, document=document)
        return result


class OpenSpecChunker(ChunkerPort):
    """One Chunk per ``Requirement:`` section heading."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.OPENSPEC

    def chunk(self, document: Document, sections: Sequence[Section],
              context: Optional[ChunkerContext] = None) -> Sequence[Chunk]:
        chunks: list[Chunk] = []
        for section in sections:
            if not section.heading.startswith("Requirement: "):
                continue
            name = section.heading[len("Requirement: "):]
            metadata = Metadata(
                documentId=document.id,
                version="0.0.0",
                language=document.metadata.language or "openspec",
                section=section.heading,
                sourcePath=document.metadata.sourcePath,
            )
            content_hash = content_address_bytes(name.encode("utf-8"))
            provenance = Evidence(
                knowledgeState=KnowledgeState.VERIFIED,
                parserVersion="openspec-chunker-0.1.0",
            )
            chunk_id = content_address(
                Chunk(
                    id="placeholder",
                    rawText=name,
                    contextualText=name,
                    metadata=metadata,
                    sourceReference=document.id,
                    contentHash=content_hash,
                    parentId=document.id,
                    childIds=(),
                    entityIds=(),
                    provenance=provenance,
                )
            )
            chunks.append(
                Chunk(
                    id=chunk_id,
                    rawText=name,
                    contextualText=name,
                    metadata=metadata,
                    sourceReference=document.id,
                    contentHash=content_hash,
                    parentId=document.id,
                    childIds=(),
                    entityIds=(),
                    provenance=provenance,
                )
            )
        return tuple(chunks)


class OpenSpecEntityExtractor:
    """Emit Requirement / Specification / OpenSpecChange entities."""

    def extract(self, document: Document, source: Source
                ) -> tuple[Sequence[Entity], Sequence[Relation]]:
        knowledge_state = (
            KnowledgeState.STALE if _is_archived(source.uri)
            else KnowledgeState.VERIFIED
        )
        metadata = Metadata(
            documentId=document.id,
            version="0.0.0",
            language=document.metadata.language or "openspec",
            sourcePath=source.uri,
        )
        change_entity = Entity(
            id=source.id,
            family="openspec_change",
            label=document.title or Path(source.uri).name or source.id,
            metadata=metadata,
            knowledgeState=knowledge_state,
        )
        requirements: list[Entity] = []
        specifications: list[Entity] = []
        seen: set[str] = {change_entity.id}
        for section in document.sections:
            lines = [section.heading]
            for chunk in section.chunks:
                lines.extend(chunk.rawText.splitlines())
            for line in lines:
                stripped = line.strip()
                requirement_match = _REQUIREMENT_RE.match(stripped)
                if requirement_match:
                    label = requirement_match.group(1).strip()
                    entity = Entity(
                        id=content_address(
                            {
                                "family": "requirement",
                                "label": label,
                                "documentId": document.id,
                            }
                        ),
                        family="requirement",
                        label=label,
                        metadata=metadata,
                        knowledgeState=knowledge_state,
                    )
                    if entity.id not in seen:
                        seen.add(entity.id)
                        requirements.append(entity)
                purpose_match = _PURPOSE_RE.match(stripped)
                if purpose_match:
                    label = purpose_match.group(1).strip()[:80]
                    entity = Entity(
                        id=content_address(
                            {
                                "family": "specification",
                                "label": label,
                                "documentId": document.id,
                            }
                        ),
                        family="specification",
                        label=label,
                        metadata=metadata,
                        knowledgeState=knowledge_state,
                    )
                    if entity.id not in seen:
                        seen.add(entity.id)
                        specifications.append(entity)
        entities: list[Entity] = [change_entity]
        entities.extend(specifications)
        entities.extend(requirements)
        relations: list[Relation] = []
        for specification in specifications:
            for requirement in requirements:
                relations.append(
                    Relation(
                        sourceId=requirement.id,
                        targetId=specification.id,
                        family="part_of",
                        knowledgeState=knowledge_state,
                    )
                )
        for requirement in requirements:
            relations.append(
                Relation(
                    sourceId=requirement.id,
                    targetId=change_entity.id,
                    family="satisfies",
                    knowledgeState=knowledge_state,
                )
            )
        return tuple(entities), tuple(relations)
