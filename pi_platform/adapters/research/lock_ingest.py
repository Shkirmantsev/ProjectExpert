"""Ingestion adapters for the dependency lock and manifest families.

These adapters make the lock evidence **searchable**: the resolved
packages of a project become canonical dependency entities with
``DEPENDS_ON`` relations, so a query about "which version of X does
this project use" is answered from the corpus instead of from a
research call.

The adapters reuse the parsers of the research service, so the corpus
and the research answer never disagree about a lock file.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pi_platform.adapters.research.node_locks import (
    NodeLock,
    NodeLockError,
    UnsupportedNodeLockVersion,
    read_node_lock,
    read_package_json,
)
from pi_platform.adapters.research.python_locks import (
    LockFile,
    LockReadError,
    UnsupportedLockVersion,
    read_lock_file,
)
from pi_platform.core.canonical.content_address import content_address
from pi_platform.core.canonical.value_types import (
    Entity,
    Evidence,
    KnowledgeState,
    Relation,
)
from pi_platform.core.ingest.records import document_result
from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterError,
    SourceAdapterPort,
    SourceContentFamily,
)

__all__ = [
    "PythonLockAdapter",
    "NodeManifestAdapter",
    "NodeLockAdapter",
    "PYTHON_LOCK_PARSER_VERSION",
    "NODE_PARSER_VERSION",
]

PYTHON_LOCK_PARSER_VERSION = "python-lock-1"
NODE_PARSER_VERSION = "node-lock-1"


def _dependency_result(source, rows, *, language: str, parser_version: str,
                       packages: Sequence[Mapping[str, Any]],
                       dependency_relations: Sequence[tuple[str, str]],
                       rationale: Optional[str] = None):
    """Build a canonical result from resolved packages."""

    result = document_result(source, rows, language, parser_version,
                             rationale=rationale)
    entities: list[Entity] = []
    relations: list[Relation] = []
    evidence: list[Evidence] = []
    ids: dict[str, str] = {}
    for package in packages:
        eid = content_address({
            "source": source.id, "hash": source.contentHash,
            "family": "Dependency", "name": package["name"],
            "version": package.get("version"),
        })
        ids[str(package["name"])] = eid
        meta = replace(result.document.metadata, extensions={
            **dict(package), "pi_evidence": {
                "knowledgeState": KnowledgeState.VERIFIED.value,
                "parserVersion": parser_version,
                "sourceHash": source.contentHash,
            }})
        entities.append(Entity(eid, "Dependency", str(package["name"]),
                                metadata=meta,
                                knowledgeState=KnowledgeState.VERIFIED))
        evidence.append(Evidence(KnowledgeState.VERIFIED, parser_version,
                                 source.contentHash))
    for source_name, target_name in dependency_relations:
        if source_name not in ids or target_name not in ids:
            continue
        relations.append(Relation(ids[source_name], ids[target_name],
                                  "DEPENDS_ON", evidence=(evidence[-1],),
                                  knowledgeState=KnowledgeState.VERIFIED))
    return replace(result, entities=tuple(entities), relations=tuple(relations),
                   evidence=tuple(evidence))


class PythonLockAdapter(SourceAdapterPort):
    """Read a ``uv.lock`` or ``poetry.lock`` into canonical dependencies."""

    family = SourceContentFamily.PYTHON_LOCK

    def parse(self, source, context=None):
        path = Path(source.uri)
        try:
            lock = read_lock_file(path)
        except UnsupportedLockVersion as exc:
            raise SourceAdapterError(str(exc)) from exc
        except LockReadError as exc:
            raise SourceAdapterError(str(exc)) from exc
        packages: list[dict[str, Any]] = []
        relations: list[tuple[str, str]] = []
        rows: list[tuple[str, int, str, dict]] = []
        for package in lock.packages:
            packages.append({
                "ecosystem": "python",
                "name": package.name,
                "version": package.version,
                "sourceKind": package.source_kind,
                "scope": package.groups[0] if package.groups else "runtime",
                "lockFormat": lock.format_name,
                "lockVersion": lock.format_version,
                "resolved": True,
            })
            rows.append((package.name, 2,
                         f"{package.name} {package.version or 'unresolved'} "
                         f"({package.source_kind})",
                         {"ecosystem": "python", "version": package.version}))
            for dependency in package.dependencies:
                relations.append((package.name, str(dependency.get("name"))))
        return _dependency_result(source, rows, language="python",
                                  parser_version=PYTHON_LOCK_PARSER_VERSION,
                                  packages=packages,
                                  dependency_relations=relations,
                                  rationale="; ".join(lock.warnings) or None)


class NodeManifestAdapter(SourceAdapterPort):
    """Read a ``package.json`` into canonical dependencies."""

    family = SourceContentFamily.NODE_MANIFEST

    def parse(self, source, context=None):
        path = Path(source.uri)
        try:
            manifest = read_package_json(path)
        except NodeLockError as exc:
            raise SourceAdapterError(str(exc)) from exc
        packages: list[dict[str, Any]] = []
        rows: list[tuple[str, int, str, dict]] = []
        for field, scope in (("dependencies", "runtime"),
                             ("devDependencies", "dev"),
                             ("optionalDependencies", "optional"),
                             ("peerDependencies", "peer")):
            block = manifest.get(field)
            if not isinstance(block, Mapping):
                continue
            for name, specifier in block.items():
                packages.append({
                    "ecosystem": "node",
                    "name": str(name),
                    "version": None,
                    "declaredConstraint": str(specifier) if specifier is not None else None,
                    "scope": scope,
                    "sourceKind": "declaration",
                    "resolved": False,
                })
                rows.append((str(name), 2,
                             f"{name} {specifier} ({scope})",
                             {"ecosystem": "node", "scope": scope}))
        return _dependency_result(source, rows, language="node",
                                  parser_version=NODE_PARSER_VERSION,
                                  packages=packages, dependency_relations=[],
                                  rationale=None)


class NodeLockAdapter(SourceAdapterPort):
    """Read a Node lock file into canonical dependencies."""

    family = SourceContentFamily.NODE_LOCK

    def parse(self, source, context=None):
        path = Path(source.uri)
        try:
            lock = read_node_lock(path)
        except UnsupportedNodeLockVersion as exc:
            raise SourceAdapterError(str(exc)) from exc
        except NodeLockError as exc:
            raise SourceAdapterError(str(exc)) from exc
        packages: list[dict[str, Any]] = []
        relations: list[tuple[str, str]] = []
        rows: list[tuple[str, int, str, dict]] = []
        for package in lock.packages:
            packages.append({
                "ecosystem": "node",
                "name": package.name,
                "version": package.version,
                "declaredConstraint": package.specifier,
                "scope": package.scope,
                "sourceKind": package.source_kind,
                "lockFormat": lock.format_name,
                "lockVersion": lock.format_version,
                "resolved": True,
            })
            rows.append((package.name, 2,
                         f"{package.name} {package.version or 'unresolved'}",
                         {"ecosystem": "node", "version": package.version}))
            for dependency in package.dependencies:
                relations.append((package.name, dependency.name))
        for importer in lock.importers:
            for dependency in importer.dependencies:
                relations.append((importer.name or importer.path, dependency.name))
        return _dependency_result(source, rows, language="node",
                                  parser_version=NODE_PARSER_VERSION,
                                  packages=packages,
                                  dependency_relations=relations,
                                  rationale="; ".join(lock.warnings) or None)
