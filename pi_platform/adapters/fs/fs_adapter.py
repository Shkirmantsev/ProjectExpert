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

    def read_source_bytes(self, path: Path) -> bytes:
        """Read a local source through the filesystem adapter's I/O boundary."""
        return Path(path).read_bytes()

    # -- canonical tree ------------------------------------------------

    # Minimal OKF v0.2 ``WikiIndex`` stub. The §10 materialise gate runs
    # ``validate_wiki_bundle`` before the first durable write and refuses to
    # commit when the bundle is invalid, so the scaffold must seed enough
    # frontmatter for a freshly-initialised project to survive its first
    # hydrate→materialise cycle. The body is intentionally trivial: it is a
    # placeholder for the operator to edit, not a curated index.
    _OKF_WIKI_INDEX_STUB = (
        "---\n"
        "okf_version: '0.2'\n"
        "type: 'WikiIndex'\n"
        "title: 'Project Knowledge Index'\n"
        "---\n"
        "# Project Knowledge Index\n"
        "\n"
        "Replace this stub with your curated OKF Wiki bundle. See the\n"
        "`okf-profile` distribution under `distribution/okf-profile/` for\n"
        "templates and the §10 OKF conformance rules.\n"
    )

    def ensure_canonical_tree(self) -> None:
        """Create the documented canonical knowledge directory tree."""

        for sub in ("wiki", "graph", "chunks", "sources", "objects",
                    "manifests"):
            (self.knowledge_root / sub).mkdir(parents=True, exist_ok=True)
        # Seed the reserved ``wiki/index.md`` with a valid OKF v0.2
        # ``WikiIndex`` stub so a freshly-initialised project passes the
        # §10 materialise gate without an extra manual step. The file is
        # only written when missing, so existing real indexes are preserved.
        wiki_index = self.knowledge_root / "wiki" / "index.md"
        if not wiki_index.exists():
            wiki_index.write_text(self._OKF_WIKI_INDEX_STUB, encoding="utf-8")

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