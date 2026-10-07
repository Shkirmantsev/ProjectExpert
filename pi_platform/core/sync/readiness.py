"""Phase 6 prerequisite 3 — knowledge readiness gate.

The :class:`DefaultKnowledgeReadiness` records the latest
:class:`HydrateReport` and :class:`ReconcileReport` and exposes
the bounded :class:`ReadinessSnapshot` the MCP server (and any
other tool serving project knowledge) consults before returning
evidence.

The gate fails closed: until a successful hydrate AND a successful
reconcile have been recorded, ``is_ready()`` returns False and
``snapshot()`` records the failure reason. The MCP server must
catch :class:`RuntimeNotReadyError` and refuse to serve; it must
NOT return stale or cross-version evidence even partially.

Design choice: the gate is intentionally tiny — no background
threads, no time-based decay. The caller (the CLI entry point or
the MCP startup hook) drives the records; the gate only
summarises. That keeps the deterministic round-trip honest and
the snapshot byte-stable for two consecutive identical cycles.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from ...ports import (
    HydrateReport,
    KnowledgeReadinessPort,
    ReadinessSnapshot,
    ReconcileReport,
    RuntimeNotReadyError,
)

__all__ = ["DefaultKnowledgeReadiness"]


log = logging.getLogger(__name__)


class DefaultKnowledgeReadiness(KnowledgeReadinessPort):
    """Default Phase 6 readiness gate."""

    def __init__(self, *, clock=None):
        # ``clock`` is a unit test seam.
        self._clock = clock or time.time
        self._hydrate_report: Optional[HydrateReport] = None
        self._reconcile_report: Optional[ReconcileReport] = None
        self._current_head: str = ""
        self._working_tree_fingerprint: str = ""
        self._last_hydrate_at: int = 0
        self._last_reconcile_at: int = 0
        self._failure_reason: str = "no hydrate recorded yet"
        self._in_progress: bool = False

    def snapshot(self) -> ReadinessSnapshot:
        if self._hydrate_report is None:
            return ReadinessSnapshot(
                consistent=False,
                current_head="",
                working_tree_fingerprint="",
                last_hydrate_at=0,
                last_reconcile_at=0,
                reason=self._failure_reason,
                in_progress=self._in_progress,
            )
        consistent = (
            self._reconcile_report is not None
            and not self._failure_reason
            and not self._in_progress
        )
        return ReadinessSnapshot(
            consistent=consistent,
            current_head=self._current_head,
            working_tree_fingerprint=self._working_tree_fingerprint,
            last_hydrate_at=self._last_hydrate_at,
            last_reconcile_at=self._last_reconcile_at,
            reason="" if consistent else (
                self._failure_reason or "no reconcile recorded yet"
            ),
            in_progress=self._in_progress,
        )

    def is_ready(self) -> bool:
        return self.snapshot().consistent

    def record_hydrate(self, report: HydrateReport) -> None:
        self._hydrate_report = report
        self._last_hydrate_at = int(self._clock())
        # Successful hydrate supersedes any prior failure reason.
        self._failure_reason = ""
        log.debug(
            "readiness: hydrate recorded families=%s",
            dict(report.families),
        )

    def record_reconcile(self, report: ReconcileReport, *,
                         current_head: str,
                         working_tree_fingerprint: str) -> None:
        self._reconcile_report = report
        self._current_head = current_head
        self._working_tree_fingerprint = working_tree_fingerprint
        self._last_reconcile_at = int(self._clock())
        self._failure_reason = ""
        log.debug(
            "readiness: reconcile recorded head=%s families=%s",
            current_head, dict(report.families),
        )

    def record_failure(self, reason: str) -> None:
        self._failure_reason = reason or "unspecified failure"
        log.warning("readiness: failure recorded reason=%r", reason)

    def begin_refresh(self) -> None:
        """Mark a refresh as in progress; consumers see ``in_progress=True``.

        The MCP server and any other server MUST refuse to serve
        while a refresh is in flight.
        """
        self._in_progress = True

    def end_refresh(self) -> None:
        self._in_progress = False


def assert_ready(readiness: KnowledgeReadinessPort) -> ReadinessSnapshot:
    """Raise :class:`RuntimeNotReadyError` unless the gate is ready.

    Convenience wrapper used by MCP tool handlers and graph /
    exact-lookup helpers (project.get_entity,
    project.find_implementation, project.trace_requirement,
    project.find_references) that must not return cross-version
    or stale evidence.
    """
    snapshot = readiness.snapshot()
    if not snapshot.consistent:
        raise RuntimeNotReadyError(snapshot)
    return snapshot