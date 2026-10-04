"""Filesystem adapter for canonical and runtime paths.

The adapter is the only place that knows how the canonical tree and
the runtime cache are laid out on the filesystem; the core domain
modules consume the adapter through the
:class:`platform.ports.GitPort`-style ports.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping

from ...core.canonical import Manifest, Shard

__all__ = ["LocalFilesystemAdapter", "canonical_root_path", "runtime_cache_path"]


DEFAULT_PROJECT_KNOWLEDGE_ROOT = Path("project-knowledge")
DEFAULT_RUNTIME_CACHE_ROOT = Path(".project-intelligence-cache")
DEFAULT_DISTRIBUTION_ROOT = Path("distribution")


def canonical_root_path(repo_root: Path,
                       override: Path | None = None) -> Path:
    if override is not None:
        return (repo_root / override).resolve()
    return (repo_root / DEFAULT_PROJECT_KNOWLEDGE_ROOT).resolve()


def runtime_cache_path(repo_root: Path,
                      override: Path | None = None) -> Path:
    if override is not None:
        return (repo_root / override).resolve()
    return (repo_root / DEFAULT_RUNTIME_CACHE_ROOT).resolve()


def distribution_root_path(repo_root: Path,
                          override: Path | None = None) -> Path:
    if override is not None:
        return (repo_root / override).resolve()
    return (repo_root / DEFAULT_DISTRIBUTION_ROOT).resolve()


class LocalFilesystemAdapter:
    """Local filesystem adapter for canonical and runtime paths.

    Phase 1 ships only the local adapter; a remote filesystem adapter
    (e.g. S3) can be added in a later phase without changing the core.
    """

    def __init__(self, repo_root: Path,
                 knowledge_root: Path | None = None,
                 cache_root: Path | None = None,
                 distribution_root: Path | None = None):
        self.repo_root = repo_root.resolve()
        self.knowledge_root = canonical_root_path(self.repo_root, knowledge_root)
        self.cache_root = runtime_cache_path(self.repo_root, cache_root)
        self.distribution_root = distribution_root_path(self.repo_root,
                                                       distribution_root)

    # -- canonical tree ------------------------------------------------

    def ensure_canonical_tree(self) -> None:
        """Create the documented canonical knowledge directory tree."""

        for sub in ("wiki", "graph", "chunks", "sources", "objects",
                    "manifests"):
            (self.knowledge_root / sub).mkdir(parents=True, exist_ok=True)

    def ensure_distribution_tree(self) -> None:
        for sub in ("licenses", "skills", "codex", "claude-code",
                    "opencode", "generic-agent", "sbom"):
            target = self.distribution_root / sub
            target.mkdir(parents=True, exist_ok=True)
            gitkeep = target / ".gitkeep"
            if not gitkeep.exists():
                gitkeep.write_text("# Phase 1 placeholder\n", encoding="utf-8")

    def ensure_cache_root(self) -> None:
        self.cache_root.mkdir(parents=True, exist_ok=True)

    # -- gitignore helpers --------------------------------------------

    GITIGNORE_ENTRIES = (
        "tmp/local/**",
        ".project-intelligence-cache/**",
    )

    def ensure_gitignore(self) -> list[str]:
        """Add only the missing entries; preserve user-managed lines.

        Returns the list of entries that were actually added.
        """

        gitignore = self.repo_root / ".gitignore"
        if gitignore.exists():
            existing = gitignore.read_text(encoding="utf-8").splitlines()
        else:
            existing = []
        added: list[str] = []
        for entry in self.GITIGNORE_ENTRIES:
            if entry in existing:
                continue
            existing.append(entry)
            added.append(entry)
        if added:
            text = "\n".join(existing).rstrip("\n") + "\n"
            gitignore.write_text(text, encoding="utf-8")
        return added

    # -- manifest I/O --------------------------------------------------

    def write_manifest(self, family: str, manifest: Manifest) -> Path:
        from ..core.canonical import save_manifest
        path = self.knowledge_root / "manifests" / f"{family}-manifest.yaml"
        return save_manifest(path, manifest)

    def read_manifest(self, family: str) -> Manifest:
        from ..core.canonical import load_manifest
        path = self.knowledge_root / "manifests" / f"{family}-manifest.yaml"
        return load_manifest(path)

    def list_manifests(self) -> list[Path]:
        root = self.knowledge_root / "manifests"
        if not root.is_dir():
            return []
        return sorted(p for p in root.glob("*-manifest.yaml") if p.is_file())