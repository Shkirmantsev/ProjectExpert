"""Current and proposed OpenSpec records share Markdown parsing and preserve status."""

import re
from dataclasses import replace
from pathlib import Path
from pi_platform.adapters.markdown.markdown_adapter import MarkdownAdapter
from pi_platform.adapters.ingest.chunkers import PlainTextChunker
from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    Entity,
    Evidence,
    Relation,
    KnowledgeState,
)
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
)


class OpenSpecChangeAdapter(SourceAdapterPort):
    family = SourceContentFamily.OPENSPEC

    def parse(self, source, context=None):
        path = Path(source.uri)
        if path.is_dir():
            from pi_platform.core.canonical.content_address import content_address_bytes
            from pi_platform.core.canonical.value_types import Source
            from pi_platform.core.ingest.records import document_result
            entities, relations, sections = {}, [], []
            for child in sorted(path.rglob("*.md")):
                if child.name != "spec.md":
                    continue
                nested = Source(content_address({"path":str(child)}), str(child), source.family, content_address_bytes(child.read_bytes()))
                parsed = self.parse(nested, context)
                entities.update((e.id,e) for e in parsed.entities)
                relations.extend(parsed.relations)
                sections.extend(parsed.sections)
            base = document_result(source, [], "openspec", "openspec-stdlib-1")
            return replace(base, document=replace(base.document, sections=tuple(sections)), sections=tuple(sections), entities=tuple(entities.values()), relations=tuple(relations), evidence=tuple(e for r in relations for e in r.evidence))
        result = MarkdownAdapter().parse(source, context)
        entities, relations = OpenSpecEntityExtractor().extract(result.document, source)
        return replace(
            result,
            document=replace(
                result.document,
                metadata=replace(result.document.metadata, language="openspec"),
            ),
            entities=entities,
            relations=relations,
            evidence=tuple(e for r in relations for e in r.evidence),
        )

    def active_changes(self, project_root):
        root = Path(project_root) / "openspec/changes"
        return (
            tuple(
                p.name
                for p in sorted(root.iterdir())
                if p.is_dir() and p.name != "archive"
            )
            if root.exists()
            else ()
        )


class OpenSpecChunker(PlainTextChunker):
    family = SourceContentFamily.OPENSPEC

    def chunk(self, document, sections, context=None):
        selected = []
        current = None
        for section in sections:
            if section.heading.startswith("Requirement:"):
                current = section
                selected.append(section)
            elif current and section.level > current.level:
                body = "\n\n".join(c.rawText for c in section.chunks)
                if body:
                    previous = selected[-1]
                    if previous.chunks:
                        c = previous.chunks[0]
                        selected[-1] = replace(
                            previous,
                            chunks=(
                                replace(
                                    c,
                                    rawText=c.rawText
                                    + "\n\n"
                                    + section.heading
                                    + "\n"
                                    + body,
                                ),
                            ),
                        )
            else:
                current = None
        return tuple(
            replace(c, parentId=document.id)
            for c in super().chunk(document, selected, context)
        )


class OpenSpecEntityExtractor:
    def extract(self, document, source):
        parts = Path(source.uri).parts
        archived = "archive" in parts
        change_index = parts.index("changes") + 1 if "changes" in parts else None
        change_id = (
            parts[change_index]
            if change_index is not None and len(parts) > change_index and not archived
            else None
        )
        capability = (
            Path(source.uri).parent.name
            if Path(source.uri).name == "spec.md"
            else document.title
        )
        status = "archived" if archived else "draft" if change_id else "active"
        state = (
            KnowledgeState.ASSUMPTION if status == "draft" else KnowledgeState.VERIFIED
        )
        # Reuse the canonical OKF frontmatter parser, including its minimal fallback.
        from pi_platform.core.canonical.okf import parse_frontmatter

        text = "\n".join(c.rawText for s in document.sections for c in s.chunks)
        frontmatter = {}
        try:
            from pi_platform.core.ingest.records import read_text

            frontmatter, _ = parse_frontmatter(read_text(source.uri))
        except (OSError, ValueError, RuntimeError):
            pass
        attrs = {
            "capabilityId": frontmatter.get("capability", capability),
            "phase": frontmatter.get("phase", 2),
            "status": status,
            **{k: v for k, v in frontmatter.items() if k.startswith("pi_")},
        }
        evidence = Evidence(state, "openspec-stdlib-1", source.contentHash)
        entities = []
        relations = []

        def add(family, label, attributes=None, knowledge=state, identity=None):
            eid = identity or content_address(
                {"source": source.id, "family": family, "label": label}
            )
            meta = replace(
                document.metadata,
                language="openspec",
                extensions={**attrs, **(attributes or {})},
            )
            entities.append(
                Entity(eid, family, label, metadata=meta, knowledgeState=knowledge)
            )
            return eid

        def link(a, b, family, knowledge=state):
            relations.append(
                Relation(
                    a,
                    b,
                    family,
                    evidence=(replace(evidence, knowledgeState=knowledge),),
                    knowledgeState=knowledge,
                )
            )

        parent = (
            add("OpenSpecChange", change_id, identity=change_id)
            if change_id
            else add("Capability", str(capability))
        )
        specification = add("Specification", str(capability))
        for s in document.sections:
            if s.heading.startswith("Requirement:"):
                rid = add("Requirement", s.heading.partition(":")[2].strip())
                link(specification, rid, "SATISFIES")
                link(rid, parent, "PART_OF")
        components = sorted(set(re.findall(r"pi_platform[./][\w./]+", text)))
        for name in components:
            cid = add("Component", name)
            link(specification, cid, "IMPLEMENTED_BY")
            if status == "draft":
                pending = add(
                    "PendingImplementation", name, knowledge=KnowledgeState.ASSUMPTION
                )
                link(specification, pending, "PENDING", KnowledgeState.ASSUMPTION)
        if frontmatter.get("kind") == "adr":
            aid = add("ArchitectureDecision", document.title)
            for e in list(entities):
                if e.family == "Component":
                    link(e.id, aid, "DOCUMENTED_BY")
        if status == "draft" and not components:
            pending = add(
                "PendingImplementation",
                change_id or str(capability),
                knowledge=KnowledgeState.ASSUMPTION,
            )
            link(specification, pending, "PENDING", KnowledgeState.ASSUMPTION)
        return tuple(entities), tuple(relations)
