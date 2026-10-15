"""Ingestion job store port (E4).

Owns the resumable state of a single ingestion run. Additive on
top of the existing runtime store; lives in a separate
``ingestion_jobs`` table in the same ``runtime.db``.
"""

from __future__ import annotations

import abc
from typing import Mapping, Optional, Sequence, Tuple

from pi_platform.core.canonical.document_graph import IngestionCheckpoint


__all__ = [
    "IngestionJobStorePort",
    "IngestionJobStoreError",
]


class IngestionJobStoreError(RuntimeError):
    """Raised when the ingestion job store cannot satisfy a request."""


class IngestionJobStorePort(abc.ABC):
    """Abstract port for the resumable ingestion job store."""

    @abc.abstractmethod
    def create(self, job: IngestionCheckpoint) -> None: ...

    @abc.abstractmethod
    def mark_running(self, job_id: str) -> None: ...

    @abc.abstractmethod
    def mark_batch_done(
        self, job_id: str, completed_range: Tuple[int, int],
    ) -> None: ...

    @abc.abstractmethod
    def mark_failed(
        self, job_id: str, failed_range: Tuple[int, int], error: str,
    ) -> None: ...

    @abc.abstractmethod
    def mark_completed(self, job_id: str) -> None: ...

    @abc.abstractmethod
    def mark_cancelled(self, job_id: str) -> None: ...

    @abc.abstractmethod
    def get(self, job_id: str) -> Optional[IngestionCheckpoint]: ...

    @abc.abstractmethod
    def list_for_source(
        self, source_id: str,
    ) -> Sequence[IngestionCheckpoint]: ...

    @abc.abstractmethod
    def list_for_revision(
        self, revision_id: str,
    ) -> Sequence[IngestionCheckpoint]: ...

    @abc.abstractmethod
    def find_completed(
        self, source_id: str, revision_id: str, strategy_version: str,
    ) -> Optional[IngestionCheckpoint]:
        """Return the COMPLETED job for the given
        (source_id, revision_id, strategy_version) tuple, if any.
        The prescan uses this to short-circuit when a previous
        run already finished."""

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...
