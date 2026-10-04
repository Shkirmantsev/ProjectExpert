"""Canonical value types for the v0.8 Project Intelligence Platform.

Implements every Phase 1 value type listed in
`openspec/specs/2026-10-04-canonical-knowledge-schema/spec.md`:

  Source, Document, Section, Chunk, ContextualChunk, Entity,
  Relation, Evidence, KnowledgeState, ProjectVersion, Shard,
  Manifest, RuntimeChange, TaskContext, Metadata.

The value types are :class:`dataclasses.dataclass` instances with a
deterministic ``to_canonical_json`` / ``from_canonical_json`` pair.
Serialization rules (sorted keys, sorted identifier arrays, ``\\n``
line endings, trailing newline) live in
:mod:`platform.core.canonical.serializer`.

The module does not import any adapter, port, filesystem, Git or
license code; it stays a pure value-type package.
"""

from __future__ import annotations

import datetime as _dt
import enum
import sys
from collections.abc import Sequence as AbcSequence, Iterable as AbcIterable
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Iterable, Mapping, Optional, Sequence, Union

from .serializer import canonical_dump_json, canonical_load_json

# When ``from __future__ import annotations`` is enabled, dataclass
# field type annotations remain as strings rather than being resolved
# to their actual classes. The :func:`dataclass_from_dict` helper below
# needs the real classes to dispatch the coercion; this module-level
# dictionary is the lookup table used to resolve string annotations.
_MODULE_GLOBALS: dict[str, Any] = {k: v for k, v in globals().items()}
_MODULE_GLOBALS["__name__"] = __name__
_MODULE_GLOBALS.update(getattr(sys.modules[__name__], "__dict__", {}))


def _resolve_string_annotation(type_hint: Any) -> Any:
    """Resolve a possibly-string annotation to its real type object."""

    if not isinstance(type_hint, str):
        return type_hint
    try:
        return eval(type_hint, _MODULE_GLOBALS)
    except NameError:
        return type_hint


# Origins that signal a Sequence-like container. We treat them as tuple
# by default so Phase 1 value types stay immutable.
_SEQUENCE_ORIGINS = (list, tuple, Sequence, Iterable,
                    AbcSequence, AbcIterable)


__all__ = [
    "KnowledgeState",
    "Source",
    "Document",
    "Section",
    "Chunk",
    "ContextualChunk",
    "Entity",
    "Relation",
    "Evidence",
    "ProjectVersion",
    "Shard",
    "Manifest",
    "RuntimeChange",
    "TaskContext",
    "Metadata",
    "dataclass_to_dict",
    "dataclass_from_dict",
    "to_canonical_json",
    "from_canonical_json",
]


class KnowledgeState(str, enum.Enum):
    """Provenance state for every durable fact.

    Stable string values ensure byte-identical canonical serialization
    regardless of the import-time enum ordering.
    """

    VERIFIED = "verified"
    INFERRED = "inferred"
    ASSUMPTION = "assumption"
    CONFLICTING = "conflicting"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Metadata:
    """§23 metadata constraint.

    ``validFrom <= validTo`` is enforced at construction time via
    :meth:`__post_init__`. Volatile fields (timestamps, hostnames) are
    intentionally not part of this value type; the canonical serializer
    rejects them.
    """

    documentId: str
    version: str
    language: str
    section: Optional[str] = None
    businessDomain: Optional[str] = None
    module: Optional[str] = None
    className: Optional[str] = None
    requirementId: Optional[str] = None
    validFrom: Optional[str] = None
    validTo: Optional[str] = None
    gitCommit: Optional[str] = None
    sourcePath: Optional[str] = None
    page: Optional[int] = None
    line: Optional[int] = None
    securityClassification: Optional[str] = None
    contentHash: Optional[str] = None

    policy: Optional[str] = field(default=None, metadata={"omit_empty": True})
    extensions: Mapping[str, Any] = field(default_factory=dict, metadata={"omit_empty": True})

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Validate the metadata invariants.

        Raises ``ValueError`` when ``validFrom`` or ``validTo`` cannot
        be parsed or when ``validFrom > validTo``.
        """

        if self.validFrom is None and self.validTo is None:
            return
        try:
            vf = (
                _dt.datetime.fromisoformat(self.validFrom.replace("Z", "+00:00"))
                if self.validFrom else None
            )
            vt = (
                _dt.datetime.fromisoformat(self.validTo.replace("Z", "+00:00"))
                if self.validTo else None
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Metadata.validFrom ({self.validFrom!r}) or validTo "
                f"({self.validTo!r}) could not be parsed: {exc}"
            ) from exc
        if vf is not None and vt is not None and vf > vt:
            raise ValueError(
                f"Metadata.validFrom ({self.validFrom}) must be <= "
                f"validTo ({self.validTo})"
            )


@dataclass(frozen=True)
class Source:
    """A source document / file / URI registered with the platform."""

    id: str
    uri: str
    family: str
    contentHash: str
    metadata: Metadata = field(
        default_factory=lambda: Metadata(
            documentId="", version="0.0.0", language="und"
        )
    )


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    sections: Sequence["Section"] = field(default_factory=tuple)
    metadata: Metadata = field(
        default_factory=lambda: Metadata(
            documentId="", version="0.0.0", language="und"
        )
    )


@dataclass(frozen=True)
class Section:
    id: str
    heading: str
    level: int
    parentId: Optional[str] = None
    chunks: Sequence["Chunk"] = field(default_factory=tuple)


@dataclass(frozen=True)
class Chunk:
    """§21 chunk model."""

    id: str
    rawText: str
    contextualText: str
    metadata: Metadata
    sourceReference: str
    contentHash: str
    parentId: Optional[str] = None
    childIds: Sequence[str] = field(default_factory=tuple)
    entityIds: Sequence[str] = field(default_factory=tuple)
    provenance: "Evidence" = field(
        default_factory=lambda: Evidence(
            knowledgeState=KnowledgeState.UNKNOWN, parserVersion="0.1.0"
        )
    )


@dataclass(frozen=True)
class ContextualChunk:
    """A chunk plus the deterministic contextual prefix."""

    chunk: Chunk
    contextPrefix: str


@dataclass(frozen=True)
class Entity:
    id: str
    family: str
    label: str
    description: Optional[str] = None
    metadata: Metadata = field(
        default_factory=lambda: Metadata(
            documentId="", version="0.0.0", language="und"
        )
    )
    relations: Sequence["Relation"] = field(default_factory=tuple)
    knowledgeState: KnowledgeState = KnowledgeState.UNKNOWN


@dataclass(frozen=True)
class Relation:
    sourceId: str
    targetId: str
    family: str
    weight: float = 1.0
    evidence: Sequence["Evidence"] = field(default_factory=tuple)
    knowledgeState: KnowledgeState = KnowledgeState.UNKNOWN


@dataclass(frozen=True)
class Evidence:
    knowledgeState: KnowledgeState
    parserVersion: str
    sourceHash: Optional[str] = None
    lastVerifiedAt: Optional[str] = None
    rationale: Optional[str] = None


@dataclass(frozen=True)
class ProjectVersion:
    """§11 runtime project version identity."""

    gitHead: str
    workingTreeFingerprint: str
    knowledgeSchemaVersion: str
    embeddingModelVersion: str
    indexSchemaVersion: str


@dataclass(frozen=True)
class Shard:
    id: str
    path: str
    contentHash: str
    sourceHash: Optional[str] = None
    count: int = 0


@dataclass(frozen=True)
class Manifest:
    """Per-family manifest (§10.3)."""

    schemaVersion: str
    family: str
    shards: Sequence[Shard] = field(default_factory=tuple)
    dependencies: Sequence[str] = field(default_factory=tuple)
    contentHash: Optional[str] = None

    def with_content_hash(self, content_hash: str) -> "Manifest":
        return Manifest(
            schemaVersion=self.schemaVersion,
            family=self.family,
            shards=self.shards,
            dependencies=self.dependencies,
            contentHash=content_hash,
        )


@dataclass(frozen=True)
class RuntimeChange:
    """An enriched runtime change awaiting materialisation."""

    id: str
    kind: str
    payload: Mapping[str, Any]
    source: Source
    knowledgeState: KnowledgeState = KnowledgeState.VERIFIED


@dataclass(frozen=True)
class TaskContext:
    """§52 bounded context bundle for an agent task."""

    taskId: str
    goal: str
    budgetTokens: int
    chunks: Sequence[Chunk] = field(default_factory=tuple)
    entities: Sequence[Entity] = field(default_factory=tuple)
    openSpecIds: Sequence[str] = field(default_factory=tuple)
    requirements: Sequence[str] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Dataclass ↔ dict helpers used by the deterministic serializer.
# ---------------------------------------------------------------------------


# Identifier-array field names whose values are sorted ascending by
# string value when serialised to canonical form so two equivalent
# in-memory states produce byte-identical canonical files.
_ID_ARRAYS = frozenset({"childIds", "entityIds", "evidence",
                       "dependencies", "openSpecIds", "requirements",
                       "relations"})


def _is_user_defined_dataclass(obj: Any) -> bool:
    return is_dataclass(obj) and not isinstance(obj, type)


def _sort_identifier_list(values: list) -> list:
    """Sort an identifier array deterministically.

    Supports three shapes:

    * arrays of plain strings (sorted by string value);
    * arrays of dataclasses sorted by a documented ``id`` / ``targetId``
      / ``sourceId`` / ``uri`` key when present;
    * empty arrays.
    """

    cleaned = [v for v in values if v is not None and v != ""]
    if not cleaned:
        return list(values)
    if all(isinstance(v, str) for v in cleaned):
        return sorted(values, key=lambda v: "" if v is None else str(v))

    def _key(item: Any) -> tuple[str, str]:
        if not _is_user_defined_dataclass(item):
            return (str(type(item).__name__), "")
        primary = (
            getattr(item, "id", None)
            or getattr(item, "targetId", None)
            or (f"{getattr(item, 'sourceId', '')}__{getattr(item, 'targetId', '')}"
                if getattr(item, "sourceId", None) is not None else None)
            or getattr(item, "uri", None)
            or ""
        )
        return (str(primary or ""), "")

    return sorted(values, key=_key)


def dataclass_to_dict(obj: Any) -> Any:
    """Recursively convert a dataclass tree to plain dicts/lists/scalars.

    Lists and tuples of dataclass instances are walked recursively and
    the original container type is preserved so a round trip returns
    structurally equal dataclass instances.
    """

    if _is_user_defined_dataclass(obj):
        out: dict[str, Any] = {}
        for f in fields(obj):
            value = getattr(obj, f.name)
            if f.metadata.get("omit_empty") and not value:
                continue
            if f.name in _ID_ARRAYS and isinstance(value, (list, tuple)):
                value = _sort_identifier_list(list(value))
            out[f.name] = dataclass_to_dict(value)
        return out
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, tuple):
        return tuple(dataclass_to_dict(x) for x in obj)
    if isinstance(obj, list):
        return [dataclass_to_dict(x) for x in obj]
    if isinstance(obj, Mapping):
        return {str(k): dataclass_to_dict(v) for k, v in obj.items()}
    return obj

def dataclass_from_dict(cls: type, data: Mapping[str, Any]) -> Any:
    """Inverse of :func:`dataclass_to_dict`.

    Supports nested dataclasses, enums, lists/tuples and Optional
    fields. Unknown keys are ignored.
    """

    if not is_dataclass(cls):
        raise TypeError(
            f"dataclass_from_dict requires a dataclass type, got {clone!r}"
        )
    hints = _safe_get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in data:
            continue
        type_hint = hints.get(f.name, f.type)
        kwargs[f.name] = _coerce(type_hint, data[f.name], f.name,
                                default_factory=f.default_factory)
    return cls(**kwargs)


def _safe_get_type_hints(cls: type) -> dict[str, Any]:
    try:
        from typing import get_type_hints
        return get_type_hints(cls)
    except Exception:  # noqa: BLE001
        return {}


def _coerce(type_hint: Any, value: Any, field_name: str,
            default_factory: Any = None) -> Any:
    if value is None:
        return None
    type_hint = _resolve_string_annotation(type_hint)
    origin = getattr(type_hint, "__origin__", None)
    args = getattr(type_hint, "__args__", ())

    if origin is Union:
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            return _coerce(non_none[0], value, field_name, default_factory)
        return value
    if origin in _SEQUENCE_ORIGINS:
        if not args:
            return list(value)
        inner = _resolve_string_annotation(args[0])
        coerced = [_coerce(inner, x, field_name) for x in value]
        # Honour the field's default container type so dataclass
        # equality compares identical types after a round trip.
        expected = _expected_container(default_factory)
        if expected is tuple or origin is tuple or isinstance(value, tuple):
            return tuple(coerced)
        if expected is list or origin is list:
            return list(coerced)
        return list(coerced)
    if isinstance(type_hint, type) and issubclass(type_hint, enum.Enum):
        if isinstance(value, type_hint):
            return value
        return type_hint(value)
    if is_dataclass(type_hint) and isinstance(value, Mapping):
        return dataclass_from_dict(type_hint, value)
    return value


def _expected_container(default_factory: Any) -> Any:
    """Best-effort lookup of the field's default container type."""

    if default_factory is None:
        return None
    try:
        sample = default_factory()
    except Exception:  # noqa: BLE001
        return None
    if isinstance(sample, tuple):
        return tuple
    if isinstance(sample, list):
        return list
    return None


# ---------------------------------------------------------------------------
# Convenience wrappers for canonical JSON I/O.
# ---------------------------------------------------------------------------


def to_canonical_json(value: Any) -> bytes:
    """Serialise ``value`` to a deterministic JSON byte string with a
    trailing newline.
    """

    payload = canonical_dump_json(dataclass_to_dict(value))
    return payload


def from_canonical_json(cls: type, raw: Union[bytes, str]) -> Any:
    """Parse canonical JSON ``raw`` back into a ``cls`` instance."""

    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else raw
    payload = canonical_load_json(text)
    return dataclass_from_dict(cls, payload)