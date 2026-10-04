"""LocalSourceInboxScanner port for the v0.8 Phase 2 ingestion pipeline.

Covers architecture sections §9 (local source inbox) and §9.2
(LOCAL_ONLY / REFERENCE / SNAPSHOT promotion policy).
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import (
    KnowledgeState,
    Metadata,
    Source,
)


__all__ = [
    "LocalSourceInboxScannerPort",
    "SourcePromotionPolicy",
    "LocalSourceInboxError",
    "UnknownSource",
    "PromotionDenied",
    "InvalidPolicy",
    "LocalSourceInboxReport",
]


class SourcePromotionPolicy(str, enum.Enum):
    """The three documented source promotion policies from §9.2."""

    LOCAL_ONLY = "local_only"
    REFERENCE = "reference"
    SNAPSHOT = "snapshot"


class LocalSourceInboxError(RuntimeError):
    """Base class for LocalSourceInboxScanner errors."""


class UnknownSource(LocalSourceInboxError):
    """Raised when the requested source is not registered with the scanner."""


class PromotionDenied(LocalSourceInboxError):
    """Raised when the active policy refuses the requested promotion."""


class InvalidPolicy(LocalSourceInboxError):
    """Raised when a policy value is not a documented :class:`SourcePromotionPolicy`."""


@dataclass
class LocalSourceInboxContext:
    project_root: Path
    default_policy: SourcePromotionPolicy = SourcePromotionPolicy.LOCAL_ONLY
    override_map: Mapping[str, SourcePromotionPolicy] = field(default_factory=dict)
    recursive: bool = True
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class LocalSourceInboxReport:
    scanned_paths: Sequence[Path]
    registered_sources: Sequence[Source]
    skipped_paths: Sequence[Path] = field(default_factory=tuple)
    promoted_paths: Sequence[Path] = field(default_factory=tuple)
    knowledge_state: KnowledgeState = KnowledgeState.VERIFIED
    rationale: Optional[str] = None


class LocalSourceInboxScannerPort(abc.ABC):
    """Adapter contract: scan the local source inbox and register sources."""

    @abc.abstractmethod
    def scan(self, context: LocalSourceInboxContext) -> LocalSourceInboxReport: ...

    @abc.abstractmethod
    def resolve_policy(self, source_path: Path,
                       default_policy: SourcePromotionPolicy,
                       override_map: Mapping[str, SourcePromotionPolicy]
                       ) -> SourcePromotionPolicy: ...

    @abc.abstractmethod
    def promote(self, source: Source, policy: SourcePromotionPolicy,
                snapshot_root: Optional[Path] = None) -> Source: ...
