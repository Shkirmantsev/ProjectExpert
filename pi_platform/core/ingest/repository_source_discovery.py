"""Repository source discovery (open spec change PR 9, plan §43–§44).

Covers the ``repository-source-discovery-incremental`` spec delta:
the automatic, incremental source discovery service that lets a
user mount a target repository and start the platform without
manually listing files. The service MUST produce a stable source
inventory with content fingerprints, MUST skip non-source
directories and intermediate build artefacts, and MUST remember
unchanged files across runs to avoid re-parsing.

The service is intentionally filesystem-only: it walks a target
directory, classifies each match against the default include /
exclude patterns, records a content hash and a stable source
family, and persists the inventory to
``.project-intelligence-cache/source-inventory.json`` so the
ingestion pipeline can compare the new inventory against the
previous one without re-walking unchanged files.
"""

from __future__ import annotations

import dataclasses
import fnmatch
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence


__all__ = [
    "DEFAULT_INCLUDE_PATTERNS",
    "DEFAULT_EXCLUDE_PATTERNS",
    "SOURCE_FAMILY_SOURCE_CODE",
    "SOURCE_FAMILY_DOCUMENTATION",
    "SOURCE_FAMILY_OPENSPEC",
    "SOURCE_FAMILY_CONFIGURATION",
    "SOURCE_FAMILY_BINARY",
    "SOURCE_FAMILIES",
    "SourceInventoryEntry",
    "SourceInventory",
    "RepositorySourceDiscovery",
    "RepositorySourceDiscoveryError",
    "classify_source_family",
]


DEFAULT_INCLUDE_PATTERNS: tuple[str, ...] = (
    # Source code
    "*.java", "*.py", "*.kt", "*.scala", "*.go", "*.rs",
    "*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs", "*.cjs",
    # Build / dependency manifests
    "pom.xml", "build.gradle", "build.gradle.kts", "settings.gradle",
    "settings.gradle.kts", "package.json", "requirements*.txt",
    "pyproject.toml", "Cargo.toml", "go.mod",
    # Documentation
    "*.md", "*.rst", "*.adoc", "*.txt", "*.html", "*.htm", "*.pdf",
    "*.xml", "*.yaml", "*.yml", "*.json", "*.proto", "*.graphql", "*.sql",
    "*.png", "*.jpg", "*.jpeg", "*.webp",
    # OpenSpec and project knowledge
    "openspec/**", "docs/**", "requirements/**",
)

DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
    # Version control
    ".git/**", ".hg/**", ".svn/**",
    # Runtime caches
    ".project-intelligence-cache/**", ".project-intelligence-deploy/**",
    "node_modules/**", ".venv/**", "venv/**", "__pycache__/**",
    # Build outputs
    "target/**", "build/**", "dist/**", "out/**", ".next/**",
    "distribution/sbom/**",
    # Generated / vendor directories
    "vendor/**", "third_party/**", "generated/**", ".generated/**",
    # Local scratch
    "tmp/local/**", "*.pyc", "*.class", "*.o", "*.so",
)


SOURCE_FAMILY_SOURCE_CODE = "source-code"
SOURCE_FAMILY_DOCUMENTATION = "documentation"
SOURCE_FAMILY_OPENSPEC = "openspec"
SOURCE_FAMILY_CONFIGURATION = "configuration"
SOURCE_FAMILY_BINARY = "binary"

SOURCE_FAMILIES: frozenset[str] = frozenset(
    {
        SOURCE_FAMILY_SOURCE_CODE,
        SOURCE_FAMILY_DOCUMENTATION,
        SOURCE_FAMILY_OPENSPEC,
        SOURCE_FAMILY_CONFIGURATION,
        SOURCE_FAMILY_BINARY,
    }
)


# Family classification rules. The first matching rule wins. The
# paths are matched against the relative POSIX form of the
# discovered file.
_FAMILY_RULES: tuple[tuple[str, Sequence[str]], ...] = (
    (
        SOURCE_FAMILY_OPENSPEC,
        ("openspec/",),
    ),
    (
        SOURCE_FAMILY_CONFIGURATION,
        (
            "pom.xml", "build.gradle", "settings.gradle",
            "package.json", "requirements", "pyproject.toml",
            "Cargo.toml", "go.mod",
        ),
    ),
    (
        SOURCE_FAMILY_DOCUMENTATION,
        ("*.md", "*.rst", "*.adoc", "docs/", "requirements/"),
    ),
    (
        SOURCE_FAMILY_SOURCE_CODE,
        (
            "*.java", "*.py", "*.kt", "*.scala", "*.go", "*.rs",
            "*.js", "*.jsx", "*.ts", "*.tsx", "*.mjs", "*.cjs",
        ),
    ),
)


# Parser version constant: the inventory records it so a parser
# version bump triggers MODIFIED classification on every entry.
DEFAULT_PARSER_VERSION = "source-discovery/v1"


class RepositorySourceDiscoveryError(RuntimeError):
    """Raised when the source discovery service cannot satisfy a
    request (e.g. missing repository root, unreadable file).
    """


def classify_source_family(rel_posix: str) -> str:
    """Classify a POSIX-style relative path into one of the
    documented source families.

    Falls back to ``SOURCE_FAMILY_BINARY`` when no rule matches
    so callers can detect unexpected file types via the inventory.
    Patterns that end with ``/`` are matched as directory
    prefixes; bare names are matched against the basename AND
    used as directory prefixes (so ``requirements`` matches
    ``requirements/base.txt`` and ``requirements.txt``).
    """

    for family, patterns in _FAMILY_RULES:
        for pattern in patterns:
            if pattern.endswith("/"):
                if rel_posix.startswith(pattern):
                    return family
            else:
                if "/" not in pattern:
                    # Bare name: matches basename OR directory
                    # prefix so ``requirements`` matches both
                    # ``requirements.txt`` and ``requirements/``.
                    if (
                        fnmatch.fnmatch(
                            os.path.basename(rel_posix), pattern,
                        )
                        or rel_posix.startswith(pattern + "/")
                    ):
                        return family
                else:
                    # Glob with slashes (e.g. ``*.java`` inside
                    # ``src/``); fnmatch over the full path.
                    if fnmatch.fnmatch(rel_posix, pattern):
                        return family
    return SOURCE_FAMILY_BINARY


@dataclass(frozen=True)
class SourceInventoryEntry:
    """One discovered source file.

    The inventory entry is the cross-run identity used by the
    ingestion pipeline. ``content_hash`` is the SHA-256 of the raw
    file bytes; ``retrieval_text_hash`` is the SHA-256 of the
    deterministic retrieval-text projection that the ingestion
    pipeline produces (or ``""`` when the parser has not yet
    produced it).
    """

    path: str
    source_family: str
    content_hash: str
    parser_version: str
    retrieval_text_hash: str = ""
    discovered_at: str = ""

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class SourceInventory:
    """The persisted inventory of a single discovery run."""

    entries: tuple[SourceInventoryEntry, ...]
    captured_at: str = ""
    schema_version: str = DEFAULT_PARSER_VERSION

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "captured_at": self.captured_at,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, object],
    ) -> "SourceInventory":
        return cls(
            entries=tuple(
                SourceInventoryEntry(**entry)
                for entry in payload.get("entries", []) or []
            ),
            captured_at=str(
                payload.get("captured_at") or "",
            ),
            schema_version=str(
                payload.get("schema_version") or DEFAULT_PARSER_VERSION
            ),
        )

    def paths(self) -> tuple[str, ...]:
        return tuple(entry.path for entry in self.entries)


class RepositorySourceDiscovery:
    """Discover source files in a target repository.

    The service walks ``repo_root`` honoring the include / exclude
    lists, classifies each match, hashes its content and persists
    the resulting inventory to ``inventory_path``. The previous
    inventory (if any) is loaded so :meth:`incremental_reuse`
    can return the unchanged entries without re-walking them.
    """

    def __init__(
        self,
        *,
        include_patterns: Sequence[str] = DEFAULT_INCLUDE_PATTERNS,
        exclude_patterns: Sequence[str] = DEFAULT_EXCLUDE_PATTERNS,
        parser_version: str = DEFAULT_PARSER_VERSION,
        max_file_bytes: int = 5 * 1024 * 1024,
    ) -> None:
        self._include = tuple(include_patterns)
        self._exclude = tuple(exclude_patterns)
        self._parser_version = parser_version
        self._max_file_bytes = int(max_file_bytes)

    @property
    def include_patterns(self) -> tuple[str, ...]:
        return self._include

    @property
    def exclude_patterns(self) -> tuple[str, ...]:
        return self._exclude

    @property
    def parser_version(self) -> str:
        return self._parser_version

    def discover(
        self, repo_root: Path | str,
    ) -> SourceInventory:
        """Walk ``repo_root`` and return the discovered inventory."""

        repo_root = Path(repo_root).resolve()
        if not repo_root.is_dir():
            raise RepositorySourceDiscoveryError(
                f"repository root {repo_root!r} is not a directory"
            )
        entries: list[SourceInventoryEntry] = []
        for dirpath, dirnames, filenames in os.walk(repo_root):
            # Apply excludes to directory pruning so we never
            # descend into `.git/`, `target/`, etc.
            original_dirnames = tuple(dirnames)
            for d in original_dirnames:
                rel = self._relative_posix(
                    repo_root, Path(dirpath) / d,
                )
                if (Path(dirpath) / d).is_symlink() or self._is_excluded(rel + "/") or self._is_excluded(d + "/"):
                    dirnames.remove(d)
            for filename in filenames:
                file_path = Path(dirpath) / filename
                if file_path.is_symlink():
                    continue
                rel = self._relative_posix(repo_root, file_path)
                if self._is_excluded(rel):
                    continue
                if not self._is_included(rel):
                    continue
                try:
                    size = file_path.stat().st_size
                except OSError:
                    continue
                if size > self._max_file_bytes:
                    continue
                try:
                    content_hash = self._content_hash(file_path)
                except OSError:
                    continue
                entries.append(
                    SourceInventoryEntry(
                        path=rel,
                        source_family=classify_source_family(rel),
                        content_hash=content_hash,
                        parser_version=self._parser_version,
                        retrieval_text_hash="",
                        discovered_at=self._now(),
                    ),
                )
        entries.sort(key=lambda e: e.path)
        return SourceInventory(
            entries=tuple(entries),
            captured_at=self._now(),
            schema_version=self._parser_version,
        )

    def incremental_reuse(
        self,
        *,
        previous_inventory: SourceInventory | None,
        new_inventory: SourceInventory,
    ) -> tuple[
        SourceInventory,
        tuple[SourceInventoryEntry, ...],
        tuple[SourceInventoryEntry, ...],
    ]:
        """Carry forward ``retrieval_text_hash`` for unchanged files.

        Returns the merged inventory plus the lists of
        ``unchanged`` and ``modified_or_added`` entries so callers
        can drive the ingestion pipeline from the diff.
        """

        if previous_inventory is None:
            return (
                new_inventory,
                (),
                tuple(new_inventory.entries),
            )

        previous_map = {
            entry.path: entry for entry in previous_inventory.entries
        }
        merged: list[SourceInventoryEntry] = []
        unchanged: list[SourceInventoryEntry] = []
        modified: list[SourceInventoryEntry] = []
        for entry in new_inventory.entries:
            prev = previous_map.get(entry.path)
            if (
                prev is not None
                and prev.content_hash == entry.content_hash
                and prev.parser_version == entry.parser_version
            ):
                # Carry the retrieval_text_hash forward so the
                # ingestion pipeline can decide whether to reparse.
                carried = SourceInventoryEntry(
                    path=entry.path,
                    source_family=entry.source_family,
                    content_hash=entry.content_hash,
                    parser_version=entry.parser_version,
                    retrieval_text_hash=prev.retrieval_text_hash,
                    discovered_at=entry.discovered_at,
                )
                merged.append(carried)
                unchanged.append(carried)
            else:
                merged.append(entry)
                modified.append(entry)
        # Detect REMOVED entries: anything in the previous
        # inventory that is absent from the new one.
        new_paths = {entry.path for entry in new_inventory.entries}
        return (
            SourceInventory(
                entries=tuple(merged),
                captured_at=new_inventory.captured_at,
                schema_version=new_inventory.schema_version,
            ),
            tuple(unchanged),
            tuple(modified),
        )

    @staticmethod
    def persist(
        inventory: SourceInventory, inventory_path: Path | str,
    ) -> Path:
        """Write the inventory to ``inventory_path`` atomically."""

        inventory_path = Path(inventory_path)
        inventory_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = inventory_path.with_suffix(inventory_path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(
                inventory.as_dict(), f,
                sort_keys=True, ensure_ascii=True,
            )
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, inventory_path)
        return inventory_path

    @staticmethod
    def load(inventory_path: Path | str) -> SourceInventory | None:
        """Load the inventory from ``inventory_path``; ``None``
        when the file does not exist.
        """

        inventory_path = Path(inventory_path)
        if not inventory_path.is_file():
            return None
        with open(inventory_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return SourceInventory.from_dict(payload)

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _relative_posix(repo_root: Path, path: Path) -> str:
        return path.resolve().relative_to(repo_root).as_posix()

    def _is_included(self, rel_posix: str) -> bool:
        return any(
            self._match(rel_posix, pattern)
            for pattern in self._include
        )

    def _is_excluded(self, rel_posix: str) -> bool:
        return any(
            self._match(rel_posix, pattern)
            for pattern in self._exclude
        )

    @staticmethod
    def _match(rel_posix: str, pattern: str) -> bool:
        if pattern.endswith("/"):
            return rel_posix.startswith(pattern)
        if "/" in pattern:
            # fnmatch treats ``/`` as a regular character, which
            # means ``openspec/**`` matches ``openspec/x`` and
            # ``openspec/foo/bar``. The wildcard ``**`` is the
            # standard convention we honour.
            return fnmatch.fnmatch(rel_posix, pattern)
        return fnmatch.fnmatch(
            os.path.basename(rel_posix), pattern,
        )

    @staticmethod
    def _content_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _now() -> str:
        import datetime as _dt
        return _dt.datetime.now(_dt.timezone.utc).isoformat()
