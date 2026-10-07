"""RuntimeStore port for the v0.8 Phase 3 storage layer.

Covers architecture section §62 (Startup / Branch-Switch
Synchronization), §10.2 (Content-Addressed Objects), §64
(Suggested Repository Layout — runtime cache) and §67 (Runtime
Synchronization Contract).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import ProjectVersion


__all__ = [
    "RuntimeStorePort",
    "RuntimeStoreError",
    "RuntimeEntry",
    "RuntimeStatusReport",
    "KnowledgeStatePolicy",
]


class RuntimeStoreError(RuntimeError):
    """Raised when a runtime store cannot satisfy a request."""


class ContentAddressCollision(RuntimeStoreError):
    """Raised when the same content address is produced by two
    different bodies, indicating a serializer bug."""


class WALTailCorrupt(RuntimeStoreError):
    """Raised when the WAL tail cannot be replayed."""


class VersionStampMismatch(RuntimeStoreError):
    """Raised when the bound VersionIdentity does not match the
    caller-supplied VersionIdentity."""


class ProjectLockTimeout(RuntimeStoreError):
    """Raised when the per-project advisory lock cannot be acquired
    within the configured budget."""


@dataclass(frozen=True)
class RuntimeEntry:
    content_hash: str
    family: str
    body: Mapping[str, Any]


@dataclass(frozen=True)
class RuntimeStatusReport:
    bound_version: ProjectVersion
    backend: str
    cache_entries: int
    wal_tail_length: int
    families: tuple = ()
    family_counts: Mapping[str, int] = field(default_factory=dict)


class KnowledgeStatePolicy(str):
    """Projection set used by the runtime store when reporting
    durable facts. Mirrors the Phase 1 ``KnowledgeStateFilter``."""

    DURABLE = "DURABLE"
    ALL = "ALL"
    STALE = "STALE"


class RuntimeStorePort(abc.ABC):
    """Abstract runtime store port.

    Phase 3 ships :class:`platform.adapters.runtime.sqlite_runtime_store
    .SqliteRuntimeStore` as the default adapter. The PostgreSQL
    backend is opt-in for the enterprise-scale profile.
    """

    @abc.abstractmethod
    def put(self, family: str, body: Mapping[str, Any]) -> str: ...

    @abc.abstractmethod
    def get(self, content_hash: str) -> RuntimeEntry: ...

    @abc.abstractmethod
    def has(self, content_hash: str) -> bool: ...

    @abc.abstractmethod
    def evict(self, content_hash: str) -> None: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...

    @abc.abstractmethod
    def runtime_status(
        self, *, policy: str = KnowledgeStatePolicy.DURABLE
    ) -> RuntimeStatusReport: ...

    @abc.abstractmethod
    def wal_tail_length(self) -> int: ...

    @abc.abstractmethod
    def recover_wal(self) -> None: ...

    @abc.abstractmethod
    def backend_name(self) -> str: ...