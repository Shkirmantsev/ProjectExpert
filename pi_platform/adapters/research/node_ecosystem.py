"""The Node ecosystem adapter.

It combines the *declaration* (``package.json``) with the *resolution*
(``package-lock.json`` / ``pnpm-lock.yaml`` / ``yarn.lock``) and, when
the static parser is installed, the *symbols* of the workspace source
files.

A workspace is a set of importers, so the same package can appear with
different versions in different workspaces. The adapter keeps those
apart instead of collapsing them, and it resolves an edge with the npm
node_modules resolution rule so a nested version wins over the
top-level one.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from pi_platform.adapters.research.node_locks import (
    NodeDependency,
    NodeImporter,
    NodeLock,
    NodeLockError,
    NodePackage,
    UnsupportedNodeLockVersion,
    _manifest_dependencies,
    read_node_lock,
    read_package_json,
)
from pi_platform.adapters.research.node_sources import (
    NodeSourceAnalysis,
    analyse_source,
    parser_status,
)
from pi_platform.core.canonical.content_address import content_address, content_address_bytes
from pi_platform.core.research.graph import instance_id
from pi_platform.core.research.records import (
    Completeness,
    DependencyEdge,
    EvidenceReference,
    EcosystemSnapshot,
    Package,
    PackageInstance,
    SymbolCard,
)
from pi_platform.ports.research.ecosystem import EcosystemResearchPort

__all__ = ["PARSER_VERSION", "NodeEcosystemAdapter"]

PARSER_VERSION = "node-research-1"

_LOCK_NAMES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock")
_SOURCE_SUFFIXES = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts")


@dataclass(frozen=True)
class _Manifest:
    path: Path
    name: Optional[str]
    version: Optional[str]
    dependencies: tuple[NodeDependency, ...]


@dataclass
class _Projection:
    """The instances and edges of one lock, plus the resolution index."""

    instances: list[PackageInstance]
    edges: list[DependencyEdge]
    by_name: dict[str, list[str]]
    by_location: dict[str, str]
    warnings: list[str]


def _nearest_directory(directories: Sequence[Path], source: Path) -> Optional[Path]:
    """Return the manifest directory that owns ``source``."""

    resolved = source.resolve()
    best: Optional[Path] = None
    for directory in directories:
        try:
            resolved.relative_to(directory.resolve())
        except ValueError:
            continue
        if best is None or len(directory.parts) > len(best.parts):
            best = directory
    return best


class NodeEcosystemAdapter(EcosystemResearchPort):
    """Offline Node dependency evidence."""

    ecosystem = "node"

    def __init__(self, *, include_sources: bool = True) -> None:
        self.include_sources = include_sources

    # -- port ----------------------------------------------------------------

    def detect(self, project_root: Path) -> bool:
        root = Path(project_root)
        if (root / "package.json").is_file():
            return True
        return any((root / name).is_file() for name in _LOCK_NAMES)

    def collect(self, project_root: Path, *, environment: str = "default",
                scopes: Sequence[str] = ()) -> EcosystemSnapshot:
        root = Path(project_root)
        warnings: list[str] = []
        instances: list[PackageInstance] = []
        edges: list[DependencyEdge] = []
        evidence: list[EvidenceReference] = []
        source_paths: list[str] = []
        symbols_found: list[SymbolCard] = []
        completeness = Completeness.COMPLETE

        manifests = self._read_manifests(root, evidence, source_paths, warnings)
        lock, lock_path = self._read_lock(root, warnings)

        lock_evidence: Optional[EvidenceReference] = None
        if lock is not None and lock_path is not None:
            lock_evidence = EvidenceReference(
                evidence_id=content_address({
                    "kind": "lock", "path": str(lock_path),
                    "hash": content_address_bytes(lock_path.read_bytes()),
                }),
                repository=str(root),
                revision="",
                artifact_hash=content_address_bytes(lock_path.read_bytes()),
                member=lock_path.name,
                parser_version=PARSER_VERSION,
                representation="manifest",
            )
            evidence.append(lock_evidence)
            source_paths.append(str(lock_path))
            warnings.extend(lock.warnings)
        else:
            completeness = Completeness.PARTIAL

        projection = self._project_packages(lock, lock_evidence, lock_path)
        instances.extend(projection.instances)
        edges.extend(projection.edges)
        warnings.extend(projection.warnings)

        importer_nodes, importer_edges = self._project_importers(
            lock, manifests, lock_evidence, projection, root)
        instances.extend(importer_nodes)
        edges.extend(importer_edges)

        if self.include_sources:
            source_warnings, symbols = self._collect_sources(
                root, manifests, evidence, source_paths)
            warnings.extend(source_warnings)
            symbols_found.extend(symbols)

        # The snapshot identity is bound to the *content* of the observed
        # files, not only to their paths: a changed lock is a changed
        # snapshot and an old cursor must not continue it.
        snapshot_id = content_address({
            "ecosystem": self.ecosystem,
            "evidence": sorted(item.evidence_id for item in evidence),
            "parser": PARSER_VERSION,
        })

        return EcosystemSnapshot(
            ecosystem=self.ecosystem,
            instances=tuple(instances),
            edges=tuple(edges),
            evidence=tuple(evidence),
            symbols=tuple(symbols_found),
            warnings=tuple(warnings),
            completeness=completeness,
            snapshot_id=snapshot_id,
            source_paths=tuple(source_paths),
        )

    # -- helpers -------------------------------------------------------------

    def _read_manifests(self, root: Path, evidence: list[EvidenceReference],
                         source_paths: list[str],
                         warnings: list[str]) -> tuple[_Manifest, ...]:
        manifests: list[_Manifest] = []
        candidates = [root / "package.json"]
        for pattern in ("packages/*/package.json", "apps/*/package.json",
                        "libs/*/package.json"):
            candidates.extend(sorted(root.glob(pattern)))
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                data = read_package_json(candidate)
            except NodeLockError as exc:
                warnings.append(str(exc))
                continue
            raw = candidate.read_bytes()
            source_paths.append(str(candidate))
            evidence.append(EvidenceReference(
                evidence_id=content_address({
                    "kind": "manifest", "path": str(candidate),
                    "hash": content_address_bytes(raw),
                }),
                repository=str(root),
                revision="",
                artifact_hash=content_address_bytes(raw),
                member=candidate.name,
                parser_version=PARSER_VERSION,
                representation="manifest",
            ))
            manifests.append(_Manifest(
                path=candidate,
                name=data.get("name"),
                version=data.get("version"),
                dependencies=_manifest_dependencies(data),
            ))
        return tuple(manifests)

    def _read_lock(self, root: Path,
                   warnings: list[str]) -> tuple[Optional[NodeLock], Optional[Path]]:
        for name in _LOCK_NAMES:
            candidate = root / name
            if not candidate.is_file():
                continue
            try:
                return read_node_lock(candidate), candidate
            except UnsupportedNodeLockVersion as exc:
                warnings.append(f"unsupported lock format: {exc}")
            except NodeLockError as exc:
                warnings.append(f"lock file could not be read: {exc}")
            return None, candidate
        return None, None

    def _project_packages(self, lock: Optional[NodeLock],
                          lock_evidence: Optional[EvidenceReference],
                          lock_path: Optional[Path]) -> _Projection:
        projection = _Projection(instances=[], edges=[], by_name={},
                                 by_location={}, warnings=[])
        if lock is None:
            return projection
        location = str(lock_path) if lock_path else None
        for package in lock.packages:
            package_record = Package(
                ecosystem=self.ecosystem,
                name=package.name,
                declared_constraint=package.specifier,
                resolved_version=package.version,
                scope=package.scope,
                source_kind=package.source_kind,
                environment="default",
            )
            node_id = instance_id(
                package_record,
                lock_location=location,
                workspace=package.workspace,
            )
            projection.instances.append(PackageInstance(
                instance_id=node_id,
                package=package_record,
                lock_location=location,
                workspace=package.workspace,
                source_path=package.location,
                alias=package.requested_as,
            ))
            projection.by_name.setdefault(package.name, []).append(node_id)
            if package.requested_as:
                # An alias is reachable under the requested name too.
                projection.by_name.setdefault(package.requested_as, []).append(node_id)
            if package.location:
                projection.by_location[package.location] = node_id

        for package in lock.packages:
            source_id = projection.by_name.get(package.name, [None])[0]
            if source_id is None:
                continue
            for dependency in (package.dependencies + package.optional_dependencies
                               + package.peer_dependencies):
                target = self._resolve_target(projection, package, dependency)
                if target is None and dependency.name in projection.by_name:
                    projection.warnings.append(
                        f"{package.name} declares {dependency.name} but the lock "
                        "holds several versions of it; the edge stays unresolved"
                    )
                projection.edges.append(DependencyEdge(
                    source_id=source_id,
                    target_id=target,
                    kind=dependency.scope,
                    condition=dependency.specifier,
                    evidence_ref=lock_evidence.evidence_id if lock_evidence else None,
                ))
        return projection

    @staticmethod
    def _resolve_target(projection: _Projection, package: NodePackage,
                         dependency: NodeDependency) -> Optional[str]:
        """Resolve a declared dependency onto a resolved instance.

        The npm resolution rule applies: a nested ``node_modules`` entry
        of the depending package wins over the top-level one, so two
        versions of the same package never collapse.
        """

        if package.location:
            prefix = package.location
            candidate = f"{prefix}/node_modules/{dependency.name}"
            if candidate in projection.by_location:
                return projection.by_location[candidate]
        candidates = projection.by_name.get(dependency.name, [])
        if not candidates:
            return None
        pinned = dependency.specifier
        if pinned:
            exact = pinned.strip().lstrip("^~>=< ")
            if exact.startswith("npm:"):
                exact = exact[4:].rsplit("@", 1)[-1]
            for node in candidates:
                instance = next((item for item in projection.instances
                                 if item.instance_id == node), None)
                if instance is not None and instance.package.resolved_version == exact:
                    return node
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _project_importers(self, lock: Optional[NodeLock],
                           manifests: tuple[_Manifest, ...],
                           lock_evidence: Optional[EvidenceReference],
                           projection: _Projection,
                           root: Path):
        instances: list[PackageInstance] = []
        edges: list[DependencyEdge] = []
        importer_records: list[NodeImporter] = list(lock.importers) if lock else []
        known = {item.path for item in importer_records}
        for manifest in manifests:
            relative = manifest.path.parent.relative_to(root) \
                if manifest.path.parent != root else Path(".")
            path = relative.as_posix()
            if path in known:
                continue
            known.add(path)
            importer_records.append(NodeImporter(
                path=path,
                name=manifest.name,
                version=manifest.version,
                dependencies=tuple(
                    dependency for dependency in manifest.dependencies
                    if dependency.scope == "runtime"),
                dev_dependencies=tuple(
                    dependency for dependency in manifest.dependencies
                    if dependency.scope == "dev"),
                optional_dependencies=tuple(
                    dependency for dependency in manifest.dependencies
                    if dependency.scope == "optional"),
                peer_dependencies=tuple(
                    dependency for dependency in manifest.dependencies
                    if dependency.scope == "peer"),
            ))
        for importer in importer_records:
            package_record = Package(
                ecosystem=self.ecosystem,
                name=importer.name or importer.path,
                declared_constraint=importer.version,
                resolved_version=importer.version,
                scope="workspace",
                source_kind="workspace",
                environment="default",
            )
            node_id = instance_id(
                package_record,
                lock_location=importer.path,
                workspace=importer.path,
            )
            instances.append(PackageInstance(
                instance_id=node_id,
                package=package_record,
                workspace=importer.path,
                source_path=importer.path,
            ))
            for dependency in (importer.dependencies + importer.dev_dependencies
                               + importer.optional_dependencies
                               + importer.peer_dependencies):
                edges.append(DependencyEdge(
                    source_id=node_id,
                    target_id=self._match_locked(projection, dependency),
                    kind=dependency.scope,
                    condition=dependency.specifier,
                    evidence_ref=lock_evidence.evidence_id if lock_evidence else None,
                ))
        return instances, edges

    @staticmethod
    def _match_locked(projection: _Projection,
                      dependency: NodeDependency) -> Optional[str]:
        candidates = projection.by_name.get(dependency.name, [])
        if len(candidates) == 1:
            return candidates[0]
        pinned = (dependency.specifier or "").strip().lstrip("^~>=< ")
        if pinned:
            for node in candidates:
                instance = next((item for item in projection.instances
                                 if item.instance_id == node), None)
                if instance is not None and instance.package.resolved_version == pinned:
                    return node
        return None

    def _collect_sources(self, root: Path, manifests: tuple[_Manifest, ...],
                         evidence: list[EvidenceReference],
                         source_paths: list[str]):
        status = parser_status()
        if not status["available"]:
            return [str(status["diagnostic"])], []
        warnings: list[str] = []
        symbols: list[SymbolCard] = []
        directories = sorted(
            (manifest.path.parent for manifest in manifests),
            key=lambda item: len(item.parts),
        )
        seen: set[str] = set()
        for manifest in manifests:
            package_name = manifest.name or manifest.path.parent.name
            for source in sorted(manifest.path.parent.glob("**/*")):
                if not source.is_file():
                    continue
                if source.suffix.lower() not in _SOURCE_SUFFIXES:
                    continue
                if "node_modules" in source.parts:
                    continue
                resolved = str(source.resolve())
                if resolved in seen:
                    continue
                # A file belongs to the nearest manifest directory, so a
                # workspace package never reports the files of a nested
                # workspace package twice.
                owner = _nearest_directory(directories, source)
                if owner is None or owner != manifest.path.parent:
                    continue
                seen.add(resolved)
                analysis: NodeSourceAnalysis = analyse_source(source)
                if not analysis.symbols and not analysis.imports:
                    continue
                raw = source.read_bytes()
                source_paths.append(str(source))
                evidence_id = content_address({
                    "kind": "node-source", "path": str(source),
                    "hash": content_address_bytes(raw),
                })
                evidence.append(EvidenceReference(
                    evidence_id=evidence_id,
                    repository=str(root),
                    revision="",
                    artifact_hash=content_address_bytes(raw),
                    member=str(source.relative_to(owner)),
                    parser_version=str(status["parserVersion"]),
                    representation="source",
                ))
                for symbol in analysis.symbols:
                    symbols.append(SymbolCard(
                        name=symbol.name,
                        kind=symbol.kind,
                        package=package_name,
                        evidence_ref=evidence_id,
                        line=symbol.line,
                        exported=symbol.exported,
                        representation="source",
                    ))
        return warnings, symbols

    # -- capabilities --------------------------------------------------------

    def capabilities(self) -> dict:
        status = parser_status()
        return {
            "ecosystem": self.ecosystem,
            "locks": ["package-lock.json", "pnpm-lock.yaml", "yarn.lock"],
            "manifests": ["package.json"],
            "parser": status,
            "parserVersion": PARSER_VERSION,
            "network": False,
            "executesDependencyCode": False,
        }
