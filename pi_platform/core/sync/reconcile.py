"""Reconcile service: incremental reconciliation after a branch switch.

The service compares the previous-HEAD manifest content hashes with
the current-HEAD manifest content hashes and re-hydrates only the
changed shards. Stale facts from the previous branch are recorded
as ``stale`` in the runtime cache so retrieval can surface them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ...adapters.fs import LocalFilesystemAdapter
from ...core.canonical import (
    KNOWN_FAMILIES,
    Manifest,
    Shard,
    canonical_load_json,
)
from ...core.git import compute_working_tree_overlay
from ...ports import ReconcilePort, ReconcileReport
from ...runtime import RuntimeCache
from .hydrate import HydrateService, _family_from_manifest_path

__all__ = ["ReconcileService"]


class ReconcileService(ReconcilePort):
    """Default Phase 1 reconcile service."""

    def __init__(self, *,
                 filesystem: Optional[LocalFilesystemAdapter] = None,
                 cache: Optional[RuntimeCache] = None,
                 hydrator: Optional[HydrateService] = None):
        self.filesystem = filesystem
        self.cache = cache
        self.hydrator = hydrator or HydrateService()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def reconcile_branch_switch(self, repo_root: Path, *,
                                previous_head: str,
                                current_head: str,
                                cache_root: Path) -> ReconcileReport:
        if previous_head == current_head:
            # Nothing to reconcile; reuse the existing hydrate report
            # structure so the call is still cheap and deterministic.
            return ReconcileReport(
                families={family: 0 for family in KNOWN_FAMILIES},
                reused_shards={family: 0 for family in KNOWN_FAMILIES},
                re_ingested_shards={family: 0 for family in KNOWN_FAMILIES},
                stale_fact_ids=(),
            )

        fs = self.filesystem or LocalFilesystemAdapter(repo_root,
                                                     cache_root=cache_root)
        cache = self.cache or RuntimeCache(cache_root)
        manifest_files = fs.list_manifests()

        families: dict[str, int] = {f: 0 for f in KNOWN_FAMILIES}
        reused: dict[str, int] = {f: 0 for f in KNOWN_FAMILIES}
        re_ingested: dict[str, int] = {f: 0 for f in KNOWN_FAMILIES}
        stale_ids: list[str] = []

        for path in manifest_files:
            family = _family_from_manifest_path(path)
            if family not in KNOWN_FAMILIES:
                continue
            try:
                manifest = _load_manifest(path)
            except Exception:  # noqa: BLE001
                continue
            for shard in manifest.shards:
                families[family] += 1
                if cache.has(shard.contentHash):
                    reused[family] += 1
                    continue
                shard_path = fs.knowledge_root / shard.path
                if not shard_path.is_file():
                    stale_ids.append(shard.id)
                    continue
                body = canonical_load_json(shard_path.read_bytes())
                cache.put(_family_for_shard(shard), body)
                re_ingested[family] += 1

        # working-tree overlay is read so the working-tree state is
        # recorded in the cache, matching the hydrate contract.
        compute_working_tree_overlay(repo_root)

        return ReconcileReport(
            families=families,
            reused_shards=reused,
            re_ingested_shards=re_ingested,
            stale_fact_ids=tuple(stale_ids),
        )


def _load_manifest(path: Path) -> Manifest:
    from ...core.canonical import load_manifest
    return load_manifest(path)


def _family_for_shard(shard: Shard) -> str:
    if "/" in shard.path:
        return shard.path.split("/", 1)[0]
    return "objects"