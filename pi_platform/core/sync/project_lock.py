"""Per-project advisory file lock.

The product tree MUST NOT import ``scripts/file_lock.py``; the
implementation duplicates the same cross-platform ``fcntl`` / ``msvcrt``
advisory file-lock semantics so the harness lock files at
``tmp/local/session-locks/`` and the product lock files at
``tmp/local/project-locks/`` can coexist.
"""

from __future__ import annotations

import contextlib
import os
import uuid
from pathlib import Path
from typing import Iterator, Optional

__all__ = ["ProjectLock", "ProjectLockError"]


class ProjectLockError(RuntimeError):
    pass


class ProjectLock:
    """Advisory file lock scoped to a single project."""

    def __init__(self, project_id: str, *, root: Optional[Path] = None):
        self.project_id = project_id
        self.root = (root or Path("tmp") / "local" / "project-locks").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / f"{project_id}.lock"

    def _open_stream(self):
        # The lock file is created on demand; mode "a+" lets the same
        # process re-acquire the lock without a separate "create" step.
        return self.path.open("a+", encoding="utf-8")

    def _lock(self, stream) -> None:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            if not stream.read(1):
                stream.write("\0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)

    def _unlock(self, stream) -> None:
        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    @contextlib.contextmanager
    def acquire(self, *, timeout_seconds: float = 0.0) -> Iterator[None]:
        """Acquire the project lock for the duration of the context.

        ``timeout_seconds=0`` blocks until the lock is acquired; a
        positive value bounds the wait and raises
        :class:`ProjectLockError` when the timeout elapses without
        success.
        """

        if timeout_seconds < 0:
            raise ProjectLockError("timeout_seconds must be non-negative")
        stream = self._open_stream()
        acquired = False
        try:
            if timeout_seconds:
                import time
                deadline = time.monotonic() + timeout_seconds
                while True:
                    if self._try_lock(stream):
                        acquired = True
                        break
                    if time.monotonic() >= deadline:
                        raise ProjectLockError(
                            f"timed out acquiring lock for {self.project_id}"
                        )
                    time.sleep(0.05)
            else:
                self._lock(stream)
                acquired = True
            yield
        finally:
            if acquired:
                self._unlock(stream)
            stream.close()

    def _try_lock(self, stream) -> bool:
        """Attempt a non-blocking acquire; return True on success."""

        if os.name == "nt":
            import msvcrt
            stream.seek(0)
            if not stream.read(1):
                stream.write("\0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except (IOError, OSError):
                return False
            return True
        import fcntl
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (IOError, OSError):
            return False
        return True

    def path_for(self) -> Path:
        """Return the lock file path (mainly for diagnostics)."""
        return self.path