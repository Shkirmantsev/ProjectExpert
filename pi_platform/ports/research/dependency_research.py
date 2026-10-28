"""The dependency research port.

Every transport (MCP, A2A, CLI) calls the same service through this
port. A handler validates and translates; it never implements its own
resolver.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional, Sequence

from pi_platform.core.research.policy import ResearchLimits
from pi_platform.core.research.records import ResearchResult

__all__ = [
    "DependencyTreeRequest",
    "DependencySearchRequest",
    "DependencyReadRequest",
    "DependencyAcquireRequest",
    "DependencyResearchPort",
]


@dataclass(frozen=True)
class DependencyTreeRequest:
    """A request for the dependency graph of a project or package."""

    ecosystem: str
    package: Optional[str] = None
    environment: str = "default"
    scopes: tuple[str, ...] = ()
    limits: ResearchLimits = field(default_factory=ResearchLimits)
    cursor: Optional[str] = None


@dataclass(frozen=True)
class DependencySearchRequest:
    """A request for symbols inside one dependency."""

    ecosystem: str
    package_ref: str
    query: str
    limit: int = 20
    limits: ResearchLimits = field(default_factory=ResearchLimits)
    cursor: Optional[str] = None


@dataclass(frozen=True)
class DependencyReadRequest:
    """A request for a bounded excerpt of library code.

    ``evidence_ref`` names a member of an acquired artifact. The
    explicit ``artifact``/``member`` pair is the alternative used when
    the caller already knows the artifact.
    """

    evidence_ref: str = ""
    artifact: Optional[str] = None
    member: Optional[str] = None
    symbol: Optional[str] = None
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    max_bytes: Optional[int] = None
    limits: ResearchLimits = field(default_factory=ResearchLimits)


@dataclass(frozen=True)
class DependencyAcquireRequest:
    """A request to download one exact dependency artifact."""

    ecosystem: str
    name: str
    version: str
    source_id: str
    limits: ResearchLimits = field(default_factory=ResearchLimits)


class DependencyResearchPort(abc.ABC):
    """The language-neutral dependency research service."""

    @abc.abstractmethod
    def tree(self, request: DependencyTreeRequest) -> ResearchResult: ...

    @abc.abstractmethod
    def search(self, request: DependencySearchRequest) -> ResearchResult: ...

    @abc.abstractmethod
    def read(self, request: DependencyReadRequest) -> ResearchResult: ...

    @abc.abstractmethod
    def acquire(self, request: DependencyAcquireRequest) -> ResearchResult: ...

    @abc.abstractmethod
    def capabilities(self) -> dict:
        """Describe what this deployment can actually research."""
