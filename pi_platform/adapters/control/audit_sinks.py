"""Phase 7 §59.13 audit sink adapters.

The adapter layer ships the documented sinks the default
Audit Log / Operational Log compose:

* :class:`JsonlAuditSink` — append-only JSONL audit sink.
* :class:`JsonlOperationalSink` — append-only JSONL
  operational sink. The two sinks MUST NOT share a file
  descriptor.

The default ``io.StringIO`` in-memory sinks under
:mod:`pi_platform.core.control.audit` remain the
authoritative production implementation; the JSONL sinks
ship as opt-in disk-backed adapters for operators that
require durable local persistence.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from pi_platform.ports.control.audit import (
    AuditOperationalSinkCollision,
    AuditRecord,
    OperationalRecord,
)


__all__ = ["JsonlAuditSink", "JsonlOperationalSink"]


@dataclass
class JsonlAuditSink:
    """Append-only JSONL audit sink.

    The sink writes each audit record as one JSONL line
    and refuses to share a path with
    :class:`JsonlOperationalSink`.
    """

    path: Path
    _fp: Optional[object] = field(default=None, repr=False)
    _operational_path: Optional[Path] = field(default=None, repr=False,
                                                init=False)

    def open(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.path, "a", encoding="utf-8")

    def write(self, record: AuditRecord) -> None:
        if self._fp is None:
            self.open()
        assert self._fp is not None
        payload = record.as_dict()
        line = json.dumps(payload, sort_keys=True,
                          separators=(",", ":"))
        self._fp.write(line + "\n")
        self._fp.flush()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    def assert_separated_from(self, other_path: Path) -> None:
        if Path(other_path) == Path(self.path):
            raise AuditOperationalSinkCollision(
                reason=f"audit path {self.path} matches "
                f"operational path {other_path}",
            )


@dataclass
class JsonlOperationalSink:
    """Append-only JSONL operational sink."""

    path: Path
    _fp: Optional[object] = field(default=None, repr=False)

    def open(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._fp = open(self.path, "a", encoding="utf-8")

    def write(self, record: OperationalRecord) -> None:
        if self._fp is None:
            self.open()
        assert self._fp is not None
        payload = {
            "timestamp": record.timestamp,
            "level": record.level,
            "component": record.component,
            "message": record.message,
            "correlationId": record.correlation_id,
            "durationMs": record.duration_ms,
        }
        line = json.dumps(payload, sort_keys=True,
                          separators=(",", ":"))
        self._fp.write(line + "\n")
        self._fp.flush()

    def close(self) -> None:
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    @staticmethod
    def assert_no_collision(audit_path: Path,
                             operational_path: Path) -> None:
        if Path(audit_path) == Path(operational_path):
            raise AuditOperationalSinkCollision(
                reason=f"audit path {audit_path} matches "
                f"operational path {operational_path}",
            )


def build_default_sink_pair(directory: Optional[Path] = None
                             ) -> tuple[JsonlAuditSink,
                                        JsonlOperationalSink]:
    """Build a default audit / operational sink pair under
    ``directory``. The two sinks land on distinct files
    and refuse to start if the directory cannot be
    created.
    """
    if directory is None:
        directory = Path(tempfile.gettempdir()) / "pi-platform-control"
    Path(directory).mkdir(parents=True, exist_ok=True)
    audit = JsonlAuditSink(directory / "audit.jsonl")
    operational = JsonlOperationalSink(directory / "operational.jsonl")
    JsonlOperationalSink.assert_no_collision(audit.path,
                                             operational.path)
    audit.assert_separated_from(operational.path)
    return audit, operational


def safe_unlink(path: Path) -> None:
    """Best-effort unlink that swallows missing-file errors
    (mirrors the Phase 1 helpers used in the Phase 3
    runtime store).
    """
    try:
        os.unlink(path)
    except FileNotFoundError:
        return None