"""Content-addressed runtime cache.

Phase 1 ships a filesystem-based cache under the
``runtimeCacheRoot`` directory (default
``.project-intelligence-cache/``). Each cached entry is keyed by the
SHA-256 content hash of the canonical JSON body and is itself stored
as canonical JSON. Phase 3 ships the
:class:`platform.adapters.runtime.sqlite_runtime_store.SqliteRuntimeStore`
default adapter that satisfies the same ``put`` / ``get`` / ``has``
/ ``evict`` / ``stats`` surface through a thin shim, so existing
Phase 1 callers (init-project, hydrate, materialise,
ingest-sources) continue to work without modification.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, TYPE_CHECKING

from ..core.canonical.value_types import ProjectVersion


__all__ = ["RuntimeCache", "RuntimeCacheError", "RuntimeCacheEntry", "CacheEntry"]


class RuntimeCacheError(RuntimeError):
    pass


@dataclass(frozen=True)
class RuntimeCacheEntry:
    content_hash: str
    family: str
    body: Mapping[str, Any]


# Backward compatibility alias (Phase 1 callers may import CacheEntry)
CacheEntry = RuntimeCacheEntry


if TYPE_CHECKING:
    from ..adapters.runtime.sqlite_runtime_store import SqliteRuntimeStore


def _default_version() -> ProjectVersion:
    return ProjectVersion(
        gitHead="unknown",
        workingTreeFingerprint="unknown",
        knowledgeSchemaVersion="0.1.0",
        embeddingModelVersion="unknown",
        indexSchemaVersion="0.1.0",
    )


class RuntimeCache:
    """Phase 1 cache surface preserved as a thin shim over
    :class:`SqliteRuntimeStore`."""

    def __init__(self, cache_root: Path, *, version: ProjectVersion | None = None):
        from ..adapters.runtime.sqlite_runtime_store import SqliteRuntimeStore
        self._store = SqliteRuntimeStore(
            cache_root=cache_root,
            version=version or _default_version(),
        )

    def has(self, content_hash: str) -> bool:
        return self._store.has(content_hash)

    def put(self, family: str, body: Mapping[str, Any]) -> str:
        return self._store.put(family, body)

    def get(self, content_hash: str) -> RuntimeCacheEntry:
        entry = self._store.get(content_hash)
        return RuntimeCacheEntry(
            content_hash=entry.content_hash,
            family=entry.family,
            body=entry.body,
        )

    def evict(self, content_hash: str) -> None:
        self._store.evict(content_hash)

    def stats(self) -> dict[str, int]:
        return dict(self._store.stats())