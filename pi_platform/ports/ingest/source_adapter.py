"""SourceAdapter port for the v0.8 Phase 2 ingestion pipeline.

Covers architecture sections §3 (source coverage) and §8.2
(content-hash computation). Every content-type adapter implements
the port, producing a :class:`Document` plus a sequence of
:class:`Section` records from a :class:`Source`.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import (
    Document,
    Entity,
    Relation,
    Evidence,
    KnowledgeState,
    Metadata,
    Section,
    Source,
)


__all__ = [
    "SourceAdapterPort",
    "SourceContentFamily",
    "SourceAdapterRegistry",
    "SourceAdapterError",
    "AdapterMissing",
    "AdapterCorruptOutput",
    "UnsupportedFamily",
]


class SourceContentFamily(str, enum.Enum):
    """Source content families supported by the adapter registry.

    Stable string values keep the registry indexable by family and
    the canonical JSON deterministic.
    """

    MARKDOWN = "markdown"
    HTML = "html"
    PLAIN_TEXT = "plain_text"
    JAVA_SOURCE = "java_source"
    JAR = "jar"
    MAVEN_POM = "maven_pom"
    GRADLE_BUILD = "gradle_build"
    OPENAPI = "openapi"
    OPENSPEC = "openspec"
    PDF = "pdf"
    OFFICE = "office"
    JAVA_BYTECODE = "java_bytecode"
    OPENSPEC_SPEC = "openspec_spec"
    OPENSPEC_CHANGE = "openspec_change"
    ADR = "adr"
    LOCAL_INBOX = "local_inbox"
    UNKNOWN = "unknown"


class SourceAdapterError(RuntimeError):
    """Base class for SourceAdapter errors."""


class AdapterMissing(SourceAdapterError):
    """Raised when the registry has no adapter for the requested family."""


class AdapterCorruptOutput(SourceAdapterError):
    """Raised when an adapter produces a malformed Document or Section."""


class UnsupportedFamily(SourceAdapterError):
    """Raised when an adapter refuses to handle a particular family."""


@dataclass
class SourceAdapterContext:
    project_root: Path
    metadata_overrides: Mapping[str, object] = field(default_factory=dict)
    project_version: object = None
    working_tree_overlay: object = None
    cancellation: object = None


@dataclass(frozen=True)
class SourceParseResult:
    document: Document
    sections: Sequence[Section]
    knowledge_state: KnowledgeState = KnowledgeState.VERIFIED
    parser_version: str = "0.1.0"
    rationale: Optional[str] = None
    entities: Sequence[Entity] = field(default_factory=tuple)
    relations: Sequence[Relation] = field(default_factory=tuple)
    evidence: Sequence[Evidence] = field(default_factory=tuple)
    source: Optional[Source] = None


class SourceAdapterPort(abc.ABC):
    """Adapter contract: turn a :class:`Source` into a :class:`Document`."""

    @property
    @abc.abstractmethod
    def family(self) -> SourceContentFamily: ...

    @abc.abstractmethod
    def parse(
        self, source: Source, context: Optional[SourceAdapterContext] = None
    ) -> SourceParseResult: ...


class SourceAdapterRegistry:
    """Map :class:`SourceContentFamily` to the registered adapter."""

    def __init__(self) -> None:
        self._adapters: dict[SourceContentFamily, SourceAdapterPort] = {}

    def register(self, adapter: SourceAdapterPort) -> None:
        self._adapters[adapter.family] = adapter

    def unregister(self, family: SourceContentFamily) -> None:
        self._adapters.pop(family, None)

    def resolve(self, family: SourceContentFamily) -> SourceAdapterPort:
        aliases = {
            SourceContentFamily.JAVA_BYTECODE: SourceContentFamily.JAR,
            SourceContentFamily.OPENSPEC_SPEC: SourceContentFamily.OPENSPEC,
            SourceContentFamily.OPENSPEC_CHANGE: SourceContentFamily.OPENSPEC,
            SourceContentFamily.ADR: SourceContentFamily.OPENSPEC,
            SourceContentFamily.LOCAL_INBOX: SourceContentFamily.PLAIN_TEXT,
        }
        adapter = self._adapters.get(aliases.get(family, family))
        if adapter is None:
            raise AdapterMissing(f"no adapter registered for family {family!r}")
        return adapter

    def has(self, family: SourceContentFamily) -> bool:
        try:
            self.resolve(family)
            return True
        except AdapterMissing:
            return False

    def families(self) -> Sequence[SourceContentFamily]:
        return tuple(self._adapters.keys())


PLANNED_ADAPTERS = (
    {"name": "PdfAdapter", "family": "pdf", "dependency": "pdfplumber", "spdx": "MIT"},
    {
        "name": "OpenApiAdapter",
        "family": "openapi",
        "dependency": "openapi-schema-validator",
        "spdx": "Apache-2.0",
    },
    {
        "name": "OfficeAdapter",
        "family": "office",
        "dependency": "python-docx",
        "spdx": "MIT",
    },
)
