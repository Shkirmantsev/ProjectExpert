"""FreshnessTracker port for the v0.8 Phase 3 storage layer.

Covers architecture section §55 (Knowledge Freshness) and §67
(Runtime Synchronization Contract — freshness staleness map).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import ProjectVersion


__all__ = [
    "FreshnessTrackerPort",
    "FreshnessError",
    "FreshnessSnapshot",
    "FreshnessFact",
]


class FreshnessError(RuntimeError):
    """Raised when a freshness tracker cannot satisfy a request."""


@dataclass(frozen=True)
class FreshnessFact:
    fact_id: str
    source_hash: str
    last_verified_at: str
    version: ProjectVersion


@dataclass(frozen=True)
class FreshnessSnapshot:
    facts: Mapping[str, FreshnessFact] = field(default_factory=dict)
    captured_at: str = ""


class FreshnessTrackerPort(abc.ABC):
    """Abstract freshness tracking port."""

    @abc.abstractmethod
    def mark_verified(
        self, fact_id: str, *, source_hash: str,
        version: ProjectVersion,
    ) -> None: ...

    @abc.abstractmethod
    def is_stale(self, fact_id: str, *, current_source_hash: str) -> bool: ...

    @abc.abstractmethod
    def derived_staleness(
        self, derived_fact_id: str, *, depends_on: Sequence[str],
    ) -> bool: ...

    @abc.abstractmethod
    def snapshot(self) -> FreshnessSnapshot: ...