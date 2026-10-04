"""JAR coordinates, JVM public APIs and resources through stdlib zip/class readers."""

import hashlib
import logging
import zipfile
from dataclasses import replace
from pathlib import Path
from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    Entity,
    Evidence,
    Relation,
    Source,
    KnowledgeState,
)
from pi_platform.core.ingest.records import document_result
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterPort,
    SourceContentFamily,
    SourceAdapterError,
)
from .dependencies import dependency_records
from .classfile import parse_class
from .java_structured_adapter import JavaStructuredAdapter

log = logging.getLogger(__name__)


class JarAdapter(SourceAdapterPort):
    family = SourceContentFamily.JAR

    def __init__(self, parser=None):
        self.parser = parser

    def parse(self, source, context=None):
        path = Path(source.uri)
        try:
            with zipfile.ZipFile(path) as archive:
                infos = archive.infolist()
                if sum(i.file_size for i in infos) > 256 * 1024 * 1024:
                    raise ValueError("JAR expanded size exceeds 256 MiB")
                manifest = {}
                for name in ("META-INF/MANIFEST.MF",):
                    if name in archive.namelist():
                        text = (
                            archive.read(name)
                            .decode("utf-8", errors="replace")
                            .replace("\r\n", "\n")
                            .replace("\n ", "")
                        )
                        manifest = dict(
                            line.split(": ", 1)
                            for line in text.splitlines()
                            if ": " in line
                        )
                props = {}
                for name in sorted(archive.namelist()):
                    if name.startswith("META-INF/maven/") and name.endswith(
                        "/pom.properties"
                    ):
                        props = dict(
                            line.split("=", 1)
                            for line in archive.read(name).decode().splitlines()
                            if "=" in line and not line.startswith("#")
                        )
                        break
                coords = {
                    "groupId": props.get(
                        "groupId", manifest.get("Implementation-Vendor-Id", "unknown")
                    ),
                    "artifactId": props.get(
                        "artifactId", manifest.get("Implementation-Title", path.stem)
                    ),
                    "version": props.get(
                        "version", manifest.get("Implementation-Version", "unknown")
                    ),
                    "classifier": "sources" if path.stem.endswith("-sources") else "",
                    "type": "sources" if path.stem.endswith("-sources") else "jar",
                    "scope": "runtime",
                }
                base = dependency_records(source, [coords], path.stem, "jar-stdlib-1")
                entities = list(base.entities)
                relations = list(base.relations)
                evidence = list(base.evidence)
                dependency = next(e for e in entities if e.family == "Dependency")
                packages = {}

                def add(family, label, attrs=None, source_hash=None):
                    ev = Evidence(
                        KnowledgeState.VERIFIED,
                        "jar-stdlib-1",
                        source_hash or source.contentHash,
                    )
                    meta = replace(
                        base.document.metadata,
                        extensions={
                            **(attrs or {}),
                            "pi_evidence": {
                                "knowledgeState": "verified",
                                "parserVersion": ev.parserVersion,
                                "sourceHash": ev.sourceHash,
                            },
                        },
                    )
                    eid = content_address(
                        {
                            "source": source.contentHash,
                            "family": family,
                            "label": label,
                            "attrs": attrs or {},
                        }
                    )
                    entities.append(
                        Entity(
                            eid,
                            family,
                            label,
                            metadata=meta,
                            knowledgeState=KnowledgeState.VERIFIED,
                        )
                    )
                    evidence.append(ev)
                    relations.append(
                        Relation(
                            dependency.id,
                            eid,
                            "CONTAINS",
                            evidence=(ev,),
                            knowledgeState=KnowledgeState.VERIFIED,
                        )
                    )
                    return eid

                for info in sorted(infos, key=lambda i: i.filename):
                    name = info.filename
                    if name.endswith("/"):
                        continue
                    if name.endswith(".class"):
                        cls = parse_class(archive.read(info))
                        if name == "module-info.class":
                            mid = add("Module", cls.get("moduleName", "module"), cls)
                            for export in cls.get("exports", []):
                                add("PublicApi", export, {"moduleId": mid})
                            continue
                        if not cls["access"] & 1:
                            continue
                        qualified = cls["name"].replace("/", ".")
                        package = qualified.rpartition(".")[0]
                        if package not in packages:
                            packages[package] = add("JavaPackage", package)
                        family = (
                            "JavaInterface" if cls["access"] & 0x200 else "JavaClass"
                        )
                        cid = add(
                            family,
                            qualified.rpartition(".")[2],
                            {
                                "packageName": package,
                                "className": qualified,
                                "modifiers": cls["access"],
                                "signature": cls.get("signature"),
                            },
                        )
                        add("PublicApi", qualified, {"classId": cid})
                        for target in [cls["superclass"], *cls["interfaces"]]:
                            if target:
                                tid = add("JavaClass", target.replace("/", "."))
                                relations.append(
                                    Relation(
                                        cid,
                                        tid,
                                        "InheritedType",
                                        knowledgeState=KnowledgeState.VERIFIED,
                                    )
                                )
                        for method in cls["methods"]:
                            mid = add("JavaMethod", method["name"], method)
                            relations.append(
                                Relation(
                                    mid,
                                    cid,
                                    "PART_OF",
                                    knowledgeState=KnowledgeState.VERIFIED,
                                )
                            )
                            for annotation in method.get("annotations", []):
                                aid = add("Annotation", annotation)
                                relations.append(
                                    Relation(
                                        mid,
                                        aid,
                                        "ANNOTATED_BY",
                                        knowledgeState=KnowledgeState.VERIFIED,
                                    )
                                )
                        for annotation in cls.get("annotations", []):
                            aid = add("Annotation", annotation)
                            relations.append(
                                Relation(
                                    cid,
                                    aid,
                                    "ANNOTATED_BY",
                                    knowledgeState=KnowledgeState.VERIFIED,
                                )
                            )
                    else:
                        add("Resource", name)
                source_jar = (
                    path
                    if path.stem.endswith("-sources")
                    else path.with_name(path.stem + "-sources.jar")
                )
                if source_jar.exists():
                    digest = hashlib.sha256(source_jar.read_bytes()).hexdigest()
                    log.info(
                        "JAR source preference binary=%s source=%s", path, source_jar
                    )
                    with zipfile.ZipFile(source_jar) as sources:
                        if (
                            sum(i.file_size for i in sources.infolist())
                            > 256 * 1024 * 1024
                        ):
                            raise ValueError("source JAR expanded size exceeds limit")
                        # Read source in a temporary directory; no archive path is extracted.
                        import tempfile

                        with tempfile.TemporaryDirectory() as directory:
                            parser = JavaStructuredAdapter(self.parser)
                            for i, name in enumerate(sorted(sources.namelist())):
                                if not name.endswith(".java"):
                                    continue
                                local = Path(directory) / f"{i}.java"
                                local.write_bytes(sources.read(name))
                                s = Source(
                                    content_address({"jar": digest, "entry": name}),
                                    str(local),
                                    "java_source",
                                    digest,
                                )
                                parsed = parser.parse(s)
                                for entity in parsed.entities:
                                    entity = replace(
                                        entity,
                                        metadata=replace(
                                            entity.metadata,
                                            sourcePath=f"{source_jar}!/{name}",
                                        ),
                                    )
                                    # Prefer source signatures over matching bytecode identities.
                                    match = next(
                                        (
                                            old
                                            for old in entities
                                            if old.family == entity.family
                                            and old.label == entity.label
                                            and old.metadata.extensions.get(
                                                "className", old.metadata.className
                                            )
                                            == (
                                                entity.metadata.extensions.get(
                                                    "className"
                                                )
                                                or entity.metadata.className
                                            )
                                        ),
                                        None,
                                    )
                                    if match:
                                        entities.remove(match)
                                        relations = [
                                            replace(
                                                r,
                                                sourceId=(
                                                    entity.id
                                                    if r.sourceId == match.id
                                                    else r.sourceId
                                                ),
                                                targetId=(
                                                    entity.id
                                                    if r.targetId == match.id
                                                    else r.targetId
                                                ),
                                            )
                                            for r in relations
                                        ]
                                    entities.append(entity)
                                    relations.append(
                                        Relation(
                                            entity.id,
                                            dependency.id,
                                            "DOCUMENTED_BY",
                                            knowledgeState=entity.knowledgeState,
                                        )
                                    )
                                evidence.extend(parsed.evidence)
                                relations.extend(parsed.relations)
                body = "\n".join(e.label for e in entities)
                result = document_result(
                    source,
                    [(path.stem, 1, body, {})],
                    "java_bytecode",
                    "jar-stdlib-1",
                    entities=entities,
                    relations=relations,
                    evidence=evidence,
                )
                return result
        except (OSError, zipfile.BadZipFile, ValueError, IndexError) as exc:
            raise SourceAdapterError(f"invalid JAR {path}: {exc}") from exc
