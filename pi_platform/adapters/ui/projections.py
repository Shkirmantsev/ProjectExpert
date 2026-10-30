"""Read-only projections used by the §57 UI surface.

The UI service consumes projections through optional ports. Each projection
degrades gracefully when its backing seam is unavailable (returns an empty
result rather than raising) so the UI can be wired up in a fresh project
before any ingestion has occurred.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from pi_platform.ports.ui.rest_api import (
    ConflictsPort,
    SourceCatalogPort,
    SourceRecord,
    WikiReadPort,
)

__all__ = ["build_read_projections", "FilesystemSourceCatalog",
           "FilesystemWikiRead", "EmptyConflicts"]


class PublishedSourceCatalog(SourceCatalogPort):
    """Sources in the same published generation used by retrieval."""

    def __init__(self, runtime):
        self._runtime = runtime

    def list_sources(self):
        failures = {f["path"]: f for f in self._runtime.extra.get("source_failures", ())}
        inventory = self._runtime.extra.get("source_inventory")
        return tuple(SourceRecord(
            id="repo:" + entry.path, uri=entry.path,
            kind=entry.source_family, content_hash=entry.content_hash,
            freshness="failed" if entry.path in failures else "current",
            policy=entry.policy or "REFERENCE",
            metadata={"path": entry.path,
                      "status": "failed" if entry.path in failures else "discovered",
                      "failure": failures.get(entry.path)},
        ) for entry in getattr(inventory, "entries", ()))


class FilesystemSourceCatalog(SourceCatalogPort):
    """Source catalog backed by ``cfg/sources.yaml`` and the local inbox."""

    DEFAULT_SOURCES_PATH = Path("project-knowledge") / "sources.yaml"
    DEFAULT_INBOX = Path("tmp") / "local" / "source"

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = Path(repo_root).resolve()

    def list_sources(self) -> Sequence[SourceRecord]:
        records: list[SourceRecord] = []
        configured = self._repo_root / self.DEFAULT_SOURCES_PATH
        if configured.is_file():
            for raw in _iter_yaml_records(configured):
                records.append(_to_source_record(raw))
        inbox = self._repo_root / self.DEFAULT_INBOX
        if inbox.is_dir():
            for path in sorted(inbox.rglob("*")):
                if not path.is_file():
                    continue
                records.append(
                    SourceRecord(
                        id=f"local:{path.relative_to(self._repo_root).as_posix()}",
                        uri=path.absolute().as_uri(),
                        kind=_family_from_suffix(path.suffix), freshness="unindexed",
                        content_hash="",
                        policy="LOCAL_ONLY",
                        metadata={},
                    )
                )
        return tuple(records)


class FilesystemWikiRead(WikiReadPort):
    """Read-only projection over the OKF Wiki bundle."""

    def __init__(self, repo_root: Path) -> None:
        self._wiki_root = (Path(repo_root).resolve() / "project-knowledge" / "wiki")

    def read(
        self, *, query: Optional[str] = None, id: Optional[str] = None
    ) -> Sequence[Any]:
        if not self._wiki_root.is_dir():
            return ()
        documents: list[Any] = []
        needle = (query or "").strip().lower()
        for path in sorted(self._wiki_root.rglob("*.md")):
            text = path.read_text(encoding="utf-8", errors="replace")
            if id and path.stem != id:
                continue
            if needle and needle not in text.lower():
                continue
            documents.append({
                "id": path.stem,
                "path": str(path.relative_to(self._wiki_root)),
                "text": text,
            })
            if len(documents) >= 50:
                break
        return tuple(documents)


class EmptyConflicts(ConflictsPort):
    """No-op conflicts projection used until the Phase 5 conflicts port
    is wired into the UI composition."""

    def conflicts(self) -> Sequence[Any]:
        return ()


def _family_from_suffix(suffix: str) -> str:
    mapping = {
        ".md": "markdown", ".markdown": "markdown",
        ".html": "html", ".htm": "html",
        ".pdf": "pdf",
        ".java": "java", ".kt": "kotlin", ".py": "python",
        ".yaml": "yaml", ".yml": "yaml", ".json": "json",
    }
    return mapping.get(suffix.lower(), "text")


def _iter_yaml_records(path: Path) -> Iterable[dict]:
    """Yield minimal source records from a YAML file.

    We deliberately avoid a third-party YAML dependency; the catalog
    tolerates non-conforming files by returning an empty list rather
    than raising.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    records: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            records.append({"id": line[2:].strip()})
    return records


def _to_source_record(raw: dict) -> SourceRecord:
    return SourceRecord(
        id=str(raw.get("id", "")),
        uri=str(raw.get("uri", "")),
        kind=str(raw.get("family", "markdown")), freshness="unindexed",
        content_hash=str(raw.get("content_hash", "")),
        policy=str(raw.get("policy", "REFERENCE")),
        metadata=dict(raw.get("metadata", {})),
    )


def build_read_projections(
    *,
    repo_root: Path,
    cache_root: Path,
    git: Any,
) -> dict[str, Any]:
    """Construct the optional read projections used by ``RestService``.

    Returns a dict with keys ``sources``, ``wiki``, ``graph``, ``freshness``,
    ``runtime_store``, ``conflicts``. Missing entries mean "no projection
    available; degrade gracefully".
    """
    repo_root = Path(repo_root).resolve()
    cache_root = Path(cache_root).resolve()

    runtime_store = None
    freshness = None
    graph_expansion = None
    try:
        from pi_platform.adapters.runtime.sqlite_runtime_store import (
            SqliteRuntimeStore,
        )
        from pi_platform.adapters.runtime.last_verified_freshness_tracker import (
            LastVerifiedFreshnessTracker,
        )
        from pi_platform.core.canonical.value_types import ProjectVersion
        from pi_platform.core.git import compute_version_identity

        try:
            vi = compute_version_identity(repo_root)
            project_version = ProjectVersion(
                gitHead=vi.gitHead,
                workingTreeFingerprint=vi.workingTreeFingerprint,
                knowledgeSchemaVersion=vi.knowledgeSchemaVersion,
                embeddingModelVersion=vi.embeddingModelVersion,
                indexSchemaVersion=vi.indexSchemaVersion,
            )
        except Exception:
            project_version = ProjectVersion(
                gitHead="unversioned",
                workingTreeFingerprint="",
                knowledgeSchemaVersion="0.1.0",
                embeddingModelVersion="unknown",
                indexSchemaVersion="0.1.0",
            )
        runtime_store = SqliteRuntimeStore(
            cache_root=cache_root, version=project_version,
        )
        freshness = LastVerifiedFreshnessTracker(store=runtime_store)
    except Exception:
        runtime_store = None
        freshness = None

    try:
        from pi_platform.adapters.runtime.graph_expansion import (
            ProductionGraphExpansion,
        )
        from pi_platform.adapters.runtime.sharded_graph import (
            LocalShardedGraph,
        )

        canonical_graph = repo_root / "project-knowledge" / "graph"
        graph_dir = (
            canonical_graph
            if (canonical_graph / "nodes").is_dir()
            else cache_root / "graph"
        )
        graph_expansion = ProductionGraphExpansion(
            LocalShardedGraph(graph_dir),
        )
    except Exception:
        graph_expansion = None

    return {
        "sources": FilesystemSourceCatalog(repo_root),
        "wiki": FilesystemWikiRead(repo_root),
        "graph": graph_expansion,
        "freshness": freshness,
        "runtime_store": runtime_store,
        "conflicts": EmptyConflicts(),
    }
