"""Context assembler port for the v0.8 Phase 4 retrieval layer.

Covers architecture section §32 (Context Assembler). The
:class:`ContextAssemblerPort` builds a bounded context bundle from
the multi-stage retrieval pipeline output. The bundle deduplicates
overlapping evidence, enforces a context budget, preserves
citations, prefers authoritative evidence, surfaces conflicts and
exposes uncertainty.

The bundle is the language-passport contract between the Phase 4
retrieval pipeline and the Phase 5 orchestrator / Phase 6 MCP
server.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from pi_platform.core.canonical.value_types import ProjectVersion


__all__ = [
    "ContextBudget",
    "Citation",
    "ContextBundle",
    "ContextAssemblerPort",
    "ContextAssemblerError",
]


class ContextAssemblerError(RuntimeError):
    """Raised when the context assembler cannot build a bundle."""


@dataclass(frozen=True)
class ContextBudget:
    """§32 context budget contract.

    ``tokenLimit`` is the maximum cumulative :attr:`token_estimate`
    the bundle may consume. ``maxHits`` is an optional secondary
    cap (independently enforced) so the assembler cannot return an
    arbitrarily long list of small hits.
    """

    tokenLimit: int
    maxHits: int = 0

    def __post_init__(self) -> None:
        if self.tokenLimit <= 0:
            raise ValueError(
                f"ContextBudget.tokenLimit must be positive, got "
                f"{self.tokenLimit}"
            )
        if self.maxHits < 0:
            raise ValueError(
                f"ContextBudget.maxHits must be non-negative, got "
                f"{self.maxHits}"
            )


@dataclass(frozen=True)
class Citation:
    """§32 citation record; immutable per-bundle shape.

    Citations are the immutable shape the Phase 5 orchestrator and
    the Phase 6 MCP server serialise back to agents.
    """

    chunkId: str
    contentHash: str
    sourceReference: str
    projectVersion: ProjectVersion
    evidenceWeight: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.evidenceWeight <= 1.0:
            raise ValueError(
                f"Citation.evidenceWeight must be in [0.0, 1.0], got "
                f"{self.evidenceWeight}"
            )


@dataclass(frozen=True)
class ContextBundle:
    """§32 bounded context bundle."""

    hits: Sequence[object] = field(default_factory=tuple)
    dedupedEntities: Sequence[object] = field(default_factory=tuple)
    citations: Sequence[Citation] = field(default_factory=tuple)
    authoritativeHits: Sequence[object] = field(default_factory=tuple)
    conflictingHits: Sequence[object] = field(default_factory=tuple)
    uncertainHits: Sequence[object] = field(default_factory=tuple)
    budgetUsed: int = 0
    droppedHits: Sequence[object] = field(default_factory=tuple)
    dropReasons: Sequence[str] = field(default_factory=tuple)
    explanations: Sequence[str] = field(default_factory=tuple)


class ContextAssemblerPort(abc.ABC):
    """Abstract context assembler port."""

    @abc.abstractmethod
    def assemble(
        self, hits: Sequence[object], *, contextBudget: ContextBudget,
        query: object,
    ) -> ContextBundle: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...