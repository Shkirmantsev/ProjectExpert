"""JavaParser port for the v0.8 Phase 2 ingestion pipeline.

Covers architecture section §14 (structured code intelligence).
Defines the abstract JavaParserPort that adapters implement
(out-of-process tree-sitter-java subprocess is the default).
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence


__all__ = [
    "JavaParserPort",
    "JavaParseRequest",
    "JavaParseResult",
    "JavaParserError",
    "JavaParserMissing",
    "JavaParserTimeout",
    "JavaParserVersionMismatch",
    "JavaParserCorruptOutput",
]


class JavaParserError(RuntimeError):
    """Base class for JavaParser errors."""


class JavaParserMissing(JavaParserError):
    """Raised when the Java parser binary is not on PATH and required=true."""


class JavaParserTimeout(JavaParserError):
    """Raised when the Java parser subprocess times out."""


class JavaParserVersionMismatch(JavaParserError):
    """Raised when the parser reports a version the platform does not support."""


class JavaParserCorruptOutput(JavaParserError):
    """Raised when the parser produces a malformed parse result."""


class JavaEntityKind(str, enum.Enum):
    """Stable string values for parsed Java entities."""

    MODULE = "module"
    PACKAGE = "package"
    CLASS = "class"
    INTERFACE = "interface"
    ENUM = "enum"
    ANNOTATION = "annotation"
    METHOD = "method"
    CONSTRUCTOR = "constructor"
    FIELD = "field"
    IMPORT = "import"
    CALL = "call"
    ANNOTATION_USE = "annotation_use"
    JPA_MAPPING = "jpa_mapping"
    TEST = "test"


@dataclass
class JavaEntity:
    kind: JavaEntityKind
    name: str
    signature: str
    parent: Optional[str] = None
    annotations: Sequence[str] = field(default_factory=tuple)
    modifiers: Sequence[str] = field(default_factory=tuple)
    source_path: Optional[Path] = None
    line: Optional[int] = None
    knowledge_state_hint: str = "verified"
    attributes: Mapping[str, object] = field(default_factory=dict)


@dataclass
class JavaParseRequest:
    source: str
    file_path: Path
    parser_version: str = "tree-sitter-java-0.23.5"
    timeout_seconds: float = 60.0


@dataclass(frozen=True)
class JavaParseResult:
    entities: Sequence[JavaEntity]
    parser_version: str
    duration_ms: float
    degraded: bool = False
    rationale: Optional[str] = None


class JavaParserPort(abc.ABC):
    """Adapter contract: parse a Java source string into structured entities."""

    @property
    @abc.abstractmethod
    def parser_version(self) -> str: ...

    @abc.abstractmethod
    def parse(self, request: JavaParseRequest) -> JavaParseResult: ...

    @abc.abstractmethod
    def is_available(self) -> bool: ...
