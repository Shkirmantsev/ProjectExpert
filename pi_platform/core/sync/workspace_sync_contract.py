"""Committed managed-workspace identity and the importer/publication lease.

The application mounts source read-only. Linux flock works on a read-only file
descriptor and coordinates with the importer's ProjectLock on the same inode.
No environment flag can silently turn a missing managed generation into bind.
"""
from contextlib import contextmanager
import json
import os
import sys
from pathlib import Path


class WorkspaceUnavailable(RuntimeError):
    """Managed source is incomplete or requires importer recovery."""


class WorkspaceSyncFence:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.state = self.root / ".projectexpert-workspace"

    @property
    def managed(self) -> bool:
        return self.state.exists() or os.environ.get("PI_WORKSPACE_MODE") == "volume"

    def committed(self) -> dict | None:
        if not self.managed:
            return None
        try:
            if self.state.is_symlink() or not (self.state / "managed.json").is_file():
                raise ValueError("missing managed sentinel")
            if (self.state / "importing.json").exists():
                raise ValueError("source import requires completion/recovery")
            path = self.state / "applied-generation.json"
            if path.is_symlink():
                raise ValueError("linked generation metadata")
            payload = json.loads(path.read_text(encoding="utf-8"))
            if payload.get("schema_version") != 1 or not isinstance(payload.get("generation"), str) or not payload["generation"]:
                raise ValueError("invalid committed generation")
            if not isinstance(payload.get("vcs"), dict):
                raise ValueError("missing VCS identity")
            return payload
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise WorkspaceUnavailable(f"Workspace unavailable: {exc}") from exc

    @contextmanager
    def lease(self):
        if not self.managed:
            yield None
            return
        if sys.platform != "linux":
            raise WorkspaceUnavailable("Managed workspace leases require Linux containers")
        import fcntl  # Managed application/importer always runs in Linux containers.
        lock = self.state / "commit.lock"
        if lock.is_symlink():
            raise WorkspaceUnavailable("Linked workspace lease")
        try:
            stream = lock.open("rb")
        except OSError as exc:
            raise WorkspaceUnavailable("Workspace lease is missing") from exc
        with stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            try:
                start = self.committed()
                yield start
                if self.committed() != start:
                    raise WorkspaceUnavailable("Workspace generation changed while leased")
            finally:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def workspace_status(root: Path) -> dict:
    fence = WorkspaceSyncFence(root)
    if not fence.managed:
        return {"mode": "bind"}
    from .version_snapshot import RuntimeSnapshotService, RuntimeSnapshotError
    cache = Path(root) / ".project-intelligence-cache"
    try:
        source = fence.committed()
        snapshot = RuntimeSnapshotService(cache_root=cache).read_snapshot()
        indexed = None
        status_path = cache / "workspace-index.json"
        if status_path.is_file():
            indexed = json.loads(status_path.read_text(encoding="utf-8"))
        backup_path = cache / "checkpoint-status.json"
        backup = json.loads(backup_path.read_text(encoding="utf-8")) if backup_path.is_file() else {}
        return {
            "mode": "volume", "sync_generation": source["generation"],
            "index_generation": snapshot.active.active_index_generation if snapshot else None,
            "indexed_sync_generation": (indexed or {}).get("sync_generation"),
            "pending_files": source.get("pending_files", 0),
            "updating": (indexed or {}).get("sync_generation") != source["generation"],
            "last_sync": source.get("last_sync"), "last_backup": backup.get("last_backup"),
            "error": backup.get("error"),
        }
    except (WorkspaceUnavailable, RuntimeSnapshotError, OSError, ValueError) as exc:
        return {"mode": "volume", "updating": True, "error": str(exc)}
