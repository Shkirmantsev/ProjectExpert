"""The Python ecosystem adapter.

It combines three offline sources of truth and never mixes them up:

* the **declaration** in ``pyproject.toml`` / ``requirements*.txt``
  (an unresolved constraint), reusing the existing static ingestion
  helpers so the shared service does not replace the existing
  ingestion;
* the **resolution** in ``uv.lock`` / ``poetry.lock`` (a locked
  version);
* the **installed metadata** of an explicitly selected environment
  (a ``dist-info`` / ``egg-info`` directory the operator points at).

A declaration is never reported as a resolution. When the three
sources disagree the adapter reports the mismatch as a warning and
keeps both facts apart.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from email.parser import Parser
from pathlib import Path
from typing import Optional, Sequence

from pi_platform.adapters.python.intelligence import requirement_record
from pi_platform.adapters.research.python_locks import (
    LockFile,
    LockReadError,
    UnsupportedLockVersion,
    lock_instances,
    normalize_python_name,
    read_lock_file,
)
from pi_platform.core.canonical.content_address import content_address, content_address_bytes
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

__all__ = [
    "PARSER_VERSION",
    "PythonEcosystemAdapter",
    "InstalledDistribution",
]

PARSER_VERSION = "python-research-1"

_LOCK_NAMES = ("uv.lock", "poetry.lock")
_MANIFEST_NAMES = ("pyproject.toml",)


@dataclass(frozen=True)
class InstalledDistribution:
    """One distribution observed in an explicitly selected environment."""

    name: str
    version: Optional[str]
    location: str
    requires: tuple[str, ...] = ()


def _read_dist_info(root: Path) -> tuple[InstalledDistribution, ...]:
    """Read the installed metadata of one environment root.

    Only ``*.dist-info/METADATA`` and ``*.egg-info/PKG-INFO`` are read.
    Nothing is imported and no ``importlib.metadata`` scan of the host
    interpreter happens: the environment is the one the operator
    selected.
    """

    found: list[InstalledDistribution] = []
    if not root.is_dir():
        return ()
    for entry in sorted(root.iterdir()):
        metadata_path: Optional[Path] = None
        if entry.is_dir() and entry.name.endswith(".dist-info"):
            metadata_path = entry / "METADATA"
        elif entry.is_dir() and entry.name.endswith(".egg-info"):
            metadata_path = entry / "PKG-INFO"
        if metadata_path is None or not metadata_path.is_file():
            continue
        try:
            message = Parser().parsestr(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
        name = message.get("Name")
        if not name:
            continue
        found.append(InstalledDistribution(
            name=normalize_python_name(name),
            version=message.get("Version"),
            location=str(entry),
            requires=tuple(message.get_all("Requires-Dist", []) or ()),
        ))
    return tuple(found)


def _exact_pin(constraint: Optional[str]) -> Optional[str]:
    """Return the pinned version of an ``==`` constraint, if it is one."""

    if not constraint:
        return None
    match = re.fullmatch(r"==\s*([A-Za-z0-9.*+!_-]+)", constraint.strip())
    return match.group(1) if match else None


class PythonEcosystemAdapter(EcosystemResearchPort):
    """Offline Python dependency evidence."""

    ecosystem = "python"

    def __init__(self, *, installed_roots: Sequence[Path] = ()) -> None:
        #: Explicitly selected environment roots. Nothing outside them
        #: is inspected, and the host interpreter is never scanned.
        self.installed_roots = tuple(Path(root) for root in installed_roots)

    # -- port ----------------------------------------------------------------

    def detect(self, project_root: Path) -> bool:
        root = Path(project_root)
        if any((root / name).is_file() for name in _LOCK_NAMES):
            return True
        if (root / "pyproject.toml").is_file():
            return True
        for candidate in sorted(root.glob("requirements*.txt")):
            if candidate.is_file():
                return True
        return False

    def collect(self, project_root: Path, *, environment: str = "default",
                scopes: Sequence[str] = ()) -> EcosystemSnapshot:
        root = Path(project_root)
        warnings: list[str] = []
        instances: list[PackageInstance] = []
        edges: list[DependencyEdge] = []
        evidence: list[EvidenceReference] = []
        source_paths: list[str] = []
        completeness = Completeness.COMPLETE

        lock, lock_path = self._read_lock(root, warnings)
        declared = self._read_declarations(root, evidence, source_paths)

        if lock is not None:
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
            lock_nodes, lock_edges = lock_instances(
                lock, location=str(lock_path), evidence=lock_evidence)
            instances.extend(lock_nodes)
            edges.extend(lock_edges)
            warnings.extend(lock.warnings)
            warnings.extend(self._compare_declarations(declared, lock))
        else:
            completeness = Completeness.PARTIAL
            warnings.append(
                "no supported lock file: the graph contains declarations only, "
                "not a resolved closure"
            )

        self._merge_declarations(declared, instances)

        installed = self._read_installed(evidence, source_paths, warnings)
        warnings.extend(self._compare_installed(installed, instances))

        symbols = self._collect_symbols(root, evidence, source_paths, warnings)

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
            symbols=tuple(symbols),
            warnings=tuple(warnings),
            completeness=completeness,
            snapshot_id=snapshot_id,
            source_paths=tuple(source_paths),
        )

    # -- helpers -------------------------------------------------------------

    def _read_lock(self, root: Path,
                   warnings: list[str]) -> tuple[Optional[LockFile], Optional[Path]]:
        for name in _LOCK_NAMES:
            candidate = root / name
            if not candidate.is_file():
                continue
            try:
                return read_lock_file(candidate), candidate
            except UnsupportedLockVersion as exc:
                warnings.append(f"unsupported lock format: {exc}")
            except LockReadError as exc:
                warnings.append(f"lock file could not be read: {exc}")
            return None, candidate
        return None, None

    def _read_declarations(self, root: Path, evidence: list[EvidenceReference],
                           source_paths: list[str]) -> list[dict]:
        """Read the declared requirements of the project manifests."""

        declarations: list[dict] = []
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            source_paths.append(str(pyproject))
            raw = pyproject.read_bytes()
            evidence.append(EvidenceReference(
                evidence_id=content_address({"kind": "manifest", "path": str(pyproject),
                                             "hash": content_address_bytes(raw)}),
                repository=str(root),
                revision="",
                artifact_hash=content_address_bytes(raw),
                member=pyproject.name,
                parser_version=PARSER_VERSION,
                representation="manifest",
            ))
            declarations.extend(self._pyproject_declarations(pyproject))
        for candidate in sorted(root.glob("requirements*.txt")):
            if not candidate.is_file():
                continue
            source_paths.append(str(candidate))
            raw = candidate.read_bytes()
            evidence.append(EvidenceReference(
                evidence_id=content_address({"kind": "manifest", "path": str(candidate),
                                             "hash": content_address_bytes(raw)}),
                repository=str(root),
                revision="",
                artifact_hash=content_address_bytes(raw),
                member=candidate.name,
                parser_version=PARSER_VERSION,
                representation="manifest",
            ))
            declarations.extend(self._requirements_declarations(candidate))
        return declarations

    @staticmethod
    def _pyproject_declarations(path: Path) -> list[dict]:
        import tomllib

        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            return []
        project = data.get("project") if isinstance(data.get("project"), dict) else {}
        values: list[tuple[str, str]] = []
        for value in project.get("dependencies", []) or ():
            if isinstance(value, str):
                values.append((value, "runtime"))
        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for group, group_values in optional.items():
                for value in group_values or ():
                    if isinstance(value, str):
                        values.append((value, f"extra:{group}"))
        groups = data.get("dependency-groups")
        if isinstance(groups, dict):
            for group, group_values in groups.items():
                for value in group_values or ():
                    if isinstance(value, str):
                        values.append((value, f"group:{group}"))
        declarations: list[dict] = []
        for value, scope in values:
            try:
                record = requirement_record(value, scope)
            except ValueError:
                continue
            declarations.append(record)
        return declarations

    @staticmethod
    def _requirements_declarations(path: Path) -> list[dict]:
        declarations: list[dict] = []
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            return []
        for line in re.sub(r"\\\r?\n", " ", text).splitlines():
            line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
            if not line or line.startswith("#"):
                continue
            line = re.sub(r"\s+--hash(?:=|\s+)\S+", "", line)
            if line.startswith(("-", ".", "/")):
                continue
            try:
                declarations.append(requirement_record(line, "runtime"))
            except ValueError:
                continue
        return declarations

    def _merge_declarations(self, declarations: list[dict],
                            instances: list[PackageInstance]) -> None:
        """Fold the declarations into the resolved instances.

        A package that the lock also knows keeps **one** instance that
        carries both facts: the declared constraint and the resolved
        version. A package that only the manifest mentions becomes an
        unresolved instance, because a declaration is not a resolution.
        """

        by_name: dict[str, list[int]] = {}
        for index, node in enumerate(instances):
            by_name.setdefault(node.package.name, []).append(index)

        seen: set[str] = set()
        for declaration in declarations:
            name = declaration["name"]
            constraint = declaration.get("specifier") or None
            indices = by_name.get(name)
            if indices:
                index = indices[0]
                node = instances[index]
                instances[index] = replace(node, package=replace(
                    node.package,
                    declared_constraint=constraint or node.package.declared_constraint,
                ))
                continue
            if name in seen:
                continue
            seen.add(name)
            package = Package(
                ecosystem=self.ecosystem,
                name=name,
                declared_constraint=constraint,
                resolved_version=None,
                scope=declaration.get("scope", "runtime"),
                source_kind="declaration",
                environment="default",
            )
            node_id = content_address({
                "ecosystem": package.ecosystem, "name": package.name,
                "resolvedVersion": None, "lockLocation": None,
            })
            instances.append(PackageInstance(
                instance_id=node_id,
                package=package,
                source_path=None,
            ))

    @staticmethod
    def _compare_declarations(declarations: list[dict],
                              lock: LockFile) -> list[str]:
        """Report declaration/lock disagreements without resolving them."""

        warnings: list[str] = []
        locked = lock.by_name()
        for declaration in declarations:
            name = declaration["name"]
            package = locked.get(name)
            if package is None:
                warnings.append(
                    f"declared dependency {name} is not present in {lock.format_name}"
                )
                continue
            pinned = _exact_pin(declaration.get("specifier"))
            if pinned and package.version and pinned != package.version:
                warnings.append(
                    f"declared constraint {name}=={pinned} differs from the locked "
                    f"version {package.version}"
                )
        return warnings

    def _read_installed(self, evidence: list[EvidenceReference],
                        source_paths: list[str],
                        warnings: list[str]) -> tuple[InstalledDistribution, ...]:
        installed: list[InstalledDistribution] = []
        for root in self.installed_roots:
            if not root.exists():
                warnings.append(f"selected environment root does not exist: {root}")
                continue
            source_paths.append(str(root))
            distributions = _read_dist_info(root)
            for distribution in distributions:
                metadata_path = Path(distribution.location)
                candidate = metadata_path / "METADATA"
                if not candidate.is_file():
                    candidate = metadata_path / "PKG-INFO"
                raw = candidate.read_bytes() if candidate.is_file() else b""
                evidence.append(EvidenceReference(
                    evidence_id=content_address({
                        "kind": "installed", "name": distribution.name,
                        "version": distribution.version, "location": distribution.location,
                    }),
                    repository=str(root),
                    revision=distribution.version or "",
                    artifact_hash=content_address_bytes(raw),
                    member=candidate.name,
                    parser_version=PARSER_VERSION,
                    representation="manifest",
                ))
                installed.append(distribution)
        return tuple(installed)

    @staticmethod
    def _compare_installed(installed: tuple[InstalledDistribution, ...],
                           instances: list[PackageInstance]) -> list[str]:
        warnings: list[str] = []
        locked = {node.package.name: node.package.resolved_version
                  for node in instances if node.package.resolved_version}
        for distribution in installed:
            resolved = locked.get(distribution.name)
            if resolved and distribution.version and resolved != distribution.version:
                warnings.append(
                    f"installed {distribution.name} {distribution.version} differs from "
                    f"the locked version {resolved}"
                )
        return warnings

    @staticmethod
    def _collect_symbols(root: Path, evidence: list[EvidenceReference],
                          source_paths: list[str],
                          warnings: list[str]) -> list[SymbolCard]:
        """Read the symbols of the project's own Python sources.

        The static AST reader of the existing ingestion is reused, so
        the research service and the ingestion never disagree about
        what a module contains.
        """

        from pi_platform.adapters.python.intelligence import source_api

        symbols: list[SymbolCard] = []
        for path in sorted(root.glob("**/*.py")) + sorted(root.glob("**/*.pyi")):
            if not path.is_file():
                continue
            if any(part in {".venv", "venv", "site-packages", "node_modules",
                            "__pycache__", ".git"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
                relative = path.relative_to(root)
            except (OSError, UnicodeError) as exc:
                warnings.append(f"cannot read {path}: {exc}")
                continue
            module = ".".join(relative.with_suffix("").parts)
            try:
                _, apis = source_api(text, module)
            except (SyntaxError, ValueError) as exc:
                warnings.append(f"cannot analyse {path}: {exc}")
                continue
            raw = path.read_bytes()
            source_paths.append(str(path))
            evidence_id = content_address({
                "kind": "python-source", "path": str(path),
                "hash": content_address_bytes(raw),
            })
            evidence.append(EvidenceReference(
                evidence_id=evidence_id,
                repository=str(root),
                revision="",
                artifact_hash=content_address_bytes(raw),
                member=str(relative),
                parser_version=PARSER_VERSION,
                representation="source",
            ))
            for family, label, attributes in apis:
                if family not in {"PythonClass", "PythonFunction"}:
                    continue
                symbols.append(SymbolCard(
                    name=str(label),
                    kind="class" if family == "PythonClass" else "function",
                    package=module,
                    evidence_ref=evidence_id,
                    line=attributes.get("line"),
                    exported=True,
                    representation="source",
                    signature=attributes.get("signature"),
                ))
        return symbols

    # -- capabilities --------------------------------------------------------

    def capabilities(self) -> dict:
        return {
            "ecosystem": self.ecosystem,
            "locks": ["uv.lock", "poetry.lock"],
            "manifests": ["pyproject.toml", "requirements*.txt"],
            "installedMetadata": "explicitly selected environment roots only",
            "parserVersion": PARSER_VERSION,
            "network": False,
            "executesDependencyCode": False,
        }
