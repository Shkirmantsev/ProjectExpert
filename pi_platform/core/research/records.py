"""Domain records for the shared dependency research service.

The records are language-neutral on purpose: the MCP tools, the A2A
adapter and the CLI all exchange the same shapes, so a research answer
does not change when it travels through a different transport.

The vocabulary follows the accepted design:

``Package``
    An ecosystem package identity. ``resolved_version`` is ``None`` when
    the version is *unknown*; a declared constraint is not a resolution.

``PackageInstance``
    A package identity *plus* the context that makes it unique: the
    lock location, the workspace and the peer context. Two versions of
    the same package therefore stay distinct.

``DependencyEdge``
    A directed dependency relation. The target may be unresolved.

``EvidenceReference``
    Where a fact came from: repository identity/revision, artifact hash,
    contained member, lines, parser version and representation kind.

``ResearchResult``
    The envelope every research call returns: status, completeness,
    nodes/edges, evidence, warnings, truncation and cursor.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

__all__ = [
    "ResearchError",
    "InvalidResearchRequest",
    "ResearchDenied",
    "ResearchUnsupported",
    "StaleResearchCursor",
    "ResearchStatus",
    "Completeness",
    "Representation",
    "Package",
    "PackageInstance",
    "DependencyEdge",
    "EvidenceReference",
    "SymbolCard",
    "EcosystemSnapshot",
    "ResearchResult",
    "RESULT_SCHEMA_VERSION",
]


#: Schema version of the research result envelope. Bump it when the
#: meaning of an existing field changes; additive fields do not bump it.
RESULT_SCHEMA_VERSION = 1


class ResearchError(RuntimeError):
    """Base class for dependency research failures."""


class InvalidResearchRequest(ResearchError):
    """The caller asked for something the service refuses to interpret."""


class ResearchDenied(ResearchError):
    """The operation is not permitted by the active policy."""


class ResearchUnsupported(ResearchError):
    """The requested ecosystem, lock format or tool is not supported."""


class StaleResearchCursor(ResearchError):
    """The cursor belongs to another snapshot, query, policy or project."""


class ResearchStatus(str, enum.Enum):
    """The operational outcome of a research call.

    ``COMPLETE`` and ``PARTIAL`` are usable results. ``UNAVAILABLE``,
    ``DENIED``, ``UNSUPPORTED`` and ``FAILED`` are not: they say *why*
    there is no usable answer. A partial graph and a failed call are
    never conflated.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    DENIED = "denied"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class Completeness(str, enum.Enum):
    """How much of the *requested* scope the result covers.

    Completeness is relative to the requested environment and scopes.
    It never claims that every extra, platform or optional dependency
    of the ecosystem was considered.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    NONE = "none"


class Representation(str, enum.Enum):
    """How a piece of library code was obtained.

    ``DISASSEMBLY`` is not recovered source. ``DECOMPILED`` is a
    reconstruction, not the original text.
    """

    SOURCE = "source"
    STUB = "stub"
    GENERATED = "generated"
    MAPPED_SOURCE = "mapped-source"
    DISASSEMBLY = "disassembly"
    DECOMPILED = "decompiled"
    MANIFEST = "manifest"
    SIGNATURE = "signature"


@dataclass(frozen=True)
class Package:
    """An ecosystem package identity.

    ``declared_constraint`` is what the manifest or lock states.
    ``resolved_version`` is the version that is actually resolved;
    ``None`` means *unknown*, never "the constraint itself".
    """

    ecosystem: str
    name: str
    declared_constraint: Optional[str] = None
    resolved_version: Optional[str] = None
    scope: str = "runtime"
    source_kind: str = "manifest"
    environment: str = "default"

    def as_dict(self) -> dict:
        return {
            "ecosystem": self.ecosystem,
            "name": self.name,
            "declaredConstraint": self.declared_constraint,
            "resolvedVersion": self.resolved_version,
            "scope": self.scope,
            "sourceKind": self.source_kind,
            "environment": self.environment,
        }


@dataclass(frozen=True)
class PackageInstance:
    """A package identity plus the context that keeps it unique.

    ``instance_id`` incorporates the package identity *and* the
    artifact context, so two versions of one package never collapse
    into a single node.
    """

    instance_id: str
    package: Package
    lock_location: Optional[str] = None
    workspace: Optional[str] = None
    peer_context: Optional[str] = None
    source_path: Optional[str] = None
    alias: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "instanceId": self.instance_id,
            "package": self.package.as_dict(),
            "lockLocation": self.lock_location,
            "workspace": self.workspace,
            "peerContext": self.peer_context,
            "sourcePath": self.source_path,
            "alias": self.alias,
        }


@dataclass(frozen=True)
class DependencyEdge:
    """A directed dependency relation between package instances."""

    source_id: str
    target_id: Optional[str]
    kind: str = "runtime"
    condition: Optional[str] = None
    evidence_ref: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "kind": self.kind,
            "condition": self.condition,
            "evidence": self.evidence_ref,
        }


@dataclass(frozen=True)
class EvidenceReference:
    """Provenance of one fact.

    ``representation`` states what the bytes actually are. A class
    signature is a ``SIGNATURE``, not a ``SOURCE``.
    """

    evidence_id: str
    repository: str = ""
    revision: str = ""
    artifact_hash: Optional[str] = None
    member: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    parser_version: str = ""
    representation: str = Representation.SOURCE.value
    license_policy: Optional[str] = None
    tool_version: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "evidenceId": self.evidence_id,
            "repository": self.repository,
            "revision": self.revision,
            "artifactHash": self.artifact_hash,
            "member": self.member,
            "startLine": self.start_line,
            "endLine": self.end_line,
            "parserVersion": self.parser_version,
            "representation": self.representation,
            "licensePolicy": self.license_policy,
            "toolVersion": self.tool_version,
        }


@dataclass(frozen=True)
class SymbolCard:
    """One searchable symbol of a package.

    ``representation`` states what the symbol was read from, so a
    class signature is never presented as recovered source.
    """

    name: str
    kind: str
    package: str
    evidence_ref: str
    line: Optional[int] = None
    exported: bool = False
    representation: str = Representation.SOURCE.value
    signature: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "package": self.package,
            "evidence": self.evidence_ref,
            "line": self.line,
            "exported": self.exported,
            "representation": self.representation,
            "signature": self.signature,
        }


@dataclass(frozen=True)
class EcosystemSnapshot:
    """Everything one ecosystem adapter could observe offline.

    The snapshot is the unit the graph builder consumes. It is
    deliberately *not* a result: the service turns it into a bounded,
    status-bearing :class:`ResearchResult`.
    """

    ecosystem: str
    instances: tuple[PackageInstance, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    symbols: tuple[SymbolCard, ...] = ()
    warnings: tuple[str, ...] = ()
    completeness: Completeness = Completeness.COMPLETE
    snapshot_id: str = ""
    source_paths: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "ecosystem": self.ecosystem,
            "instances": [item.as_dict() for item in self.instances],
            "edges": [edge.as_dict() for edge in self.edges],
            "evidence": [item.as_dict() for item in self.evidence],
            "symbols": [item.as_dict() for item in self.symbols],
            "warnings": list(self.warnings),
            "completeness": self.completeness.value,
            "snapshotId": self.snapshot_id,
        }


@dataclass(frozen=True)
class ResearchResult:
    """The envelope every research call returns.

    ``status`` describes the operational outcome; ``completeness``
    describes how much of the requested scope is covered. ``truncated``
    is true when a limit stopped the traversal, and ``cursor`` then
    carries the way to continue. The effective ``limits`` are always
    reported so a caller never has to guess what was applied.
    """

    schema_version: int = RESULT_SCHEMA_VERSION
    snapshot_id: str = ""
    status: ResearchStatus = ResearchStatus.COMPLETE
    completeness: Completeness = Completeness.COMPLETE
    operation: str = "dependency.tree"
    nodes: tuple[PackageInstance, ...] = ()
    edges: tuple[DependencyEdge, ...] = ()
    evidence: tuple[EvidenceReference, ...] = ()
    excerpts: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()
    truncated: bool = False
    cursor: Optional[str] = None
    limits: Mapping[str, Any] = field(default_factory=dict)
    scope: Mapping[str, Any] = field(default_factory=dict)
    detail: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in (ResearchStatus.COMPLETE, ResearchStatus.PARTIAL)

    def as_dict(self) -> dict:
        return {
            "schemaVersion": self.schema_version,
            "snapshotId": self.snapshot_id,
            "status": self.status.value,
            "completeness": self.completeness.value,
            "operation": self.operation,
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "evidence": [item.as_dict() for item in self.evidence],
            "excerpts": [dict(excerpt) for excerpt in self.excerpts],
            "warnings": list(self.warnings),
            "truncated": self.truncated,
            "cursor": self.cursor,
            "limits": dict(self.limits),
            "scope": dict(self.scope),
            "detail": dict(self.detail),
        }
