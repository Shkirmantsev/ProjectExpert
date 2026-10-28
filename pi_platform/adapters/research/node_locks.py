"""Offline readers for the supported Node lock formats.

Supported formats and their exact versions:

======================  ==========================================================
``package-lock.json``  npm lockfile versions 1, 2 and 3
``pnpm-lock.yaml``     pnpm lockfile versions 6.0 and 9.0
``yarn.lock``          Yarn classic (v1) and Yarn berry (lockfile v2 - v8)
======================  ==========================================================

An unknown lockfile version is rejected with an actionable diagnostic.
A guessed dependency graph is worse than an explicit "not supported".

The readers are pure: they parse bytes that are already on disk. They
never run ``npm``, ``pnpm`` or ``yarn``, never install a package and
never touch the network.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

__all__ = [
    "SUPPORTED_NPM_LOCK_VERSIONS",
    "SUPPORTED_PNPM_LOCK_VERSIONS",
    "SUPPORTED_YARN_BERRY_VERSIONS",
    "NodeLockError",
    "UnsupportedNodeLockVersion",
    "NodeDependency",
    "NodePackage",
    "NodeImporter",
    "NodeLock",
    "read_package_json",
    "read_npm_lock",
    "read_pnpm_lock",
    "read_yarn_lock",
    "read_node_lock",
]


#: npm ``lockfileVersion`` values this reader supports.
SUPPORTED_NPM_LOCK_VERSIONS = frozenset({1, 2, 3})
#: pnpm ``lockfileVersion`` values this reader supports.
SUPPORTED_PNPM_LOCK_VERSIONS = frozenset({"6.0", "9.0"})
#: Yarn berry ``__metadata.version`` values this reader supports.
SUPPORTED_YARN_BERRY_VERSIONS = frozenset(range(2, 9))


class NodeLockError(RuntimeError):
    """The lock file could not be read."""


class UnsupportedNodeLockVersion(NodeLockError):
    """The lock file uses a format version this reader does not support."""


@dataclass(frozen=True)
class NodeDependency:
    """One dependency edge declared by a package or importer."""

    name: str
    specifier: Optional[str] = None
    scope: str = "runtime"
    optional: bool = False


@dataclass(frozen=True)
class NodePackage:
    """One resolved package in a Node lock."""

    name: str
    version: Optional[str] = None
    specifier: Optional[str] = None
    requested_as: Optional[str] = None
    scope: str = "runtime"
    workspace: Optional[str] = None
    requested_as: Optional[str] = None
    source_kind: str = "registry"
    dependencies: tuple[NodeDependency, ...] = ()
    peer_dependencies: tuple[NodeDependency, ...] = ()
    optional_dependencies: tuple[NodeDependency, ...] = ()
    resolved: Optional[str] = None
    integrity: Optional[str] = None
    location: Optional[str] = None


@dataclass(frozen=True)
class NodeImporter:
    """A project in the workspace and the dependencies it declares."""

    path: str
    name: Optional[str] = None
    version: Optional[str] = None
    dependencies: tuple[NodeDependency, ...] = ()
    dev_dependencies: tuple[NodeDependency, ...] = ()
    optional_dependencies: tuple[NodeDependency, ...] = ()
    peer_dependencies: tuple[NodeDependency, ...] = ()


@dataclass(frozen=True)
class NodeLock:
    """A parsed Node lock file."""

    format_name: str
    format_version: str
    packages: tuple[NodePackage, ...] = ()
    importers: tuple[NodeImporter, ...] = ()
    warnings: tuple[str, ...] = ()
    requires_yaml: bool = False

    def by_name(self) -> dict[str, list[NodePackage]]:
        grouped: dict[str, list[NodePackage]] = {}
        for package in self.packages:
            grouped.setdefault(package.name, []).append(package)
        return grouped


def _alias(name: str, specifier: Optional[str]) -> tuple[str, Optional[str]]:
    """Resolve an npm alias (``npm:other@^1``) to the real package name."""

    if specifier and specifier.startswith("npm:"):
        target = specifier[4:]
        real = target.rsplit("@", 1)[0] if "@" in target[1:] else target
        return real, name
    return name, None


def _specifier_version(specifier: Optional[str]) -> Optional[str]:
    """Return the exact version of an exact pin, if it is one."""

    if not specifier:
        return None
    match = re.fullmatch(r"(?:npm:)?@?[^@/]+@(\d[^@\s]*)", specifier.strip())
    if match:
        return match.group(1)
    match = re.fullmatch(r"(\d[^@\s]*)", specifier.strip())
    return match.group(1) if match else None


def read_package_json(path: Path) -> dict:
    """Read a ``package.json`` manifest."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NodeLockError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise NodeLockError(f"{path} is not a JSON object")
    return data


def _manifest_dependencies(manifest: Mapping[str, Any]) -> tuple[
        NodeDependency, ...]:
    """Read the declared dependencies of a ``package.json``."""

    found: list[NodeDependency] = []
    for field, scope in (("dependencies", "runtime"),
                          ("devDependencies", "dev"),
                          ("optionalDependencies", "optional"),
                          ("peerDependencies", "peer")):
        block = manifest.get(field)
        if not isinstance(block, Mapping):
            continue
        for name, specifier in block.items():
            found.append(NodeDependency(
                name=str(name),
                specifier=str(specifier) if specifier is not None else None,
                scope=scope,
                optional=scope == "optional",
            ))
    return tuple(found)


def _workspace_names(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    workspaces = manifest.get("workspaces")
    if isinstance(workspaces, list):
        return tuple(str(item) for item in workspaces)
    if isinstance(workspaces, Mapping):
        packages = workspaces.get("packages")
        if isinstance(packages, list):
            return tuple(str(item) for item in packages)
    return ()


def read_npm_lock(path: Path) -> NodeLock:
    """Read an npm ``package-lock.json`` (lockfile versions 1, 2 and 3)."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NodeLockError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise NodeLockError(f"{path} is not a JSON object")

    version = data.get("lockfileVersion")
    if version not in SUPPORTED_NPM_LOCK_VERSIONS:
        raise UnsupportedNodeLockVersion(
            f"unsupported npm lockfileVersion {version!r}; supported: "
            f"{sorted(SUPPORTED_NPM_LOCK_VERSIONS)}"
        )

    warnings: list[str] = []
    packages: list[NodePackage] = []
    importers: list[NodeImporter] = []

    if version in (2, 3):
        block = data.get("packages")
        if not isinstance(block, Mapping):
            raise NodeLockError("npm lockfileVersion >= 2 requires a 'packages' block")
        for location in sorted(block):
            entry = block[location]
            if not isinstance(entry, Mapping):
                continue
            if location == "":
                importers.append(NodeImporter(
                    path=".",
                    name=entry.get("name"),
                    version=entry.get("version"),
                    dependencies=_manifest_dependencies(entry),
                ))
                continue
            name = entry.get("name")
            requested_as: Optional[str] = None
            derived = _name_from_location(location)
            if not isinstance(name, str):
                name = derived
            elif derived and derived != name:
                # An npm alias installs the real package under the
                # requested name; both identities are kept.
                requested_as = derived
            if name is None:
                continue
            if entry.get("link"):
                # A workspace link: the real package lives elsewhere.
                importers.append(NodeImporter(
                    path=location,
                    name=name,
                    version=entry.get("version"),
                    dependencies=_manifest_dependencies(entry),
                ))
                continue
            dependencies = tuple(
                NodeDependency(name=str(dep), specifier=str(spec) if spec is not None else None,
                               scope="runtime")
                for dep, spec in (entry.get("dependencies") or {}).items()
            )
            optional = tuple(
                NodeDependency(name=str(dep), specifier=str(spec) if spec is not None else None,
                               scope="optional", optional=True)
                for dep, spec in (entry.get("optionalDependencies") or {}).items()
            )
            peers = tuple(
                NodeDependency(name=str(dep), specifier=str(spec) if spec is not None else None,
                               scope="peer")
                for dep, spec in (entry.get("peerDependencies") or {}).items()
            )
            packages.append(NodePackage(
                name=name,
                version=str(entry.get("version")) if entry.get("version") else None,
                scope="runtime",
                requested_as=requested_as,
                source_kind="registry",
                dependencies=dependencies,
                optional_dependencies=optional,
                peer_dependencies=peers,
                resolved=entry.get("resolved"),
                integrity=entry.get("integrity"),
                location=location,
            ))
    else:
        # lockfileVersion 1 keeps the tree in a nested "dependencies" map.
        root = data.get("dependencies")
        if not isinstance(root, Mapping):
            root = {}
        importers.append(NodeImporter(
            path=".",
            name=data.get("name"),
            version=data.get("version"),
            dependencies=_manifest_dependencies(data),
        ))
        packages.extend(_npm_v1_packages(root, location="node_modules"))

    return NodeLock(
        format_name="package-lock.json",
        format_version=str(version),
        packages=tuple(packages),
        importers=tuple(importers),
        warnings=tuple(warnings),
    )


def _name_from_location(location: str) -> Optional[str]:
    """Derive the package name from a ``node_modules`` path."""

    if "node_modules/" not in location:
        return None
    tail = location.rsplit("node_modules/", 1)[1]
    if not tail:
        return None
    parts = tail.split("/")
    if tail.startswith("@"):
        return "/".join(parts[:2]) if len(parts) >= 2 else tail
    return parts[0]


def _npm_v1_packages(block: Mapping[str, Any], *, location: str) -> list[NodePackage]:
    packages: list[NodePackage] = []
    for name in sorted(block):
        entry = block[name]
        if not isinstance(entry, Mapping):
            continue
        requires = entry.get("requires")
        dependencies = tuple(
            NodeDependency(name=str(dep), specifier=str(spec) if spec is not None else None,
                           scope="runtime")
            for dep, spec in (requires or {}).items()
        )
        packages.append(NodePackage(
            name=str(name),
            version=str(entry.get("version")) if entry.get("version") else None,
            scope="runtime",
            source_kind="registry",
            dependencies=dependencies,
            resolved=entry.get("resolved"),
            integrity=entry.get("integrity"),
            location=location,
        ))
        nested = entry.get("dependencies")
        if isinstance(nested, Mapping):
            packages.extend(_npm_v1_packages(
                nested, location=f"{location}/{name}/node_modules"))
    return packages


def read_pnpm_lock(path: Path) -> NodeLock:
    """Read a ``pnpm-lock.yaml`` (lockfile versions 6.0 and 9.0).

    The reader needs a YAML parser. When none is installed the caller
    receives an explicit "unsupported" diagnostic instead of a crash:
    a missing optional parser must never break the deployment.
    """

    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise UnsupportedNodeLockVersion(
            "reading pnpm-lock.yaml requires a YAML parser (install the "
            "'yaml' extra); no dependency graph was guessed"
        ) from exc

    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, Exception) as exc:  # noqa: BLE001
        raise NodeLockError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise NodeLockError(f"{path} is not a YAML mapping")

    version = str(data.get("lockfileVersion") or "")
    if version not in SUPPORTED_PNPM_LOCK_VERSIONS:
        raise UnsupportedNodeLockVersion(
            f"unsupported pnpm lockfileVersion {version!r}; supported: "
            f"{sorted(SUPPORTED_PNPM_LOCK_VERSIONS)}"
        )

    warnings: list[str] = []
    packages: list[NodePackage] = []
    importers: list[NodeImporter] = []

    importers_block = data.get("importers")
    if isinstance(importers_block, Mapping):
        for location in sorted(importers_block):
            entry = importers_block[location]
            if not isinstance(entry, Mapping):
                continue
            importers.append(_pnpm_importer(str(location), entry))

    packages_block = data.get("packages")
    snapshots_block = data.get("snapshots")
    if not isinstance(packages_block, Mapping):
        packages_block = {}
    if not isinstance(snapshots_block, Mapping):
        snapshots_block = {}

    resolved_versions: dict[str, str] = {}
    for key in sorted(set(packages_block) | set(snapshots_block)):
        name, version = _split_pnpm_key(str(key))
        if name is None:
            continue
        if version:
            resolved_versions[f"{name}@{version}"] = version
        entry = packages_block.get(key) if isinstance(packages_block.get(key), Mapping) else {}
        snapshot = snapshots_block.get(key) if isinstance(snapshots_block.get(key), Mapping) else {}
        merged: dict[str, Any] = {**entry, **snapshot}
        dependencies = _pnpm_dependencies(merged.get("dependencies"))
        optional = _pnpm_dependencies(merged.get("optionalDependencies"))
        peers = _pnpm_dependencies(merged.get("peerDependencies"))
        resolution = merged.get("resolution")
        integrity = None
        resolved = None
        if isinstance(resolution, Mapping):
            integrity = resolution.get("integrity")
            tarball = resolution.get("tarball")
            if isinstance(tarball, str):
                resolved = tarball
        packages.append(NodePackage(
            name=name,
            version=version,
            scope="runtime",
            source_kind="registry",
            dependencies=dependencies,
            optional_dependencies=optional,
            peer_dependencies=peers,
            resolved=resolved,
            integrity=integrity,
            location=str(key),
        ))

    return NodeLock(
        format_name="pnpm-lock.yaml",
        format_version=version,
        packages=tuple(packages),
        importers=tuple(importers),
        warnings=tuple(warnings),
        requires_yaml=True,
    )


def _split_pnpm_key(key: str) -> tuple[Optional[str], Optional[str]]:
    """Split a pnpm package key into its name and version."""

    if key.startswith("/"):
        key = key[1:]
    if "@" not in key:
        return None, None
    name, _, version = key.rpartition("@")
    if not name:
        return None, None
    if version.startswith("npm:"):
        version = version[4:]
    if "(" in version:
        version = version.split("(", 1)[0]
    return name, version or None


def _pnpm_importer(location: str, entry: Mapping[str, Any]) -> NodeImporter:
    def read(field_name: str, scope: str) -> tuple[NodeDependency, ...]:
        block = entry.get(field_name)
        if not isinstance(block, Mapping):
            return ()
        found: list[NodeDependency] = []
        for name, spec in block.items():
            if isinstance(spec, Mapping):
                specifier = spec.get("specifier")
                version = spec.get("version")
                found.append(NodeDependency(
                    name=str(name),
                    specifier=str(specifier) if specifier is not None
                    else (str(version) if version is not None else None),
                    scope=scope,
                    optional=scope == "optional",
                ))
            else:
                found.append(NodeDependency(name=str(name),
                                           specifier=str(spec) if spec else None,
                                           scope=scope,
                                           optional=scope == "optional"))
        return tuple(found)

    return NodeImporter(
        path=location,
        dependencies=read("dependencies", "runtime"),
        dev_dependencies=read("devDependencies", "dev"),
        optional_dependencies=read("optionalDependencies", "optional"),
    )


def _pnpm_dependencies(block: Any) -> tuple[NodeDependency, ...]:
    if not isinstance(block, Mapping):
        return ()
    found: list[NodeDependency] = []
    for name, spec in block.items():
        if isinstance(spec, Mapping):
            specifier = spec.get("specifier") or spec.get("version")
            found.append(NodeDependency(name=str(name),
                                       specifier=str(specifier) if specifier else None))
        else:
            found.append(NodeDependency(name=str(name),
                                       specifier=str(spec) if spec else None))
    return tuple(found)


_YARN_CLASSIC_HEADER = re.compile(r"^# yarn lockfile v(\d+)", re.MULTILINE)
_YARN_CLASSIC_ENTRY = re.compile(r"^(\S.*):\s*$")
_YARN_CLASSIC_FIELD = re.compile(r'^  ("?[^"\s]+"?)\s+(".*"|[^"\s]+)$')


def read_yarn_lock(path: Path) -> NodeLock:
    """Read a ``yarn.lock``.

    Yarn classic (v1) and Yarn berry (lockfile metadata v2 - v8) are
    supported. The classic format is parsed directly; the berry format
    is YAML and needs the optional YAML parser.
    """

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise NodeLockError(f"cannot read {path}: {exc}") from exc

    header = _YARN_CLASSIC_HEADER.search(text)
    if header:
        return _read_yarn_classic(text, path)
    if "__metadata:" in text:
        return _read_yarn_berry(text, path)
    raise UnsupportedNodeLockVersion(
        f"cannot determine the yarn.lock format of {path.name}; supported: "
        "yarn classic v1 and yarn berry lockfile v2-v8"
    )


def _read_yarn_classic(text: str, path: Path) -> NodeLock:
    packages: list[NodePackage] = []
    current: Optional[dict[str, Any]] = None
    section: Optional[str] = None

    def flush() -> None:
        if current is None:
            return
        name, _ = _split_yarn_spec(str(current["spec"]))
        # The entry key states the requested range; the "version" field
        # states the resolved version.
        version = current.get("version") or None
        dependencies = tuple(
            NodeDependency(name=dep_name, specifier=dep_spec)
            for dep_name, dep_spec in current.get("dependencies", {}).items()
        )
        packages.append(NodePackage(
            name=name,
            version=version,
            specifier=str(current["spec"]),
            scope="runtime",
            source_kind="registry",
            dependencies=dependencies,
            resolved=current.get("resolved"),
            integrity=current.get("integrity"),
            location=str(path.name),
        ))

    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if not raw.startswith(" "):
            flush()
            match = _YARN_CLASSIC_ENTRY.match(raw)
            if not match:
                current = None
                continue
            current = {"spec": match.group(1).strip('"'), "dependencies": {}}
            section = None
            continue
        if current is None:
            continue
        stripped = raw.strip()
        if stripped.startswith("dependencies:"):
            section = "dependencies"
            continue
        if section == "dependencies":
            if ":" in stripped:
                dep_name, _, dep_spec = stripped.partition(":")
                current["dependencies"][dep_name.strip().strip('"')] = \
                    dep_spec.strip().strip('"')
                continue
            section = None
        field_match = _YARN_CLASSIC_FIELD.match(raw)
        if field_match:
            current[field_match.group(1).strip('"')] = field_match.group(2).strip('"')
    flush()

    return NodeLock(
        format_name="yarn.lock",
        format_version="1",
        packages=tuple(packages),
        importers=(),
    )


def _split_yarn_spec(spec: str) -> tuple[str, Optional[str]]:
    """Split a yarn classic spec into its package name and version."""

    for separator in ("@npm:"):
        if separator in spec:
            name, _, version = spec.partition(separator)
            return name.strip().strip('"'), version.strip().strip('"') or None
    at = spec.rfind("@")
    if at > 0:
        return spec[:at], spec[at + 1:] or None
    return spec, None


def _read_yarn_berry(text: str, path: Path) -> NodeLock:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on the host
        raise UnsupportedNodeLockVersion(
            "reading a Yarn berry lockfile requires a YAML parser (install the "
            "'yaml' extra); no dependency graph was guessed"
        ) from exc

    try:
        data = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001
        raise NodeLockError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, Mapping):
        raise NodeLockError(f"{path} is not a YAML mapping")

    metadata = data.get("__metadata")
    if not isinstance(metadata, Mapping):
        raise NodeLockError("yarn berry lockfile has no __metadata block")
    version = int(metadata.get("version") or 0)
    if version not in SUPPORTED_YARN_BERRY_VERSIONS:
        raise UnsupportedNodeLockVersion(
            f"unsupported yarn berry lockfile version {version}; supported: "
            f"{sorted(SUPPORTED_YARN_BERRY_VERSIONS)}"
        )

    packages: list[NodePackage] = []
    for key in sorted(data):
        if key == "__metadata":
            continue
        entry = data[key]
        if not isinstance(entry, Mapping):
            continue
        name, version_text = _split_yarn_berry_key(str(key))
        if name is None:
            continue
        dependencies = tuple(
            NodeDependency(name=str(dep_name), specifier=str(spec) if spec is not None else None)
            for dep_name, spec in (entry.get("dependencies") or {}).items()
        )
        peers = tuple(
            NodeDependency(name=str(dep_name), specifier=str(spec) if spec is not None else None,
                           scope="peer")
            for dep_name, spec in (entry.get("peerDependencies") or {}).items()
        )
        resolution = entry.get("resolution")
        packages.append(NodePackage(
            name=name,
            version=version_text,
            specifier=str(key),
            scope="runtime",
            source_kind="registry",
            dependencies=dependencies,
            peer_dependencies=peers,
            resolved=str(resolution) if resolution is not None else None,
            integrity=entry.get("checksum"),
            location=str(path.name),
        ))

    return NodeLock(
        format_name="yarn.lock",
        format_version=f"berry-{version}",
        packages=tuple(packages),
        importers=(),
        requires_yaml=True,
    )


def _split_yarn_berry_key(key: str) -> tuple[Optional[str], Optional[str]]:
    """Split a yarn berry key such as ``lodash@npm:4.17.21``."""

    at = key.find("@", 1)
    if at <= 0:
        return None, None
    name = key[:at]
    rest = key[at + 1:]
    if rest.startswith("npm:"):
        rest = rest[4:]
    version = rest.split(":", 1)[1] if ":" in rest else None
    return name, version


def read_node_lock(path: Path) -> NodeLock:
    """Read the lock file at ``path``, dispatching on its name."""

    name = path.name.lower()
    if name == "package-lock.json":
        return read_npm_lock(path)
    if name == "pnpm-lock.yaml":
        return read_pnpm_lock(path)
    if name == "yarn.lock":
        return read_yarn_lock(path)
    raise UnsupportedNodeLockVersion(f"unsupported lock file name: {path.name!r}")
