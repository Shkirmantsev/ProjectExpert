"""Offline readers for the supported Python lock formats.

Supported lock files:

``uv.lock``
    uv lockfile version 1 (revision 1, 2 or 3). An unknown ``version``
    is rejected with an actionable diagnostic instead of a guessed
    graph.

``poetry.lock``
    Poetry lock versions 1.1, 2.0 and 2.1.

The readers are pure: they parse bytes that are already on disk. They
never import a package, never run ``pip``/``uv``/``poetry`` and never
touch the network. A declared constraint is not a resolution, and a
marker or an extra is preserved rather than evaluated against the host.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pi_platform.core.research.graph import instance_id
from pi_platform.core.research.records import (
    Completeness,
    DependencyEdge,
    EvidenceReference,
    Package,
    PackageInstance,
)

__all__ = [
    "SUPPORTED_UV_LOCK_VERSIONS",
    "SUPPORTED_POETRY_LOCK_VERSIONS",
    "LockReadError",
    "UnsupportedLockVersion",
    "LockedPackage",
    "LockFile",
    "read_uv_lock",
    "read_poetry_lock",
    "read_lock_file",
    "normalize_python_name",
]


#: uv lockfile versions this reader supports.
SUPPORTED_UV_LOCK_VERSIONS = frozenset({1})
#: uv lockfile revisions this reader supports.
SUPPORTED_UV_LOCK_REVISIONS = frozenset({1, 2, 3})
#: Poetry lock versions this reader supports.
SUPPORTED_POETRY_LOCK_VERSIONS = frozenset({"1.1", "2.0", "2.1"})


class LockReadError(RuntimeError):
    """The lock file could not be read."""


class UnsupportedLockVersion(LockReadError):
    """The lock file uses a format version this reader does not support."""


def normalize_python_name(name: str) -> str:
    """PEP 503 name normalisation."""

    import re

    return re.sub(r"[-_.]+", "-", name).strip().lower()


@dataclass(frozen=True)
class LockedPackage:
    """One package as the lock states it."""

    name: str
    version: Optional[str]
    source_kind: str
    dependencies: tuple[Mapping[str, Any], ...] = ()
    optional_dependencies: Mapping[str, tuple[Mapping[str, Any], ...]] = field(default_factory=dict)
    markers: tuple[str, ...] = ()
    extras: tuple[str, ...] = ()
    groups: tuple[str, ...] = ()
    editable: bool = False
    workspace: Optional[str] = None
    origin: Optional[str] = None
    license: Optional[str] = None
    requires_python: Optional[str] = None


@dataclass(frozen=True)
class LockFile:
    """A parsed lock file."""

    ecosystem: str
    format_name: str
    format_version: str
    packages: tuple[LockedPackage, ...]
    requires_python: Optional[str] = None
    warnings: tuple[str, ...] = ()
    completeness: Completeness = Completeness.COMPLETE

    def by_name(self) -> dict[str, LockedPackage]:
        return {package.name: package for package in self.packages}


def _dependency_entries(entries: Sequence[Any]) -> tuple[Mapping[str, Any], ...]:
    """Normalise the dependency entry shapes of the supported formats."""

    normalised: list[Mapping[str, Any]] = []
    for entry in entries or ():
        if isinstance(entry, str):
            normalised.append({"name": entry})
        elif isinstance(entry, Mapping):
            item = dict(entry)
            name = item.get("name")
            if not isinstance(name, str):
                continue
            extras = item.get("extras")
            marker = item.get("marker")
            normalised.append({
                "name": normalize_python_name(name),
                "extras": tuple(sorted(extras)) if isinstance(extras, list) else (),
                "marker": marker if isinstance(marker, str) else None,
                "version": item.get("version"),
            })
    return tuple(normalised)


def read_uv_lock(path: Path) -> LockFile:
    """Read a ``uv.lock`` file.

    The reader supports uv lockfile version 1. An unknown version is
    rejected: a guessed graph would be worse than an explicit
    diagnostic.
    """

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise LockReadError(f"cannot read uv lock {path}: {exc}") from exc

    version = data.get("version")
    if version not in SUPPORTED_UV_LOCK_VERSIONS:
        raise UnsupportedLockVersion(
            f"unsupported uv.lock version {version!r}; supported: "
            f"{sorted(SUPPORTED_UV_LOCK_VERSIONS)}"
        )
    revision = data.get("revision", 1)
    if revision not in SUPPORTED_UV_LOCK_REVISIONS:
        raise UnsupportedLockVersion(
            f"unsupported uv.lock revision {revision!r}; supported: "
            f"{sorted(SUPPORTED_UV_LOCK_REVISIONS)}"
        )

    warnings: list[str] = []
    packages: list[LockedPackage] = []
    for entry in data.get("package", []) or ():
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        source = entry.get("source") if isinstance(entry.get("source"), Mapping) else {}
        source_kind = "registry"
        editable = False
        workspace: Optional[str] = None
        origin: Optional[str] = None
        if isinstance(source, Mapping):
            if "editable" in source:
                source_kind = "editable"
                editable = True
                origin = str(source.get("editable"))
            elif "virtual" in source:
                source_kind = "virtual"
                origin = str(source.get("virtual"))
            elif "directory" in source:
                source_kind = "directory"
                origin = str(source.get("directory"))
            elif "git" in source:
                source_kind = "git"
                origin = str(source.get("git"))
            elif "registry" in source:
                origin = str(source.get("registry"))
        dependencies = _dependency_entries(entry.get("dependencies"))
        optional: dict[str, tuple[Mapping[str, Any], ...]] = {}
        for extra_name, extra_entries in (entry.get("optional-dependencies") or {}).items():
            optional[str(extra_name)] = _dependency_entries(extra_entries)
        markers = tuple(
            str(item.get("marker"))
            for item in dependencies
            if isinstance(item.get("marker"), str)
        )
        packages.append(LockedPackage(
            name=normalize_python_name(name),
            version=str(entry.get("version")) if entry.get("version") else None,
            source_kind=source_kind,
            dependencies=dependencies,
            optional_dependencies=optional,
            markers=markers,
            editable=editable,
            workspace=origin if editable else None,
            origin=origin,
            license=entry.get("license"),
            requires_python=entry.get("requires-python"),
        ))

    if not packages:
        warnings.append("uv.lock contains no package entries")
    return LockFile(
        ecosystem="python",
        format_name="uv.lock",
        format_version=f"{version}.{revision}",
        packages=tuple(packages),
        requires_python=data.get("requires-python"),
        warnings=tuple(warnings),
    )


def read_poetry_lock(path: Path) -> LockFile:
    """Read a ``poetry.lock`` file.

    The reader supports Poetry lock versions 1.1, 2.0 and 2.1. An
    unknown ``lock-version`` is rejected.
    """

    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        raise LockReadError(f"cannot read poetry lock {path}: {exc}") from exc

    metadata = data.get("metadata") if isinstance(data.get("metadata"), Mapping) else {}
    lock_version = str(metadata.get("lock-version") or "")
    if lock_version not in SUPPORTED_POETRY_LOCK_VERSIONS:
        raise UnsupportedLockVersion(
            f"unsupported poetry.lock lock-version {lock_version!r}; supported: "
            f"{sorted(SUPPORTED_POETRY_LOCK_VERSIONS)}"
        )

    warnings: list[str] = []
    packages: list[LockedPackage] = []
    for entry in data.get("package", []) or ():
        if not isinstance(entry, Mapping):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        dependencies: list[Mapping[str, Any]] = []
        declared = entry.get("dependencies")
        if isinstance(declared, Mapping):
            for dep_name, constraint in declared.items():
                dependencies.append({
                    "name": normalize_python_name(dep_name),
                    "extras": (),
                    "marker": None,
                    "version": str(constraint) if constraint is not None else None,
                })
        optional: dict[str, tuple[Mapping[str, Any], ...]] = {}
        extras_block = entry.get("extras")
        if isinstance(extras_block, Mapping):
            for extra_name, requirements in extras_block.items():
                entries = []
                for requirement in requirements or ():
                    if not isinstance(requirement, str):
                        continue
                    # "name (>=1.0)" and "name" are both valid forms.
                    head = requirement.split(" (", 1)[0].strip()
                    entries.append({
                        "name": normalize_python_name(head),
                        "extras": (),
                        "marker": None,
                        "version": None,
                    })
                optional[str(extra_name)] = tuple(entries)
        markers: list[str] = []
        if isinstance(entry.get("markers"), str):
            markers.append(entry["markers"])
        groups = tuple(
            group for group in (str(entry.get("category") or ""),) if group
        )
        source_kind = "registry"
        origin: Optional[str] = None
        editable = False
        workspace: Optional[str] = None
        source = entry.get("source")
        if isinstance(source, Mapping):
            source_type = str(source.get("type") or "")
            if source_type in {"directory", "file"}:
                source_kind = source_type
                origin = str(source.get("url") or "")
                editable = source_type == "directory"
                workspace = origin
            elif source_type == "git":
                source_kind = "git"
                origin = str(source.get("url") or "")
            elif source_type == "legacy" or source_type == "url":
                origin = str(source.get("url") or "")
        packages.append(LockedPackage(
            name=normalize_python_name(name),
            version=str(entry.get("version")) if entry.get("version") else None,
            source_kind=source_kind,
            dependencies=tuple(dependencies),
            optional_dependencies=optional,
            markers=tuple(markers),
            extras=tuple(sorted(optional)),
            groups=groups,
            editable=editable,
            workspace=workspace,
            origin=origin,
            license=entry.get("license"),
            requires_python=entry.get("python-versions"),
        ))

    if not packages:
        warnings.append("poetry.lock contains no package entries")
    return LockFile(
        ecosystem="python",
        format_name="poetry.lock",
        format_version=lock_version,
        packages=tuple(packages),
        requires_python=metadata.get("python-versions"),
        warnings=tuple(warnings),
    )


def read_lock_file(path: Path) -> LockFile:
    """Read the lock file at ``path``, dispatching on its name."""

    name = path.name.lower()
    if name == "uv.lock":
        return read_uv_lock(path)
    if name == "poetry.lock":
        return read_poetry_lock(path)
    raise UnsupportedLockVersion(f"unsupported lock file name: {path.name!r}")


def lock_instances(lock: LockFile, *, location: str,
                   evidence: EvidenceReference) -> tuple[
                       tuple[PackageInstance, ...], tuple[DependencyEdge, ...]]:
    """Project a parsed lock onto instances and edges.

    The lock location is part of every instance identity, so the same
    package locked by two files stays two nodes.
    """

    instances: list[PackageInstance] = []
    by_name: dict[str, str] = {}
    for package in lock.packages:
        package_record = Package(
            ecosystem=lock.ecosystem,
            name=package.name,
            declared_constraint=package.version,
            resolved_version=package.version,
            scope=package.groups[0] if package.groups else "runtime",
            source_kind=package.source_kind,
            environment="default",
        )
        node_id = instance_id(
            package_record,
            lock_location=location,
            workspace=package.workspace,
        )
        by_name[package.name] = node_id
        instances.append(PackageInstance(
            instance_id=node_id,
            package=package_record,
            lock_location=location,
            workspace=package.workspace,
            source_path=package.origin,
        ))

    edges: list[DependencyEdge] = []
    for package in lock.packages:
        source_id = by_name.get(package.name)
        if source_id is None:
            continue
        for dependency in package.dependencies:
            target_name = dependency.get("name")
            condition = dependency.get("marker")
            extras = dependency.get("extras") or ()
            if extras:
                condition = (condition or "") + (" " if condition else "") + \
                    f"extras={','.join(extras)}"
            edges.append(DependencyEdge(
                source_id=source_id,
                target_id=by_name.get(str(target_name)),
                kind="runtime",
                condition=condition or None,
                evidence_ref=evidence.evidence_id,
            ))
        for extra_name, extra_entries in package.optional_dependencies.items():
            for dependency in extra_entries:
                edges.append(DependencyEdge(
                    source_id=source_id,
                    target_id=by_name.get(str(dependency.get("name"))),
                    kind="optional",
                    condition=f"extra={extra_name}",
                    evidence_ref=evidence.evidence_id,
                ))
    return tuple(instances), tuple(edges)
