"""Write-ahead log for crash-safe materialise.

The WAL records one JSON line per materialise step at
``<cache-root>/wal.log``. A marker file
``<cache-root>/materialise_in_progress`` is created when a
materialise step begins and removed when it commits.

On startup the WAL recovery procedure:

* if the marker is present and the WAL contains uncommitted entries,
  the WAL is rolled back to the last committed entry;
* otherwise the WAL is truncated and the marker removed.

This guarantees crash-safe recovery per the Phase 1 design.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Iterable, Mapping, Optional

__all__ = ["WriteAheadLog", "WalError"]


class WalError(RuntimeError):
    pass


class WriteAheadLog:
    """Append-only write-ahead log with crash-safe recovery."""

    MARKER_NAME = "materialise_in_progress"

    def __init__(self, cache_root: Path):
        self.cache_root = cache_root.resolve()
        self.cache_root.mkdir(parents=True, exist_ok=True)
        self.path = self.cache_root / "wal.log"
        self.marker_path = self.cache_root / self.MARKER_NAME

    # -- state helpers --------------------------------------------------

    def is_in_progress(self) -> bool:
        return self.marker_path.exists()

    def begin(self, materialise_id: Optional[str] = None) -> str:
        """Mark a materialise as in-progress and return its identifier."""

        mid = materialise_id or uuid.uuid4().hex
        self.marker_path.write_text(mid + "\n", encoding="utf-8")
        return mid

    def commit(self) -> None:
        """Commit the current materialise and truncate the WAL."""

        if self.marker_path.exists():
            self.marker_path.unlink()
        if self.path.exists():
            self.path.unlink()

    def rollback(self) -> int:
        """Roll back the WAL to the last committed entry.

        Returns the number of entries that were removed.
        """

        if not self.path.exists():
            if self.marker_path.exists():
                self.marker_path.unlink()
            return 0
        lines = self.path.read_text(encoding="utf-8").splitlines()
        # Find the last "committed" marker; entries after it are
        # discarded because they belong to the rolled-back materialise.
        last_committed = -1
        for index, raw_line in enumerate(lines):
            try:
                entry = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, Mapping) and entry.get("op") == "commit":
                last_committed = index
        keep = lines[:last_committed + 1]
        removed = len(lines) - len(keep)
        self.path.write_text("\n".join(keep) + ("\n" if keep else ""),
                             encoding="utf-8")
        if self.marker_path.exists():
            self.marker_path.unlink()
        return removed

    def recover(self) -> int:
        """Recover from a crashed materialise.

        Returns the number of WAL entries that were truncated (either
        rolled back because the marker was present, or discarded as
        stale because no marker was present).
        """

        if not self.is_in_progress():
            count = 0
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        count += 1
                self.path.unlink()
            return count
        return self.rollback()

    # -- append ---------------------------------------------------------

    def append(self, op: str, payload: Mapping[str, object],
               *, ts: Optional[float] = None) -> None:
        if op not in {"begin", "write", "commit", "abort"}:
            raise WalError(f"unknown WAL op {op!r}")
        entry = {"op": op, "ts": ts or time.time(), "payload": dict(payload)}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True,
                                    ensure_ascii=False,
                                    separators=(",", ":")))
            handle.write("\n")

    def read_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        out: list[dict] = []
        for raw_line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                parsed = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, Mapping):
                out.append(parsed)
        return out