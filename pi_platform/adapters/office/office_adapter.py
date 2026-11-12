"""Bounded OOXML text extraction; unsupported Office formats fail explicitly."""
from pathlib import Path, PurePosixPath
import posixpath
from io import BytesIO
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree

from pi_platform.core.ingest.records import document_result
from pi_platform.core.canonical.value_types import KnowledgeState
from pi_platform.ports.ingest.source_adapter import SourceAdapterError, SourceAdapterPort, SourceContentFamily


class _OfficeTreeBuilder(ElementTree.TreeBuilder):
    def doctype(self, name, pubid, system):
        # The XML parser invokes this after decoding XML's declared encoding.
        # Checking raw byte substrings misses UTF-16 declarations/entities.
        raise SourceAdapterError("Office XML document types and entities are unsupported")


class OfficeAdapter(SourceAdapterPort):
    family = SourceContentFamily.OFFICE
    max_xml_bytes = 32 * 1024 * 1024
    max_archive_bytes = 256 * 1024 * 1024

    def parse(self, source, context=None):
        suffix = Path(source.uri).suffix.lower()
        if suffix not in (".docx", ".pptx"):
            raise SourceAdapterError(f"Office capability unavailable for {suffix}; supported: .docx, .pptx")
        try:
            source_path = Path(source.uri).absolute()
            root = Path(context.project_root).resolve() if context is not None else source_path.parent.resolve()
            resolved = source_path.resolve()
            if not resolved.is_relative_to(root):
                raise SourceAdapterError("Office source must stay inside the project root")
            current = source_path
            while current != root:
                if current.is_symlink():
                    raise SourceAdapterError("Office source path must not contain symlinks")
                if current == current.parent:
                    break
                current = current.parent
            if not resolved.is_file():
                raise SourceAdapterError("Office source must be a regular file")
            if resolved.stat().st_size > self.max_archive_bytes:
                raise SourceAdapterError("Office archive exceeds extraction size limit")
            from pi_platform.adapters.fs import LocalFilesystemAdapter
            raw_archive = LocalFilesystemAdapter(root).read_source_bytes(resolved)
            if len(raw_archive) > self.max_archive_bytes:
                raise SourceAdapterError("Office archive exceeds extraction size limit")
            partial = False
            with ZipFile(BytesIO(raw_archive)) as archive:
                consumed_xml = 0

                def read_xml(name):
                    nonlocal consumed_xml
                    consumed_xml += archive.getinfo(name).file_size
                    if consumed_xml > self.max_xml_bytes:
                        raise SourceAdapterError("Office XML exceeds extraction size limit")
                    return ElementTree.fromstring(archive.read(name),
                        parser=ElementTree.XMLParser(target=_OfficeTreeBuilder()))

                if suffix == ".docx":
                    names = ["word/document.xml"]
                else:
                    presentation = "ppt/presentation.xml"
                    relationships = "ppt/_rels/presentation.xml.rels"
                    if presentation in archive.namelist() and relationships in archive.namelist():
                        document = read_xml(presentation)
                        rels = {}
                        for relationship in read_xml(relationships):
                            if relationship.get("Type", "").endswith("/slide"):
                                if relationship.get("TargetMode", "Internal") != "Internal":
                                    raise SourceAdapterError("External slide relationships are unsupported")
                                target = relationship.get("Target", "")
                                if "\\" in target or ":" in target:
                                    raise SourceAdapterError("Unsafe slide relationship target")
                                name = posixpath.normpath(target.lstrip("/") if target.startswith("/")
                                                        else posixpath.join("ppt", target))
                                if not name.startswith("ppt/slides/") or ".." in PurePosixPath(name).parts:
                                    raise SourceAdapterError("Slide relationship must stay inside ppt/slides")
                                identity = relationship.get("Id")
                                if not identity or identity in rels:
                                    raise SourceAdapterError("Invalid duplicate slide relationship")
                                rels[identity] = name
                        names = []
                        for slide in document.iter():
                            if slide.tag.rsplit("}", 1)[-1] == "sldId":
                                identity = next((value for key, value in slide.attrib.items()
                                                 if key.startswith("{") and key.endswith("}id")), None)
                                if identity not in rels:
                                    raise SourceAdapterError("Slide relationship is missing")
                                names.append(rels[identity])
                    else:
                        # Minimal/incomplete packages have no authoritative slide order.
                        # Keep text searchable with explicit part identities and degradation.
                        names = sorted(name for name in archive.namelist()
                                       if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                                       and len(PurePosixPath(name).parts) == 3)
                        partial = True
                if not names or any(name not in archive.namelist() for name in names):
                    raise SourceAdapterError("Office package contains no supported document content")
                rows = []
                for index, name in enumerate(names):
                    document = read_xml(name)
                    paragraphs = []
                    for paragraph in document.iter():
                        if paragraph.tag.rsplit("}", 1)[-1] == "p":
                            paragraphs.append("".join(node.text or "" for node in paragraph.iter()
                                if node.tag.rsplit("}", 1)[-1] == "t"))
                    attributes = {"officeFormat": suffix[1:], "extraction": "ooxml-text", "part": name}
                    heading = ""
                    if suffix == ".pptx":
                        attributes["presentationOrderKnown"] = not partial
                        heading = f"Part {name}" if partial else f"Slide {index + 1}"
                        if not partial:
                            attributes["slideNumber"] = index + 1
                    rows.append((heading, 1, "\n".join(paragraphs), attributes))
        except (OSError, BadZipFile, KeyError, ValueError, ElementTree.ParseError) as exc:
            raise SourceAdapterError(f"Office extraction failed: {exc}") from exc
        return document_result(source, rows, "office", "ooxml-text-2",
            state=KnowledgeState.ASSUMPTION if partial else KnowledgeState.VERIFIED,
            rationale="partial extraction: presentation order unavailable" if partial else None)
