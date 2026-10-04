"""ContextEnricher port for the v0.8 Phase 2 ingestion pipeline.

Covers architecture sections §22 (three-layer context enrichment),
§54 (metadata-only fields) and §55 (freshness and provenance).
Defines the deterministic metadata layer, the domain-rule layer
and the optional small LLM layer that produce
:class:`ContextualChunk` records.
"""

from __future__ import annotations

import abc
import enum
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import (
    Chunk,
    ContextualChunk,
    KnowledgeState,
    Metadata,
)

from .source_adapter import SourceContentFamily


__all__ = [
    "ContextEnricherPort",
    "EnrichmentLayer",
    "EnricherError",
    "DomainRule",
    "ContextEnricherReport",
]


class EnrichmentLayer(str, enum.Enum):
    """The three documented enrichment layers.

    Stable string values keep the canonical report indexable by
    layer and the runtime cache addressable by layer.
    """

    DETERMINISTIC = "deterministic"
    DOMAIN_RULE = "domain_rule"
    OPTIONAL_LLM = "optional_llm"


class EnricherError(RuntimeError):
    """Raised when an enricher cannot produce a ContextualChunk."""


@dataclass(frozen=True)
class DomainRule:
    """A single deterministic domain-rule entry."""

    path_glob: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    content_family: Optional[SourceContentFamily] = None
    description: Optional[str] = None


@dataclass
class EnricherContext:
    """Per-enrichment context."""

    project_root: object = None
    knowledge_state_default: KnowledgeState = KnowledgeState.VERIFIED
    domain_rules: Sequence[DomainRule] = field(default_factory=tuple)
    enable_optional_llm: bool = False
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ContextEnricherReport:
    chunk_id: str
    applied_layers: Sequence[EnrichmentLayer]
    duration_ms: float
    rationale: Optional[str] = None
    knowledge_state: KnowledgeState = KnowledgeState.VERIFIED


class ContextEnricherPort(abc.ABC):
    """Adapter contract: turn :class:`Chunk` records into :class:`ContextualChunk` records.

    The implementation MUST follow the three-layer strategy in
    §22.3: a deterministic metadata layer that never invents
    authoritative identifiers, a domain-rule layer that applies
    project-context rules, and an optional small LLM layer
    (disabled by default) that never authoritatively populates
    any field covered by the deterministic layer.
    """

    @property
    @abc.abstractmethod
    def family(self) -> SourceContentFamily: ...

    @abc.abstractmethod
    def enrich(self, chunks: Sequence[Chunk],
               context: Optional[EnricherContext] = None
               ) -> tuple[Sequence[ContextualChunk], Sequence[ContextEnricherReport]]: ...
