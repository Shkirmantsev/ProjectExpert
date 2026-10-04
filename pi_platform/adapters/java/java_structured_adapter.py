"""Structured Java records and class/method chunks from an isolated AST parser."""

import re
from dataclasses import replace
from pathlib import Path
from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    Entity,
    Relation,
    Evidence,
    KnowledgeState,
)
from pi_platform.core.ingest.records import document_result, read_text, make_chunk
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
)
from pi_platform.ports.ingest.chunker import ChunkerPort
from pi_platform.ports.ingest.java_parser import JavaParseRequest
from .parser_subprocess import TreeSitterJavaSubprocess


class JavaStructuredAdapter(SourceAdapterPort):
    family = SourceContentFamily.JAVA_SOURCE

    def __init__(self, parser=None, *, required=False):
        self.parser = parser or TreeSitterJavaSubprocess(required=required)

    def parse(self, source, context=None):
        text = read_text(source.uri)
        if Path(source.uri).suffix in (".properties", ".yml", ".yaml"):
            rows = re.findall(r"^\s*([\w.\-]+)\s*[:=]\s*(.+)$", text, re.M)
            result = document_result(
                source,
                [(k, 1, v, {}) for k, v in rows],
                "configuration",
                "configuration-stdlib-1",
            )
            entities = tuple(
                Entity(
                    content_address({"source": source.id, "key": k}),
                    "ConfigurationProperty",
                    k,
                    description=v,
                    metadata=result.document.metadata,
                    knowledgeState=KnowledgeState.INFERRED,
                )
                for k, v in rows
            )
            return replace(result, entities=entities)
        parsed = self.parser.parse(
            JavaParseRequest(text, Path(source.uri), self.parser.parser_version)
        )
        state = (
            KnowledgeState.ASSUMPTION if parsed.degraded else KnowledgeState.VERIFIED
        )
        mapping = {
            "class": "JavaClass",
            "interface": "JavaInterface",
            "enum": "JavaClass",
            "annotation": "Annotation",
            "package": "JavaPackage",
            "method": "JavaMethod",
            "constructor": "JavaMethod",
            "field": "JavaField",
            "call": "JavaMethod",
        }
        rows = [
            (
                e.name,
                1 if e.kind.value in ("class", "interface", "enum") else 2,
                str(e.attributes.get("body", e.signature)),
                {
                    "javaKind": e.kind.value,
                    "qualifiedName": e.attributes.get("qualifiedName", e.name),
                    "parent": e.parent,
                    "line": e.line,
                },
            )
            for e in parsed.entities
            if e.kind.value in ("class", "interface", "enum", "method", "constructor")
        ]
        if not rows:
            rows = [(Path(source.uri).stem, 1, text, {"degraded": parsed.degraded})]
        result = document_result(
            source,
            rows,
            "java",
            parsed.parser_version,
            state=state,
            rationale=parsed.rationale,
        )
        entities, relations, evidence, names = [], [], [], {}
        ev = Evidence(
            state, parsed.parser_version, source.contentHash, rationale=parsed.rationale
        )

        def add(family, name, attrs=None, qualified=None):
            key = content_address(
                {
                    "source": source.id,
                    "family": family,
                    "name": qualified or name,
                    "attributes": attrs or {},
                }
            )
            meta = replace(
                result.document.metadata,
                className=(
                    qualified if family in ("JavaClass", "JavaInterface") else None
                ),
                extensions={
                    **(attrs or {}),
                    "pi_evidence": {
                        "knowledgeState": state.value,
                        "parserVersion": parsed.parser_version,
                        "sourceHash": source.contentHash,
                    },
                },
            )
            entity = Entity(key, family, name, metadata=meta, knowledgeState=state)
            entities.append(entity)
            evidence.append(ev)
            if qualified:
                names[qualified] = key
            return key

        def link(a, b, family):
            relations.append(
                Relation(a, b, family, evidence=(ev,), knowledgeState=state)
            )

        for e in parsed.entities:
            if e.kind.value == "call":
                continue
            family = mapping.get(e.kind.value, "JavaClass")
            qualified = str(e.attributes.get("qualifiedName", e.name))
            attrs = dict(e.attributes)
            attrs.pop("body", None)
            attrs["signature"] = e.signature
            attrs["modifiers"] = tuple(e.modifiers)
            eid = add(family, e.name, attrs, qualified)
            if e.parent in names:
                link(eid, names[e.parent], "PART_OF")
            for target in e.attributes.get("extends", []):
                link(eid, add("JavaClass", target, qualified=target), "EXTENDS")
            for target in e.attributes.get("implements", []):
                link(eid, add("JavaInterface", target, qualified=target), "IMPLEMENTS")
            for annotation in e.annotations:
                aid = add("Annotation", annotation)
                link(eid, aid, "ANNOTATED_BY")
            if any(re.match(r"@(?:[\w.]+\.)?Entity\b", a) for a in e.annotations):
                table = next(
                    (
                        re.search(r'name\s*=\s*"([^"]+)"', a)
                        for a in e.annotations
                        if "Table" in a
                    ),
                    None,
                )
                schema = next(
                    (
                        re.search(r'schema\s*=\s*"([^"]+)"', a)
                        for a in e.annotations
                        if "Table" in a
                    ),
                    None,
                )
                jid = add(
                    "JPAEntity",
                    e.name,
                    {
                        "tableName": table[1] if table else None,
                        "schema": schema[1] if schema else None,
                    },
                    qualified + ".jpa",
                )
                link(jid, eid, "PART_OF")
            if e.kind.value == "field" and any(
                any(
                    x in a
                    for x in (
                        "OneToMany",
                        "ManyToOne",
                        "ManyToMany",
                        "OneToOne",
                        "JoinColumn",
                        "Column",
                    )
                )
                for a in e.annotations
            ):
                target = re.search(r"<([\w.]+)>", str(e.attributes.get("type", "")))
                target_name = target[1] if target else str(e.attributes.get("type", ""))
                link(
                    eid,
                    add("JavaClass", target_name, qualified=target_name),
                    "MAPPED_BY",
                )
            if any(re.match(r"@(?:[\w.]+\.)?Test\b", a) for a in e.annotations):
                tid = add("Test", e.name, qualified=qualified + ".test")
                if e.parent in names:
                    link(tid, names[e.parent], "PART_OF")
                production = str(e.parent or "").rsplit(".", 1)[-1].removesuffix("Test")
                if production and production in str(e.attributes.get("body", "")):
                    link(
                        add("JavaClass", production, qualified=production),
                        tid,
                        "TESTED_BY",
                    )
        for e in parsed.entities:
            if e.kind.value == "call" and e.parent in names:
                target = add(
                    "JavaMethod",
                    e.name,
                    {"receiver": e.attributes.get("object", "")},
                    qualified=str(e.attributes.get("qualifiedName", e.name)) + ".call",
                )
                link(names[e.parent], target, "CALLS")
        return replace(
            result,
            entities=tuple(entities),
            relations=tuple(relations),
            evidence=tuple(evidence),
        )


class JavaStructuredChunker(ChunkerPort):
    family = SourceContentFamily.JAVA_SOURCE

    def chunk(self, document, sections, context=None):
        from pi_platform.adapters.ingest.chunkers import _split_bytes

        maximum = context.max_chunk_bytes if context else 4096
        chunks, names = [], {}
        for s in sections:
            for c in s.chunks:
                attrs = c.metadata.extensions
                parent = names.get(attrs.get("parent"), document.id)
                parts = _split_bytes(c.rawText, maximum)
                for i, text in enumerate(parts):
                    chunk = make_chunk(
                        document,
                        s,
                        text,
                        parent_id=parent,
                        parser_version=c.provenance.parserVersion,
                        extensions=attrs,
                        index=i,
                    )
                    chunk = replace(chunk, provenance=c.provenance)
                    chunks.append(chunk)
                    names.setdefault(attrs.get("qualifiedName"), chunk.id)
        return tuple(
            replace(c, childIds=tuple(x.id for x in chunks if x.parentId == c.id))
            for c in chunks
        )
