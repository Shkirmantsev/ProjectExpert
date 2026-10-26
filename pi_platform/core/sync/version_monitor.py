"""Project version monitor (open spec change PR 8, plan §40).

Covers the ``persisted-runtime-snapshot-reconciliation`` spec
delta's "background version monitor" requirement: the platform MUST
run a portable background monitor that polls the Git HEAD and the
working-tree fingerprint at a configurable interval between 2 and 5
seconds and schedules a reconciliation when either changes. The
monitor MUST NOT depend on OS-specific filesystem watchers.

The concrete polling monitor is owned by the serving lifecycle. It runs one
callback at a time and retries failed candidates without requiring another edit.
The no-op stub remains available for callers explicitly disabling monitoring.
"""

from __future__ import annotations

import abc
import hashlib
import json
import logging
import subprocess
from datetime import datetime, timezone
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "MIN_POLL_INTERVAL_SECONDS",
    "MAX_POLL_INTERVAL_SECONDS",
    "ProjectVersionState",
    "ProjectVersionMonitor",
    "ProjectVersionMonitorStub",
    "PollingProjectVersionMonitor",
    "read_project_version",
    "HeadChange",
]


DEFAULT_POLL_INTERVAL_SECONDS = 3
MIN_POLL_INTERVAL_SECONDS = 2
MAX_POLL_INTERVAL_SECONDS = 5


@dataclass(frozen=True)
class HeadChange:
    """One detected change event.

    The ``kind`` is one of ``"head"``, ``"working-tree"`` or
    ``"both"``. ``previous_head`` and ``new_head`` are ``None``
    when only the working-tree fingerprint changed.
    """

    kind: str
    previous_head: str | None
    new_head: str | None
    previous_fingerprint: str
    new_fingerprint: str
    detected_at: str


@dataclass(frozen=True)
class ProjectVersionState:
    """A snapshot of the Git state the monitor polls."""

    head: str
    branch: str
    working_tree_fingerprint: str


class ProjectVersionMonitor(abc.ABC):
    """Abstract portable background monitor.

    Implementations MUST poll between 2 and 5 seconds and MUST NOT
    depend on OS-specific filesystem watchers. The interface is
    intentionally narrow: ``start`` schedules reconciliation,
    ``stop`` halts the loop, ``poll_once`` is a deterministic
    single-tick helper for tests.
    """

    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS
    on_change: Callable[[HeadChange], ProjectVersionState | None] | None = None

    @abc.abstractmethod
    def start(self) -> None: ...

    @abc.abstractmethod
    def stop(self) -> None: ...

    @abc.abstractmethod
    def poll_once(self) -> HeadChange | None: ...


class ProjectVersionMonitorStub(ProjectVersionMonitor):
    """No-op monitor used by tests and the default startup profile.

    The stub records ``start`` / ``stop`` calls so tests can verify
    lifecycle wiring. ``poll_once`` returns ``None`` (no change
    detected) so the production reconciliation flow is never
    triggered spuriously in tests.
    """

    def __init__(
        self,
        *,
        poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
        on_change: Callable[[HeadChange], ProjectVersionState | None] | None = None,
    ) -> None:
        if not (
            MIN_POLL_INTERVAL_SECONDS
            <= int(poll_interval_seconds)
            <= MAX_POLL_INTERVAL_SECONDS
        ):
            raise ValueError(
                f"poll_interval_seconds must be between "
                f"{MIN_POLL_INTERVAL_SECONDS} and "
                f"{MAX_POLL_INTERVAL_SECONDS}; got "
                f"{poll_interval_seconds}"
            )
        self.poll_interval_seconds = int(poll_interval_seconds)
        self.on_change = on_change
        self._started = False
        self._stopped = False
        self._lock = threading.Lock()
        self._poll_count = 0

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def poll_count(self) -> int:
        return self._poll_count

    def start(self) -> None:
        with self._lock:
            if self._stopped:
                raise RuntimeError(
                    "ProjectVersionMonitorStub: cannot start after stop"
                )
            self._started = True

    def stop(self) -> None:
        with self._lock:
            self._started = False
            self._stopped = True

    def poll_once(self) -> HeadChange | None:
        with self._lock:
            self._poll_count += 1
        return None


def read_project_version(repo_root: Path) -> ProjectVersionState:
    """Read content identity, including edits that leave Git status unchanged.

    The discovery inventory excludes generated files and the runtime cache, so
    writing an index cannot schedule an endless cycle of refreshes. Canonical
    knowledge JSON is included separately because it is not a source extension.
    """
    from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery

    root = Path(repo_root).resolve()
    head, branch = "unversioned", ""
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise RuntimeError(f"Cannot read target Git HEAD: {result.stderr.strip()}")
        head = result.stdout.strip()
        result = subprocess.run(
            ["git", "-C", str(root), "symbolic-ref", "--quiet", "--short", "HEAD"],
            capture_output=True, text=True, check=False,
        )
        branch = result.stdout.strip() if result.returncode == 0 else "HEAD"
    inventory = RepositorySourceDiscovery().discover(root)
    hashes = {entry.path: entry.content_hash for entry in inventory.entries}
    canonical = root / "project-knowledge"
    if canonical.is_dir():
        for path in sorted(path for path in canonical.rglob("*") if path.is_file() and path.suffix in {".json", ".jsonl"}):
            hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    settings_path = root / ".project-intelligence-cache" / "retrieval-settings.json"
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        hashes["@retrieval-settings"] = {
            key: settings.get(key) for key in
            ("embedding_model_alias", "device", "document_processing_enabled")
        }
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return ProjectVersionState(head, branch, fingerprint)


class PollingProjectVersionMonitor(ProjectVersionMonitor):
    """Portable polling with serial refreshes, retry, and deterministic ticks.

    A state becomes the baseline only after its callback succeeds. A failed
    refresh is retried even when HEAD and file contents have not changed again.
    """

    def __init__(self, repo_root: Path, *, on_change: Callable[[HeadChange], ProjectVersionState | None],
                 poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
                 on_error: Callable[[Exception], None] | None = None,
                 state_reader: Callable[[], ProjectVersionState] | None = None) -> None:
        if not MIN_POLL_INTERVAL_SECONDS <= poll_interval_seconds <= MAX_POLL_INTERVAL_SECONDS:
            raise ValueError("poll_interval_seconds must be between 2 and 5")
        self.poll_interval_seconds = poll_interval_seconds
        self.on_change = on_change
        self._on_error = on_error
        self._read = state_reader or (lambda: read_project_version(repo_root))
        self._previous: ProjectVersionState | None = None
        self._stop = threading.Event()
        self._requested = threading.Event()
        self._request_lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def poll_once(self) -> HeadChange | None:
        with self._tick_lock:
            current = self._read()
            with self._request_lock:
                previous = None if self._requested.is_set() else self._previous
                self._requested.clear()
            if current == previous:
                return None
            head_changed = previous is None or current.head != previous.head or current.branch != previous.branch
            tree_changed = previous is None or current.working_tree_fingerprint != previous.working_tree_fingerprint
            event = HeadChange(
                "both" if head_changed and tree_changed else "head" if head_changed else "working-tree",
                previous.head if previous and head_changed else None,
                current.head if head_changed else None,
                previous.working_tree_fingerprint if previous else "",
                current.working_tree_fingerprint,
                datetime.now(timezone.utc).isoformat(),
            )
            try:
                accepted = self.on_change(event)
            except Exception:
                # Explicit refreshes may target the already accepted version.
                # Preserve the retry even for deterministic/manual polling.
                self._previous = None
                raise
            # A publisher can return its verified snapshot identity after bootstrap
            # creates settings. Never re-read here: that could swallow a later edit.
            self._previous = accepted if isinstance(accepted, ProjectVersionState) else current
            return event

    def request_refresh(self) -> None:
        """Queue an explicit operator refresh even if source bytes are unchanged."""
        with self._request_lock:
            self._requested.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                self._previous = None
                if self._on_error:
                    self._on_error(exc)
                else:
                    logging.getLogger(__name__).exception("Project refresh failed")
            self._stop.wait(self.poll_interval_seconds)

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("monitor already started")
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="project-version-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
