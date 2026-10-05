"""Provenance port for the v0.8 Phase 3 storage layer.

Covers architecture section §67 (Runtime Synchronization Contract
— provenance), §54 (Knowledge Provenance) and §55 (Knowledge
Freshness — state machine).
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import Evidence, KnowledgeState


__all__ = [
    "ProvenancePort",
    "ProvenanceError",
    "ProvenanceEvent",
]


class ProvenanceError(RuntimeError):
    """Raised when a provenance transition violates the state
    machine or the evidence chain is broken."""


@dataclass(frozen=True)
class ProvenanceEvent:
    entity_id: str
    from_state: KnowledgeState
    to_state: KnowledgeState
    evidence_hash: str
    evidence: Mapping[str, object]


class ProvenancePort(abc.ABC):
    """Abstract provenance / KnowledgeState port."""

    @abc.abstractmethod
    def transition(
        self, entity_id: str, *, from_state: KnowledgeState,
        to_state: KnowledgeState,
        evidence: Mapping[str, object],
    ) -> None: ...

    @abc.abstractmethod
    def current_state(self, entity_id: str) -> Optional[KnowledgeState]: ...

    @abc.abstractmethod
    def evidence(self, entity_id: str) -> Sequence[Evidence]: ...

    @abc.abstractmethod
    def staleness_map(self) -> Mapping[str, KnowledgeState]: ...

    @abc.abstractmethod
    def events(self, entity_id: str) -> Sequence[ProvenanceEvent]: ...