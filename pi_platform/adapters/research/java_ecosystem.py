"""The Java ecosystem adapter.

It reads the *declaration* of a Maven or Gradle project through the
existing static adapters, so the shared service does not replace the
existing ingestion. It never runs a build tool: ``mvn dependency:tree``
and ``gradle dependencies`` execute project code, and that requires the
existing policy boundary and isolation, not an implicit research call.

An explicitly selected local repository (``~/.m2/repository`` and
friends) contributes the *installed* version of a declared dependency.
That is an installed fact, not a resolved closure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from pi_platform.adapters.java.gradle_adapter import GradleAdapter
from pi_platform.adapters.java.maven_adapter import MavenAdapter
from pi_platform.core.canonical.content_address import content_address, content_address_bytes
from pi_platform.core.canonical.value_types import Source
from pi_platform.core.research.graph import instance_id
from pi_platform.core.research.records import (
    Completeness,
    DependencyEdge,
    EvidenceReference,
    EcosystemSnapshot,
    Package,
    PackageInstance,
)
from pi_platform.ports.research.ecosystem import EcosystemResearchPort

__all__ = ["PARSER_VERSION", "JavaEcosystemAdapter"]

PARSER_VERSION = "java-research-1"

_COORDINATE = re.compile(r"^\s*([A-Za-z0-9_.\-]+):([A-Za-z0-9_.\-]+)(?::([^\s]+))?\s*$")


@dataclass(frozen=True)
class _Declaration:
    group: str
    artifact: str
    version: Optional[str]
    scope: str
    source_path: str


class JavaEcosystemAdapter(EcosystemResearchPort):
    """Offline Java dependency evidence."""

    ecosystem = "java"

    def __init__(self, *, installed_roots: Sequence[Path] = ()) -> None:
        #: Explicitly selected local repositories. Nothing outside them
        #: is inspected.
        self.installed_roots = tuple(Path(root) for root in installed_roots)

    # -- port ----------------------------------------------------------------

    def detect(self, project_root: Path) -> bool:
        root = Path(project_root)
        return any((root / name).is_file()
                   for name in ("pom.xml", "build.gradle", "build.gradle.kts"))

    def collect(self, project_root: Path, *, environment: str = "default",
                scopes: Sequence[str] = ()) -> EcosystemSnapshot:
        root = Path(project_root)
        warnings: list[str] = []
        instances: list[PackageInstance] = []
        edges: list[DependencyEdge] = []
        evidence: list[EvidenceReference] = []
        source_paths: list[str] = []
        declarations = self._read_declarations(root, evidence, source_paths, warnings)

        by_coordinate: dict[str, str] = {}
        for declaration in declarations:
            package_record = Package(
                ecosystem=self.ecosystem,
                name=f"{declaration.group}:{declaration.artifact}",
                declared_constraint=declaration.version,
                resolved_version=None,
                scope=declaration.scope,
                source_kind="declaration",
                environment="default",
            )
            node_id = instance_id(package_record, lock_location=declaration.source_path)
            by_coordinate[f"{declaration.group}:{declaration.artifact}"] = node_id
            instances.append(PackageInstance(
                instance_id=node_id,
                package=package_record,
                source_path=declaration.source_path,
            ))

        installed = self._read_installed(declarations, evidence, source_paths, warnings)
        for coordinate, node_id in list(by_coordinate.items()):
            version = installed.get(coordinate)
            if version is None:
                continue
            current = next(item for item in instances
                           if item.instance_id == node_id)
            by_coordinate[coordinate] = node_id
            instances.remove(current)
            package_record = Package(
                ecosystem=self.ecosystem,
                name=current.package.name,
                declared_constraint=current.package.declared_constraint,
                resolved_version=version,
                scope=current.package.scope,
                source_kind="installed",
                environment="default",
            )
            instances.append(PackageInstance(
                instance_id=node_id,
                package=package_record,
                source_path=current.source_path,
            ))

        root_node = self._root_instance(root, declarations, instances)
        if root_node is not None:
            for declaration in declarations:
                edges.append(DependencyEdge(
                    source_id=root_node.instance_id,
                    target_id=by_coordinate.get(
                        f"{declaration.group}:{declaration.artifact}"),
                    kind=declaration.scope,
                    condition=None,
                    evidence_ref=None,
                ))

        completeness = Completeness.PARTIAL if declarations else Completeness.NONE
        warnings.append(
            "the transitive closure is not resolved: a dependency-tree command "
            "executes project code and requires an explicit authorisation"
        )

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
            warnings=tuple(warnings),
            completeness=completeness,
            snapshot_id=snapshot_id,
            source_paths=tuple(source_paths),
        )

    # -- helpers -------------------------------------------------------------

    def _read_declarations(self, root: Path, evidence: list[EvidenceReference],
                           source_paths: list[str],
                           warnings: list[str]) -> list[_Declaration]:
        declarations: list[_Declaration] = []
        candidates = [
            (root / "pom.xml", MavenAdapter()),
            (root / "build.gradle", GradleAdapter()),
            (root / "build.gradle.kts", GradleAdapter()),
        ]
        for path, adapter in candidates:
            if not path.is_file():
                continue
            raw = path.read_bytes()
            source_paths.append(str(path))
            evidence.append(EvidenceReference(
                evidence_id=content_address({"kind": "manifest", "path": str(path),
                                             "hash": content_address_bytes(raw)}),
                repository=str(root),
                revision="",
                artifact_hash=content_address_bytes(raw),
                member=path.name,
                parser_version=PARSER_VERSION,
                representation="manifest",
            ))
            source = Source(
                content_address({"path": str(path)}),
                str(path),
                adapter.family.value,
                content_address_bytes(raw),
            )
            try:
                declared = adapter.parse(source)
            except Exception as exc:  # noqa: BLE001 - the adapter boundary is wide
                warnings.append(f"cannot read {path.name}: {exc}")
                continue
            for entity in declared.entities:
                if entity.family != "Dependency":
                    continue
                attributes = dict(entity.metadata.extensions or {})
                group = attributes.get("group") or attributes.get("groupId")
                artifact = attributes.get("artifact") or attributes.get("artifactId")
                version = attributes.get("version")
                scope = attributes.get("scope") or "compile"
                if not group or not artifact:
                    continue
                declarations.append(_Declaration(
                    group=str(group),
                    artifact=str(artifact),
                    version=str(version) if version else None,
                    scope=str(scope),
                    source_path=str(path),
                ))
        return declarations

    def _read_installed(self, declarations: list[_Declaration],
                        evidence: list[EvidenceReference],
                        source_paths: list[str],
                        warnings: list[str]) -> dict[str, str]:
        installed: dict[str, str] = {}
        for repository in self.installed_roots:
            if not repository.is_dir():
                warnings.append(f"selected local repository does not exist: {repository}")
                continue
            source_paths.append(str(repository))
            for declaration in declarations:
                coordinate = f"{declaration.group}:{declaration.artifact}"
                group_path = declaration.group.replace(".", "/")
                directory = repository / group_path / declaration.artifact
                if not directory.is_dir():
                    continue
                versions = sorted(
                    entry.name for entry in directory.iterdir()
                    if entry.is_dir() and entry.name[0].isdigit()
                )
                if not versions:
                    continue
                installed[coordinate] = versions[-1]
                evidence.append(EvidenceReference(
                    evidence_id=content_address({
                        "kind": "installed", "coordinate": coordinate,
                        "version": versions[-1],
                    }),
                    repository=str(repository),
                    revision=versions[-1],
                    artifact_hash=None,
                    member=f"{declaration.group}/{declaration.artifact}/{versions[-1]}",
                    parser_version=PARSER_VERSION,
                    representation="manifest",
                ))
        return installed

    @staticmethod
    def _root_instance(root: Path, declarations: list[_Declaration],
                       instances: list[PackageInstance]) -> Optional[PackageInstance]:
        if not declarations:
            return None
        package_record = Package(
            ecosystem="java",
            name=str(root.name),
            declared_constraint=None,
            resolved_version=None,
            scope="project",
            source_kind="project",
            environment="default",
        )
        node = PackageInstance(
            instance_id=instance_id(package_record, lock_location=str(root)),
            package=package_record,
            source_path=str(root),
        )
        instances.append(node)
        return node

    # -- capabilities --------------------------------------------------------

    def capabilities(self) -> dict:
        return {
            "ecosystem": self.ecosystem,
            "manifests": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "installedRepositories": "explicitly selected local repositories only",
            "resolvedClosure": (
                "requires an authorised dependency-tree command; the research "
                "service never runs a build tool"
            ),
            "parserVersion": PARSER_VERSION,
            "network": False,
            "executesDependencyCode": False,
        }
