"""Content-addressed runtime cache.

Phase 1 ships a filesystem-based cache under the
``runtimeCacheRoot`` directory (default
``.project-intelligence-cache/``). Each cached entry is keyed by the
SHA-256 content hash of the canonical JSON body and is itself stored
as canonical JSON. Phase 3 replaces this stub with the real embedded
runtime store (relational + vector + graph).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from ..core.canonical import canonical_dump_json, canonical_load_json

__all__ = ["RuntimeCache", "RuntimeCacheError"]


class RuntimeCacheError(RuntimeError):
    pass


@dataclass(frozen=True)
class CacheEntry:
    content_hash: str
    family: str
    body: Mapping[str, object]


class RuntimeCache:
    """Content-addressed filesystem cache."""

    def __init__(self, cache_root: Path):
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_root / "index.json"

    # -- IO helpers ----------------------------------------------------

    def _entry_path(self, content_hash: str) -> Path:
        if len(content_hash) < 3:
            raise RuntimeCacheError("content hash too short")
        return self.cache_root / content_hash[:2] / f"{content_hash[2:]}.json"

    def _load_index(self) -> dict[str, dict[str, str]]:
        if not self.index_path.exists():
            return {}
        return canonical_load_json(self.index_path.read_bytes())

    def _save_index(self, index: Mapping[str, Mapping[str, str]]) -> None:
        body = canonical_dump_json(index)
        self.index_path.write_bytes(body)

    # -- API -----------------------------------------------------------

    def has(self, content_hash: str) -> bool:
        return self._entry_path(content_hash).exists()

    def put(self, family: str, body: Mapping[str, object]) -> str:
        from ..core.canonical import content_address_bytes
        body_bytes = canonical_dump_json(body)
        content_hash = content_address_bytes(body_bytes)
        path = self._entry_path(content_hash)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body_bytes)
        index = self._load_index()
        index[content_hash] = {"family": family, "path": str(path.relative_to(self.cache_root))}
        self._save_index(index)
        return content_hash

    def get(self, content_hash: str) -> CacheEntry:
        path = self._entry_path(content_hash)
        if not path.exists():
            raise RuntimeCacheError(f"cache miss for {content_hash}")
        body = canonical_load_json(path.read_bytes())
        return CacheEntry(content_hash=content_hash, family=body.get("family", ""), body=body)

    def evict(self, content_hash: str) -> None:
        path = self._entry_path(content_hash)
        if path.exists():
            path.unlink()
        index = self._load_index()
        index.pop(content_hash, None)
        self._save_index(index)

    def stats(self) -> dict[str, int]:
        index = self._load_index()
        return {"entries": len(index)}