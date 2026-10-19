"""Project version monitor (open spec change PR 8, plan §40).

Covers the ``persisted-runtime-snapshot-reconciliation`` spec
delta's "background version monitor" requirement: the platform MUST
run a portable background monitor that polls the Git HEAD and the
working-tree fingerprint at a configurable interval between 2 and 5
seconds and schedules a reconciliation when either changes. The
monitor MUST NOT depend on OS-specific filesystem watchers.

This module ships the abstract :class:`ProjectVersionMonitor` and a
no-op stub. Production deployment wires a concrete subclass that
calls :func:`ReconcileService.reconcile_branch_switch` when the
fingerprint or HEAD changes; the wiring is intentionally external
because the actual scheduling thread lives outside the
synchronous platform core. The stub keeps the surface stable for
unit tests and for callers that disable background reconciliation.
"""

from __future__ import annotations

import abc
import dataclasses
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


__all__ = [
    "DEFAULT_POLL_INTERVAL_SECONDS",
    "MIN_POLL_INTERVAL_SECONDS",
    "MAX_POLL_INTERVAL_SECONDS",
    "ProjectVersionState",
    "ProjectVersionMonitor",
    "ProjectVersionMonitorStub",
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
    on_change: Callable[[HeadChange], None] | None = None

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
        on_change: Callable[[HeadChange], None] | None = None,
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
