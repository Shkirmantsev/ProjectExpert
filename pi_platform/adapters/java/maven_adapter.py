"""Namespace-aware deterministic Maven POM extraction; no build execution at parse."""

import re
import xml.etree.ElementTree as ET
from dataclasses import replace
from pi_platform.core.ingest.records import read_text
from pi_platform.core.canonical.value_types import Entity, Relation, KnowledgeState
from pi_platform.core.canonical.content_address import content_address
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
    SourceAdapterError,
)
from .dependencies import BuildTreeMixin, dependency_records


class MavenAdapter(BuildTreeMixin, SourceAdapterPort):
    family = SourceContentFamily.MAVEN_POM
    binary, build_name = "mvn", "pom.xml"

    def __init__(self, inventory_path=None):
        self.inventory_path = inventory_path

    def parse(self, source, context=None):
        try:
            root = ET.fromstring(read_text(source.uri))
        except ET.ParseError as exc:
            raise SourceAdapterError(f"invalid Maven XML: {exc}") from exc
        for node in root.iter():
            node.tag = node.tag.rsplit("}", 1)[-1]
        props = {n.tag: n.text or "" for n in root.findall("./properties/*")}
        for key in ("groupId", "version"):
            props["project." + key] = (
                root.findtext(key) or root.findtext("parent/" + key) or ""
            )

        def value(text):
            text = text or ""
            for _ in range(10):
                updated = re.sub(
                    r"\$\{([^}]+)\}", lambda m: props.get(m[1], m[0]), text
                )
                if updated == text:
                    break
                text = updated
            return text

        managed = {
            f'{n.findtext("groupId")}:{n.findtext("artifactId")}': value(
                n.findtext("version")
            )
            for n in root.findall("./dependencyManagement/dependencies/dependency")
        }
        rows = []
        for n in root.findall("./dependencies/dependency"):
            group, artifact = value(n.findtext("groupId")), value(
                n.findtext("artifactId")
            )
            rows.append(
                {
                    "groupId": group,
                    "artifactId": artifact,
                    "version": value(n.findtext("version"))
                    or managed.get(f"{group}:{artifact}", "unknown"),
                    "scope": value(n.findtext("scope")) or "compile",
                    "classifier": value(n.findtext("classifier")),
                    "type": value(n.findtext("type")) or "jar",
                }
            )
        result = dependency_records(
            source,
            rows,
            root.findtext("artifactId") or "project",
            "maven-xml-1",
            self.inventory_path,
        )
        entities = list(result.entities)
        relations = list(result.relations)
        for n in root.findall("./modules/module"):
            eid = content_address({"source": source.id, "module": n.text or ""})
            entities.append(
                Entity(
                    eid,
                    "MavenModule",
                    n.text or "",
                    metadata=result.document.metadata,
                    knowledgeState=KnowledgeState.VERIFIED,
                )
            )
            relations.append(
                Relation(
                    eid,
                    result.entities[0].id,
                    "PART_OF",
                    knowledgeState=KnowledgeState.VERIFIED,
                )
            )
        return replace(result, entities=tuple(entities), relations=tuple(relations))
