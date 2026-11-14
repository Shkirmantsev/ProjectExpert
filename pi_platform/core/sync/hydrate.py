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
                 cache: Optional[RuntimeCache] = None, strict: bool = True,
                 verify_portable: bool = True):
        self.filesystem = filesystem
        self.cache = cache
        self.strict = strict
        self.verify_portable = verify_portable

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

        from pi_platform.adapters.sync.portable_format import ROOT
        if self.verify_portable and (fs.knowledge_root / ROOT).exists():
            from pi_platform.adapters.sync.portable_snapshot_reader import verified_snapshot
            # v2 is verified here; only the exclusive production indexer seeds
            # indexing-state.sqlite and publishes generation membership.
            with verified_snapshot(fs.knowledge_root, cache_root):
                pass
        manifest_files = fs.list_manifests()
        for manifest_path in manifest_files:
            family = _family_from_manifest_path(manifest_path)
            if family not in KNOWN_FAMILIES:
                continue
            try:
                manifest = _safe_load_manifest(manifest_path, fs.knowledge_root)
            except Exception as exc:  # noqa: BLE001
                if self.strict:
                    raise ValueError(f"Invalid canonical manifest: {manifest_path.name}") from exc
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
        from pi_platform.adapters.sync.portable_format import confined, read_bounded, sha
        for shard in manifest.shards:
            try:
                shard_path = confined(knowledge_root, shard.path)
                raw = read_bounded(shard_path, 32 * 1024 * 1024)
                if shard_path.suffix == '.jsonl':
                    bodies = [canonical_load_json(line) for line in raw.splitlines() if line.strip()]
                    valid = sha(raw) == shard.contentHash and len(bodies) == shard.count
                else:
                    bodies = [canonical_load_json(raw)]
                    valid = content_address(bodies[0]) == shard.contentHash
                if not valid:
                    raise ValueError(f'Canonical shard checksum/count mismatch: {shard.id}')
                was_hit = all(cache.has(content_address(body)) for body in bodies)
                for body in bodies:
                    if not cache.has(content_address(body)):
                        cache.put(_family_for_shard(shard), body)
                if was_hit:
                    hit += 1
            except (OSError, ValueError) as exc:
                if self.strict:
                    raise ValueError(f'Cannot hydrate canonical shard {shard.id}: {exc}') from exc
                log.warning('legacy permissive hydration skipped %s: %s', shard.id, exc)
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
    from pi_platform.adapters.sync.portable_format import confined
    return load_manifest(confined(knowledge_root, path.relative_to(knowledge_root).as_posix()))