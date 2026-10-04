"""Hydrate service: restore runtime cache from the canonical tree.

The service reads the per-family manifests, populates the
content-addressed runtime cache for every shard and reports the
cache hit rate per family. The Phase 1 hydrate operates over the
canonical layer and the runtime cache only; the graph/sparse/dense
indexes and the embedding cache land in Phases 3-4.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ...adapters.fs import LocalFilesystemAdapter
from ...core.canonical import (
    KNOWN_FAMILIES,
    Manifest,
    Shard,
    canonical_load_json,
    content_address,
    manifest_from_shards,
)
from ...core.git import compute_version_identity
from ...ports import HydratePort, HydrateReport, VersionIdentity
from ...runtime import RuntimeCache

__all__ = ["HydrateService"]


log = logging.getLogger(__name__)


class HydrateService(HydratePort):
    """Default Phase 1 hydrate service."""

    def __init__(self, *,
                 filesystem: Optional[LocalFilesystemAdapter] = None,
                 cache: Optional[RuntimeCache] = None):
        self.filesystem = filesystem
        self.cache = cache

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def restore_runtime(self, repo_root: Path, *,
                        cache_root: Path) -> HydrateReport:
        fs = self.filesystem or LocalFilesystemAdapter(repo_root,
                                                     cache_root=cache_root)
        cache = self.cache or RuntimeCache(cache_root)
        fs.ensure_cache_root()

        version = compute_version_identity(repo_root,
                                         knowledge_schema_version="0.1.0",
                                         index_schema_version="0.1.0")

        families: dict[str, int] = {}
        hit_rates: dict[str, float] = {}
        stale: list[str] = []

        manifest_files = fs.list_manifests()
        for manifest_path in manifest_files:
            family = _family_from_manifest_path(manifest_path)
            if family not in KNOWN_FAMILIES:
                continue
            try:
                manifest = _safe_load_manifest(manifest_path, fs.knowledge_root)
            except Exception as exc:  # noqa: BLE001
                log.warning("manifest %s could not be loaded: %s", manifest_path, exc)
                continue
            shards_hit, shards_total = self._hydrate_family(
                repo_root, manifest, cache, fs.knowledge_root
            )
            families[family] = shards_total
            hit_rates[family] = (shards_hit / shards_total) if shards_total else 1.0

        for family, total in families.items():
            if family not in hit_rates:
                hit_rates[family] = 0.0
        for family in KNOWN_FAMILIES:
            families.setdefault(family, 0)
            hit_rates.setdefault(family, 0.0)

        return HydrateReport(
            project_version=version,
            families=families,
            cache_hit_rates=hit_rates,
            stale_fact_ids=tuple(stale),
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _hydrate_family(self, repo_root: Path, manifest: Manifest,
                        cache: RuntimeCache, knowledge_root: Path
                        ) -> tuple[int, int]:
        total = len(manifest.shards)
        hit = 0
        for shard in manifest.shards:
            shard_path = knowledge_root / shard.path
            if not shard_path.is_file():
                continue
            body = canonical_load_json(shard_path.read_bytes())
            content_hash = content_address(body)
            if content_hash != shard.contentHash:
                log.warning("shard %s hash mismatch: declared %s actual %s",
                            shard.id, shard.contentHash, content_hash)
                continue
            if cache.has(shard.contentHash):
                hit += 1
                continue
            cache.put(_family_for_shard(shard), body)
            hit += 1
        return hit, total


def _family_from_manifest_path(path: Path) -> str:
    name = path.stem
    if name.endswith("-manifest"):
        name = name[: -len("-manifest")]
    return name


def _family_for_shard(shard: Shard) -> str:
    if "/" in shard.path:
        return shard.path.split("/", 1)[0]
    return "objects"


def _safe_load_manifest(path: Path, knowledge_root: Path) -> Manifest:
    from ...core.canonical import load_manifest
    return load_manifest(path)