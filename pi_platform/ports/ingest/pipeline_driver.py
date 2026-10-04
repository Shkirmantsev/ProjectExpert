"""PipelineDriver port for the v0.8 Phase 2 ingestion pipeline.

Covers architecture sections §18 (Ingestion Pipeline) and §13
(content-addressed processing across branches). Defines the
PipelineDriver coordinator that runs the documented
parsers -> chunking -> enrichment -> graph/vector/metadata -> runtime
store pipeline, plus the per-stage error-handling, idempotency and
cancellation contract.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import (
    Chunk,
    ContextualChunk,
    Document,
    Entity,
    Evidence,
    KnowledgeState,
    Relation,
    Source,
    ProjectVersion,
)


__all__ = [
    "PipelineDriverPort",
    "PipelineReport",
    "StageOutcome",
    "StageContext",
    "CancellationToken",
    "StageError",
    "StageErrorCategory",
]


class StageErrorCategory(str, enum.Enum):
    """Classification of per-stage errors.

    Stable string values keep the canonical JSON deterministic and
    the runtime cache indexable by category.
    """

    TRANSIENT = "transient"
    PERMANENT = "permanent"
    CONFIGURATION = "configuration_error"
    CANCELLED = "cancelled"


class StageError(RuntimeError):
    """Raised by a stage when it cannot proceed.

    The :attr:`category` drives the PipelineDriver's retry / abort /
    cancel policy documented in
    ``openspec/changes/implement-phase-2-ingestion/specs/2026-10-04-ingestion-pipeline-driver/spec.md``.
    """

    def __init__(self, category: StageErrorCategory, message: str,
                 *, source_id: Optional[str] = None,
                 stage: Optional[str] = None) -> None:
        super().__init__(message)
        self.category = category
        self.source_id = source_id
        self.stage = stage


class CancellationToken(abc.ABC):
    """Cooperative cancellation token for the ingestion pipeline."""

    @abc.abstractmethod
    def is_cancelled(self) -> bool: ...

    @abc.abstractmethod
    def cancel(self) -> None: ...


@dataclass
class StageContext:
    """Per-stage context passed alongside the artefact being processed."""

    project_root: Path
    source: Source
    stage_name: str
    attempt: int = 1
    timeout_seconds: float = 60.0
    cancellation: Optional[CancellationToken] = None
    cache_key: Optional[str] = None  # SHA-256 content address
    extra: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class StageOutcome:
    stage: str
    cache_hit: bool
    output_count: int
    duration_ms: float
    error_category: Optional[str] = None
    error_message: Optional[str] = None
    source_id: str = ""
    outcome: str = "ok"
    content_addresses: Sequence[str] = field(default_factory=tuple)
    attempts: int = 1


@dataclass(frozen=True)
class PipelineReport:
    source_id: str
    content_hash: str
    stages: Sequence[StageOutcome]
    chunk_count: int = 0
    entity_count: int = 0
    relation_count: int = 0
    evidence_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    knowledge_state: KnowledgeState = KnowledgeState.VERIFIED
    error_category: Optional[str] = None
    error_message: Optional[str] = None

    project_version: Optional[ProjectVersion] = None
    sources: Sequence[Source] = field(default_factory=tuple)
    started_at: str = ""
    finished_at: str = ""

    @property
    def ok(self) -> bool:
        return self.error_category is None


class PipelineDriverPort(abc.ABC):
    """The §18 ingestion pipeline coordinator.

    The driver runs the documented five-stage sequence:

    1. Parse (SourceAdapter);
    2. Chunk (Chunker);
    3. Enrich (ContextEnricher);
    4. Emit (Phase 3 Graph port placeholder);
    5. Store (Phase 3 RuntimeStore port placeholder).

    Per-stage idempotency: each stage's output is keyed by its
    SHA-256 content address. The driver MUST check the runtime cache
    for the content address before invoking a stage and reuse the
    cached artefact when present.
    """

    @abc.abstractmethod
    def run(self, source: Source, project_root: Path,
            *, cancellation: Optional[CancellationToken] = None,
            cache: Optional["RuntimeCachePort"] = None) -> PipelineReport: ...

    @abc.abstractmethod
    def run_many(self, sources: Sequence[Source], project_root: Path,
                 *, cancellation: Optional[CancellationToken] = None,
                 cache: Optional["RuntimeCachePort"] = None) -> Sequence[PipelineReport]: ...


class RuntimeCachePort(abc.ABC):
    """Phase 1 placeholder for the runtime content-addressed cache.

    The full persistent store lands in Phase 3; this port exists so
    the Phase 2 PipelineDriver can implement the
    content-addressed cache reuse semantics without depending on the
    Phase 3 implementation.
    """

    @abc.abstractmethod
    def get(self, content_hash: str) -> Optional[bytes]: ...

    @abc.abstractmethod
    def put(self, content_hash: str, payload: bytes) -> None: ...

    @abc.abstractmethod
    def hits(self) -> int: ...

    @abc.abstractmethod
    def misses(self) -> int: ...
