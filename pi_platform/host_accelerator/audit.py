"""JSONL audit log for the host accelerator (G3)."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Optional


__all__ = [
    "AuditLog",
    "AuditEntry",
    "AuditError",
]


class AuditError(RuntimeError):
    """Raised when the audit log cannot be written."""


@dataclass(frozen=True)
class AuditEntry:
    """One audit log entry.

    Payload contents (``input`` text, ``embedding`` vector) are
    NEVER recorded. The audit log is for health / model
    identity / endpoint / status / timing only.
    """

    timestamp: str
    request_id: str
    endpoint: str
    model_id: str
    embedding_profile_hash: str
    status: int
    duration_ms: int
    client_address: str
    reason: str = ""

    FORBIDDEN_FIELDS = ("input", "embedding", "payload", "body")

    def to_json(self) -> str:
        d = asdict(self)
        for key in self.FORBIDDEN_FIELDS:
            if key in d:
                d[key] = "<redacted: not audited>"
        return json.dumps(d, sort_keys=True, separators=(",", ":"))


class AuditLog:
    """JSONL audit log for the host accelerator.

    Entries are appended to ``config.audit_log_path`` (default
    ``.project-intelligence-cache/accelerator/audit.jsonl``)
    one line per entry. The directory is created on first
    write.
    """

    def __init__(
        self,
        audit_log_path: str,
        *,
        clock: callable = lambda: time.time(),
    ) -> None:
        self._path = audit_log_path
        self._clock = clock

    @property
    def path(self) -> str:
        return self._path

    def record(
        self,
        *,
        endpoint: str,
        model_id: str,
        embedding_profile_hash: str,
        status: int,
        duration_ms: int,
        client_address: str,
        request_id: Optional[str] = None,
        reason: str = "",
    ) -> AuditEntry:
        entry = AuditEntry(
            timestamp=_isoformat(self._clock()),
            request_id=request_id or uuid.uuid4().hex,
            endpoint=endpoint,
            model_id=model_id,
            embedding_profile_hash=embedding_profile_hash,
            status=status,
            duration_ms=duration_ms,
            client_address=client_address,
            reason=reason,
        )
        self._append(entry)
        return entry

    def read_recent(self, limit: int = 100) -> list[dict]:
        if not os.path.isfile(self._path):
            return []
        out: list[dict] = []
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return out[-limit:]

    def _append(self, entry: AuditEntry) -> None:
        directory = os.path.dirname(self._path)
        if directory and not os.path.isdir(directory):
            try:
                os.makedirs(directory, exist_ok=True)
                os.chmod(directory, 0o700)
            except (OSError, AttributeError) as exc:
                raise AuditError(
                    f"failed to create audit log directory: {exc}"
                ) from exc
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(entry.to_json())
                f.write("\n")
        except OSError as exc:
            raise AuditError(
                f"failed to append to audit log {self._path!r}: {exc}"
            ) from exc
        try:
            os.chmod(self._path, 0o600)
        except (OSError, AttributeError):
            pass


def _isoformat(t: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(t, tz=timezone.utc).isoformat()
