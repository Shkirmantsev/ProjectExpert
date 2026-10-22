"""Persisted runtime snapshot (open spec change PR 8, plan §31–§34).

Covers the ``persisted-runtime-snapshot-reconciliation`` spec
delta: the platform persists the last successful runtime snapshot
naming the active project version, its branch, HEAD, working-tree
fingerprint, manifest snapshot hash, source snapshot hash,
embedding profile identity, active index generation and the last
successful refresh identifier. The snapshot is written only after
reconciliation and index activation succeed.

The snapshot is the input to the reconcile loop
(:func:`pi_platform.core.sync.reconcile.ReconcileService.reconcile_branch_switch`).
Without the persisted snapshot the reconcile loop would compare only
against the freshly computed manifests, which would falsely
classify every chunk as ADDED on every run.

The three persisted files (written together via the same
:class:`RuntimeSnapshotService.commit` call):

* ``runtime-state/active-version.json`` — the active project
  version identity, embedding profile identity, active index
  generation, last successful refresh identifier.
* ``runtime-state/manifest-snapshot.json`` — the canonical chunk /
  graph snapshot hash, the manifest entries, and the list of
  effective canonical chunk identifiers.
* ``runtime-state/source-snapshot.json`` — the discovered source
  inventory snapshot.

Working-tree fingerprint is part of the active-version record so a
dirty tree (HEAD unchanged, tree changed) is detectable from the
single persisted file.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


__all__ = [
    "ACTIVE_VERSION_FILENAME",
    "MANIFEST_SNAPSHOT_FILENAME",
    "SOURCE_SNAPSHOT_FILENAME",
    "RUNTIME_STATE_DIRNAME",
    "PersistedActiveVersion",
    "ManifestSnapshot",
    "SourceSnapshot",
    "PersistedSnapshot",
    "RuntimeSnapshotService",
    "RuntimeSnapshotError",
    "compute_working_tree_fingerprint",
    "compute_snapshot_hash",
    "SnapshotDiff",
]


RUNTIME_STATE_DIRNAME = "runtime-state"
ACTIVE_VERSION_FILENAME = "active-version.json"
MANIFEST_SNAPSHOT_FILENAME = "manifest-snapshot.json"
SOURCE_SNAPSHOT_FILENAME = "source-snapshot.json"


class RuntimeSnapshotError(RuntimeError):
    """Raised when the runtime snapshot cannot be persisted or read."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def compute_working_tree_fingerprint(
    paths: Iterable[Path],
) -> str:
    """Plan §38: SHA256 of (sorted path, sorted content hash) pairs.

    The fingerprint is the cheap-but-stable proxy for "the working
    tree changed" — HEAD alone is not enough because the operator
    can edit the tree without committing. The function reads the
    files; if a path does not exist it contributes ``""`` so the
    fingerprint is reproducible across partially-rendered trees.
    """

    h = hashlib.sha256()
    pairs: list[tuple[str, str]] = []
    for path in paths:
        path_str = str(path)
        try:
            data = path.read_bytes()
        except (OSError, FileNotFoundError):
            content_hash = ""
        else:
            content_hash = hashlib.sha256(data).hexdigest()
        pairs.append((path_str, content_hash))
    pairs.sort()
    for path_str, content_hash in pairs:
        h.update(path_str.encode("utf-8"))
        h.update(b"\x1f")
        h.update(content_hash.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


def compute_snapshot_hash(
    items: Sequence[str],
) -> str:
    """SHA256 of the sorted item identifiers.

    Used to label a manifest snapshot or a source snapshot with a
    stable hash so the reconcile loop can detect a change cheaply
    before falling back to per-item comparison.
    """

    h = hashlib.sha256()
    for item in sorted(items):
        h.update(item.encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


@dataclass(frozen=True)
class PersistedActiveVersion:
    """The ``runtime-state/active-version.json`` payload.

    The fingerprint captures the working-tree state; the
    ``manifest_snapshot_hash`` and ``source_snapshot_hash`` are the
    hashes of the corresponding snapshot files so the reconcile
    loop can tell cheaply whether the canonical or discovered
    state has changed.
    """

    project_version: str
    branch: str
    head: str
    working_tree_fingerprint: str
    manifest_snapshot_hash: str
    source_snapshot_hash: str
    embedding_profile_identity: str
    active_index_generation: str
    last_refresh_id: str
    persisted_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, object]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class ManifestSnapshot:
    """The ``runtime-state/manifest-snapshot.json`` payload."""

    snapshot_hash: str
    chunk_ids: tuple[str, ...]
    graph_node_ids: tuple[str, ...]
    captured_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "chunk_ids": list(self.chunk_ids),
            "graph_node_ids": list(self.graph_node_ids),
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "ManifestSnapshot":
        return cls(
            snapshot_hash=str(payload["snapshot_hash"]),
            chunk_ids=tuple(payload.get("chunk_ids", []) or []),
            graph_node_ids=tuple(payload.get("graph_node_ids", []) or []),
            captured_at=str(
                payload.get("captured_at") or _now()
            ),
        )


@dataclass(frozen=True)
class SourceSnapshot:
    """The ``runtime-state/source-snapshot.json`` payload.

    The ``source_ids`` list is the set of inventory identifiers
    used by the reconcile loop to detect ADDED / REMOVED source
    items; ``content_hashes`` lets the loop detect MODIFIED items.
    """

    snapshot_hash: str
    source_ids: tuple[str, ...]
    content_hashes: Mapping[str, str]
    captured_at: str = field(default_factory=_now)

    def as_dict(self) -> dict[str, object]:
        return {
            "snapshot_hash": self.snapshot_hash,
            "source_ids": list(self.source_ids),
            "content_hashes": dict(self.content_hashes),
            "captured_at": self.captured_at,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "SourceSnapshot":
        return cls(
            snapshot_hash=str(payload["snapshot_hash"]),
            source_ids=tuple(payload.get("source_ids", []) or []),
            content_hashes=dict(
                payload.get("content_hashes", {}) or {},
            ),
            captured_at=str(
                payload.get("captured_at") or _now()
            ),
        )


@dataclass(frozen=True)
class PersistedSnapshot:
    """The combined in-memory view of the three persisted files."""

    active: PersistedActiveVersion
    manifest: ManifestSnapshot
    source: SourceSnapshot


@dataclass(frozen=True)
class SnapshotDiff:
    """The result of comparing a persisted snapshot against a
    freshly computed candidate.

    The classification follows the spec's
    ``UNCHANGED / ADDED / MODIFIED / REMOVED`` vocabulary. The
    reconcile loop uses the diff to drive the REMOVED handling and
    to schedule ADDED / MODIFIED chunks for re-embedding.
    """

    unchanged_chunk_ids: tuple[str, ...] = ()
    added_chunk_ids: tuple[str, ...] = ()
    modified_chunk_ids: tuple[str, ...] = ()
    removed_chunk_ids: tuple[str, ...] = ()
    added_source_ids: tuple[str, ...] = ()
    removed_source_ids: tuple[str, ...] = ()
    modified_source_ids: tuple[str, ...] = ()
    working_tree_changed: bool = False
    head_changed: bool = False

    @property
    def has_removed_chunks(self) -> bool:
        return bool(self.removed_chunk_ids)

    @property
    def has_changes(self) -> bool:
        return (
            bool(self.added_chunk_ids)
            or bool(self.modified_chunk_ids)
            or bool(self.removed_chunk_ids)
            or bool(self.added_source_ids)
            or bool(self.removed_source_ids)
            or bool(self.modified_source_ids)
            or self.working_tree_changed
            or self.head_changed
        )


class RuntimeSnapshotService:
    """Persist + read the three runtime-state files.

    The service is intentionally filesystem-only: it does not own
    the snapshot generation (the reconcile loop generates it) or
    the activation (the dense index owns it). The service is the
    durable hand-off between the two.
    """

    def __init__(self, cache_root: Path | str | None = None, **kwargs: object):
        resolved = cache_root if cache_root is not None else kwargs.get("cache_root")
        if resolved is None:
            raise TypeError("RuntimeSnapshotService requires cache_root")
        self._cache_root = Path(str(resolved))
        self._runtime_state_dir = (
            self._cache_root / RUNTIME_STATE_DIRNAME
        )

    @property
    def cache_root(self) -> Path:
        return self._cache_root

    @property
    def runtime_state_dir(self) -> Path:
        return self._runtime_state_dir

    def has_persisted_snapshot(self) -> bool:
        """Return True iff all three files exist on disk."""

        return self.read_snapshot() is not None

    def read_snapshot(self) -> PersistedSnapshot | None:
        """Read the persisted snapshot; return ``None`` when absent."""

        bundle = self._runtime_state_dir / "snapshot.json"
        if bundle.is_file():
            try:
                payload = json.loads(bundle.read_text(encoding="utf-8"))
                if payload is None:
                    return None
                return PersistedSnapshot(
                    active=PersistedActiveVersion(**payload["active"]),
                    manifest=ManifestSnapshot.from_dict(payload["manifest"]),
                    source=SourceSnapshot.from_dict(payload["source"]),
                )
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise RuntimeSnapshotError(f"failed to read runtime snapshot bundle: {exc}") from exc
        # Backward compatibility: an old installation only has these three files.
        active_path = self._runtime_state_dir / ACTIVE_VERSION_FILENAME
        manifest_path = (
            self._runtime_state_dir / MANIFEST_SNAPSHOT_FILENAME
        )
        source_path = self._runtime_state_dir / SOURCE_SNAPSHOT_FILENAME
        if not (
            active_path.is_file()
            and manifest_path.is_file()
            and source_path.is_file()
        ):
            return None
        try:
            active_payload = json.loads(
                active_path.read_text(encoding="utf-8"),
            )
            manifest_payload = json.loads(
                manifest_path.read_text(encoding="utf-8"),
            )
            source_payload = json.loads(
                source_path.read_text(encoding="utf-8"),
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeSnapshotError(
                f"failed to read persisted runtime snapshot: {exc}"
            ) from exc
        return PersistedSnapshot(
            active=PersistedActiveVersion(**active_payload),
            manifest=ManifestSnapshot.from_dict(manifest_payload),
            source=SourceSnapshot.from_dict(source_payload),
        )

    def commit(
        self,
        *,
        active: PersistedActiveVersion,
        manifest: ManifestSnapshot,
        source: SourceSnapshot,
    ) -> PersistedSnapshot:
        """Publish one atomic bundle; retain three files as legacy projections.

        Existing legacy snapshots are bundled before modifying their projections.
        A failed mirror write or bundle replacement leaves the last successful
        bundle authoritative, so readers cannot combine two generations.
        """

        self._runtime_state_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = (
            self._runtime_state_dir / MANIFEST_SNAPSHOT_FILENAME
        )
        source_path = self._runtime_state_dir / SOURCE_SNAPSHOT_FILENAME
        active_path = self._runtime_state_dir / ACTIVE_VERSION_FILENAME
        bundle_path = self._runtime_state_dir / "snapshot.json"
        try:
            if not bundle_path.exists():
                previous = self.read_snapshot()
                baseline = None if previous is None else {
                    "active": previous.active.as_dict(),
                    "manifest": previous.manifest.as_dict(),
                    "source": previous.source.as_dict(),
                }
                self._atomic_write_json(bundle_path, baseline)
            self._atomic_write_json(
                manifest_path, manifest.as_dict(),
            )
            self._atomic_write_json(
                source_path, source.as_dict(),
            )
            self._atomic_write_json(
                active_path, active.as_dict(),
            )
            self._atomic_write_json(bundle_path, {
                "active": active.as_dict(), "manifest": manifest.as_dict(),
                "source": source.as_dict(),
            })
        except OSError as exc:
            raise RuntimeSnapshotError(
                f"failed to persist runtime snapshot: {exc}"
            ) from exc
        return PersistedSnapshot(
            active=active, manifest=manifest, source=source,
        )

    @staticmethod
    def _atomic_write_json(path: Path, payload: dict[str, object] | None) -> None:
        """Write ``payload`` as JSON to ``path`` atomically.

        Writes to a temporary sibling file and uses ``os.replace``
        so a crash mid-write cannot leave a partially-written
        runtime-state file.
        """

        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, sort_keys=True, ensure_ascii=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)

    @staticmethod
    def diff(
        persisted: PersistedSnapshot | None,
        *,
        candidate_active: PersistedActiveVersion,
        candidate_manifest: ManifestSnapshot,
        candidate_source: SourceSnapshot,
    ) -> SnapshotDiff:
        """Classify a candidate snapshot against the persisted one.

        When ``persisted`` is ``None`` (first run / missing
        snapshot), every chunk and source item is ADDED. The
        working-tree fingerprint change is reported as well so the
        caller can decide to rebuild from scratch.
        """

        if persisted is None:
            return SnapshotDiff(
                unchanged_chunk_ids=(),
                added_chunk_ids=candidate_manifest.chunk_ids,
                modified_chunk_ids=(),
                removed_chunk_ids=(),
                added_source_ids=candidate_source.source_ids,
                modified_source_ids=(),
                removed_source_ids=(),
                working_tree_changed=True,
                head_changed=True,
            )

        old_chunks = set(persisted.manifest.chunk_ids)
        new_chunks = set(candidate_manifest.chunk_ids)
        unchanged_chunks = old_chunks & new_chunks
        added_chunks = new_chunks - old_chunks
        removed_chunks = old_chunks - new_chunks

        # MODIFIED chunks: the chunk identifier is unchanged but
        # the source content hash for at least one of its source
        # ids changed. In this simplified snapshot the content hash
        # is keyed by source id, not chunk id; the loop maps
        # chunk -> source id via the inventory. We report the
        # chunk-level overlap here and let the reconcile loop do
        # the finer-grained mapping.
        old_sources = set(persisted.source.source_ids)
        new_sources = set(candidate_source.source_ids)
        added_sources = new_sources - old_sources
        removed_sources = old_sources - new_sources

        old_hashes = dict(persisted.source.content_hashes)
        new_hashes = dict(candidate_source.content_hashes)
        common_sources = old_sources & new_sources
        modified_sources = tuple(
            sid for sid in sorted(common_sources)
            if old_hashes.get(sid) != new_hashes.get(sid)
        )

        working_tree_changed = (
            persisted.active.working_tree_fingerprint
            != candidate_active.working_tree_fingerprint
        )
        head_changed = (
            persisted.active.head != candidate_active.head
            or persisted.active.branch != candidate_active.branch
        )

        # Every chunk whose source was modified is conservatively
        # treated as MODIFIED at the chunk level. The reconcile
        # loop drives the actual re-embed; the snapshot diff
        # carries enough information for the loop to decide.
        modified_chunks: list[str] = []
        # If we cannot map chunks -> sources, we mark every common
        # chunk that lost a source as potentially modified.
        if modified_sources:
            for cid in sorted(unchanged_chunks):
                # The chunk id matches a source id in the
                # simplified inventory scheme. The reconcile loop
                # also accepts the loose coupling: any chunk whose
                # source has been re-discovered with a different
                # content hash is marked modified here.
                if cid in modified_sources:
                    modified_chunks.append(cid)
            # Treat chunks touched by added/removed sources as
            # modified too (cross-source dependencies are not
            # modelled in this layer).
            modified_chunks.extend(added_sources)
            modified_chunks.extend(removed_sources)
            modified_chunks = sorted(set(modified_chunks))
            unchanged_chunks = tuple(
                cid for cid in sorted(unchanged_chunks)
                if cid not in set(modified_chunks)
            )

        return SnapshotDiff(
            unchanged_chunk_ids=tuple(sorted(unchanged_chunks)),
            added_chunk_ids=tuple(sorted(added_chunks)),
            modified_chunk_ids=tuple(modified_chunks),
            removed_chunk_ids=tuple(sorted(removed_chunks)),
            added_source_ids=tuple(sorted(added_sources)),
            removed_source_ids=tuple(sorted(removed_sources)),
            modified_source_ids=tuple(sorted(modified_sources)),
            working_tree_changed=working_tree_changed,
            head_changed=head_changed,
        )
