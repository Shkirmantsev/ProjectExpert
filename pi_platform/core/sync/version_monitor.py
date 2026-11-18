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
import os
import subprocess
from datetime import datetime, timezone
import threading
import time
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


def read_project_version(repo_root: Path, *, include_portable: bool = True, cache_root: Path | None = None) -> ProjectVersionState:
    """Read content identity, including edits that leave Git status unchanged.

    The discovery inventory excludes generated files and the runtime cache, so
    writing an index cannot schedule an endless cycle of refreshes. Canonical
    knowledge JSON is included separately because it is not a source extension.
    """
    from pi_platform.core.ingest.repository_source_discovery import RepositorySourceDiscovery

    root = Path(repo_root).resolve()
    from .workspace_sync_contract import WorkspaceSyncFence
    managed = WorkspaceSyncFence(root).committed()
    head, branch = "unversioned", ""
    if managed is not None:
        vcs = managed["vcs"]
        head = str(vcs.get("head") or vcs.get("revision") or "unversioned")
        branch = str(vcs.get("branch") or "")
    elif (root / ".git").exists():
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
    if managed is not None:
        hashes["@workspace-generation"] = managed["generation"]
    canonical_hashes = canonical_fingerprints(root)
    if not include_portable:
        canonical_hashes.pop("project-knowledge/manifests/portable-v2.json", None)
    hashes.update(canonical_hashes)
    policy_path = (Path(cache_root) if cache_root else root / '.project-intelligence-cache') / 'config/source-encodings.json'
    if policy_path.is_file():
        # Invalid oversized settings still change identity without an unbounded read.
        with policy_path.open('rb') as stream:
            prefix = stream.read(131073)
        hashes['@source-encodings'] = hashlib.sha256(prefix).hexdigest()
    hashes['@ingestion-runtime'] = {key: os.environ.get(key) for key in (
        'PI_INDEX_ENGINE', 'PI_INDEX_REQUIRE_COMPLETE', 'PI_STARTUP_PROFILE',
        'PI_EMBEDDING_MODEL', 'PI_EMBEDDING_DEVICE', 'PI_DOCLING_ENABLED',
        'PI_ASSET_MANIFEST_SHA256', 'PI_IMAGE')}

    settings_path = root / ".project-intelligence-cache" / "retrieval-settings.json"
    if settings_path.is_file():
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        hashes["@retrieval-settings"] = {
            key: settings.get(key) for key in
            ("embedding_model_alias", "device", "document_processing_enabled")
        }
    fingerprint = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    return ProjectVersionState(head, branch, fingerprint)


def canonical_fingerprints(root):
    """Hash legacy canonical files and the v2 root without walking v2 data."""
    hashes = {}
    canonical = root / "project-knowledge"
    if canonical.is_dir():
        for directory, dirs, names in os.walk(canonical):
            relative_dir = Path(directory).relative_to(canonical).as_posix()
            dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()
                       and f"{relative_dir}/{name}" not in
                       {'objects/portable-v2', 'manifests/portable-v2'}]
            for name in sorted(names):
                path = Path(directory) / name
                if path.is_file() and not path.is_symlink() and path.suffix in {'.json', '.jsonl'}:
                    hashes[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


class PollingProjectVersionMonitor(ProjectVersionMonitor):
    """Portable polling with serial refreshes, retry, and deterministic ticks.

    A state becomes the baseline only after its callback succeeds. Typed permanent
    candidate failures suspend until input changes or the owner requests retry.
    Typed transient failures back off; legacy untyped callbacks retain retry.
    """

    def __init__(self, repo_root: Path, *, on_change: Callable[[HeadChange], ProjectVersionState | None],
                 poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
                 on_error: Callable[[Exception], None] | None = None,
                 state_reader: Callable[[], ProjectVersionState] | None = None,
                 cache_root: Path | None = None) -> None:
        if not MIN_POLL_INTERVAL_SECONDS <= poll_interval_seconds <= MAX_POLL_INTERVAL_SECONDS:
            raise ValueError("poll_interval_seconds must be between 2 and 5")
        self.poll_interval_seconds = poll_interval_seconds
        self.on_change = on_change
        self._on_error = on_error
        self._read = state_reader or (lambda: read_project_version(repo_root, cache_root=cache_root))
        self._previous: ProjectVersionState | None = None
        self._failure_path = (Path(cache_root) if cache_root else Path(repo_root) / '.project-intelligence-cache') / 'index-retry.json'
        self._failure = None
        try:
            saved = json.loads(self._failure_path.read_text(encoding='utf-8'))
            if (isinstance(saved, dict) and saved.get('schema_version') == 1
                    and isinstance(saved.get('candidate'), str) and isinstance(saved.get('attempts'), int)
                    and (saved.get('retry_at') is None or isinstance(saved.get('retry_at'), (int, float)))):
                self._failure = saved
        except (OSError, ValueError):
            pass
        self._stop = threading.Event()
        self._requested = threading.Event()
        self._request_lock = threading.Lock()
        self._tick_lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def poll_once(self) -> HeadChange | None:
        with self._tick_lock:
            current = self._read()
            with self._request_lock:
                manual = self._requested.is_set()
                previous = None if manual else self._previous
                self._requested.clear()
            candidate = hashlib.sha256(json.dumps([current.head, current.branch, current.working_tree_fingerprint]).encode()).hexdigest()
            if not manual and self._failure and self._failure.get('candidate') == candidate:
                retry_at = self._failure.get('retry_at')
                if retry_at is None or time.time() < retry_at:
                    return None
            if current == previous and not (self._failure and self._failure.get("candidate") == candidate):
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
            except Exception as exc:
                from pi_platform.core.ingest.failures import CandidateIndexingError
                if isinstance(exc, CandidateIndexingError):
                    attempted = getattr(exc, 'candidate_state', current)
                    candidate = hashlib.sha256(json.dumps([attempted.head, attempted.branch, attempted.working_tree_fingerprint]).encode()).hexdigest()
                    attempts = (self._failure.get('attempts', 0) if self._failure and self._failure.get('candidate') == candidate else 0) + 1
                    self._failure = {'schema_version': 1, 'candidate': candidate,
                        'categories': exc.categories, 'attempts': attempts,
                        'state': 'retry-delayed' if exc.retryable and attempts < 5 else 'blocked-by-source-errors',
                        'retry_at': time.time() + min(300, 5 * 2 ** min(attempts, 6)) if exc.retryable and attempts < 5 else None}
                    self._persist_failure()
                # Explicit refreshes may target the already accepted version.
                # Preserve the retry even for deterministic/manual polling.
                if not isinstance(exc, CandidateIndexingError):
                    self._previous = None
                raise
            # A publisher can return its verified snapshot identity after bootstrap
            # creates settings. Never re-read here: that could swallow a later edit.
            self._previous = accepted if isinstance(accepted, ProjectVersionState) else current
            if self._failure is not None:
                self._failure = None
                self._failure_path.unlink(missing_ok=True)
            return event

    def _persist_failure(self):
        self._failure_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._failure_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self._failure, sort_keys=True), encoding='utf-8')
        os.replace(temporary, self._failure_path)

    def request_refresh(self) -> None:
        """Queue an explicit operator refresh even if source bytes are unchanged."""
        with self._request_lock:
            self._requested.set()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as exc:
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
