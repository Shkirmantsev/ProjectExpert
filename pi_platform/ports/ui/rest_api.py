"""Language-neutral UI API contracts (architecture §57, §44.3).

The UI-facing surface is deliberately expressed as ports and value types so a
REST frontend, a desktop frontend or an Open WebUI shim can all be replaceable
adapters over the same platform core. This module must stay free of transport,
HTTP and framework concerns.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

#: The ten §44.3 UI API operations. Order is the documented contract order.
UI_OPERATIONS: tuple[str, ...] = (
    "query",
    "retrieve",
    "sources",
    "graph",
    "wiki",
    "project-version",
    "indexing-status",
    "knowledge-status",
    "materialize",
    "agent-delegation",
)


@dataclass(frozen=True)
class UiActor:
    """Authenticated caller identity presented to the policy engine."""

    actor_type: str
    actor_id: str
    role: str


@dataclass(frozen=True)
class QueryRequest:
    text: str
    top_k: int = 10
    filters: Optional[Mapping[str, Any]] = None
    context_budget: int = 2000


@dataclass(frozen=True)
class RetrieveRequest:
    text: str
    top_k: int = 10
    filters: Optional[Mapping[str, Any]] = None
    context_budget: int = 2000


@dataclass(frozen=True)
class GraphRequest:
    entity: str
    depth: int = 1


@dataclass(frozen=True)
class WikiRequest:
    query: Optional[str] = None
    id: Optional[str] = None


@dataclass(frozen=True)
class MaterializeRequest:
    approval_token: Optional[str] = None


@dataclass(frozen=True)
class AgentDelegationRequest:
    task: str
    target: Optional[str] = None


@dataclass(frozen=True)
class QueryResult:
    mode: str
    results: Sequence[Any] = ()
    provenance: Sequence[Any] = ()
    answer: Optional[str] = None
    explanations: Sequence[str] = ()
    budget_used: int = 0


@dataclass(frozen=True)
class RetrieveResult:
    results: Sequence[Any] = ()
    context: Optional[Any] = None
    conflicts: Sequence[Any] = ()
    uncertainties: Sequence[Any] = ()
    budget_used: int = 0


@dataclass(frozen=True)
class SourceRecord:
    id: str
    kind: str
    policy: str
    freshness: str
    uri: str = ""
    content_hash: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SourcesResult:
    sources: Sequence[SourceRecord] = ()


@dataclass(frozen=True)
class GraphResult:
    nodes: Sequence[Any] = ()
    edges: Sequence[Any] = ()


@dataclass(frozen=True)
class WikiResult:
    documents: Sequence[Any] = ()


@dataclass(frozen=True)
class ProjectVersionResult:
    repo: str
    head: str
    branch: Optional[str] = None
    fingerprint: str = ""
    knowledge_schema_version: str = ""
    embedding_model_version: str = ""
    index_schema_version: str = ""


@dataclass(frozen=True)
class IndexingStatusResult:
    ready: bool
    hydration: Mapping[str, Any] = field(default_factory=dict)
    indexes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeStatusResult:
    stale: Sequence[Any] = ()
    conflicts: Sequence[Any] = ()


@dataclass(frozen=True)
class MaterializeResult:
    materialized: bool
    files: Sequence[str] = ()
    okf_validation_errors: Sequence[str] = ()
    reason: str = ""


@dataclass(frozen=True)
class AgentDelegationResult:
    status: str
    result: Optional[Any] = None
    reason: str = ""


class SourceCatalogPort(abc.ABC):
    """Read-only projection of configured knowledge sources.

    Source discovery is a presentation concern for the UI; the ingestion
    pipeline remains the owner of parsing and import.
    """

    @abc.abstractmethod
    def list_sources(self) -> Sequence[SourceRecord]:
        """Return every configured source with its policy and freshness."""


class WikiReadPort(abc.ABC):
    """Read-only projection of the canonical Wiki layer."""

    @abc.abstractmethod
    def read(
        self, *, query: Optional[str] = None, id: Optional[str] = None
    ) -> Sequence[Any]:
        """Return Wiki documents for a query or a stable document id."""


class ConflictsPort(abc.ABC):
    """Read-only projection of recorded knowledge conflicts."""

    @abc.abstractmethod
    def conflicts(self) -> Sequence[Any]:
        """Return known conflicting knowledge facts."""


class RestApiPort(abc.ABC):
    """The §44.3 UI API surface exposed by the platform."""

    @classmethod
    def operations(cls) -> tuple[str, ...]:
        """Return the documented UI operations (always the §44.3 set)."""
        return UI_OPERATIONS

    @abc.abstractmethod
    def query(self, actor: UiActor, request: QueryRequest) -> QueryResult:
        """Ask a project question through the query orchestrator."""

    @abc.abstractmethod
    def retrieve(self, actor: UiActor, request: RetrieveRequest) -> RetrieveResult:
        """Run deterministic retrieval and context assembly."""

    @abc.abstractmethod
    def sources(self, actor: UiActor) -> SourcesResult:
        """List configured knowledge sources."""

    @abc.abstractmethod
    def graph(self, actor: UiActor, request: GraphRequest) -> GraphResult:
        """Expand project relations around an entity."""

    @abc.abstractmethod
    def wiki(self, actor: UiActor, request: WikiRequest) -> WikiResult:
        """Browse canonical Wiki knowledge."""

    @abc.abstractmethod
    def project_version(self, actor: UiActor) -> ProjectVersionResult:
        """Report the current Git-backed project version."""

    @abc.abstractmethod
    def indexing_status(self, actor: UiActor) -> IndexingStatusResult:
        """Report hydration readiness and index state."""

    @abc.abstractmethod
    def knowledge_status(self, actor: UiActor) -> KnowledgeStatusResult:
        """Report stale and conflicting knowledge."""

    @abc.abstractmethod
    def materialize(
        self, actor: UiActor, request: MaterializeRequest
    ) -> MaterializeResult:
        """Materialise approved durable knowledge."""

    @abc.abstractmethod
    def agent_delegation(
        self, actor: UiActor, request: AgentDelegationRequest
    ) -> AgentDelegationResult:
        """Delegate a complex task through the orchestrator under egress control."""


__all__ = [
    "UI_OPERATIONS",
    "UiActor",
    "QueryRequest",
    "RetrieveRequest",
    "GraphRequest",
    "WikiRequest",
    "MaterializeRequest",
    "AgentDelegationRequest",
    "QueryResult",
    "RetrieveResult",
    "SourceRecord",
    "SourcesResult",
    "GraphResult",
    "WikiResult",
    "ProjectVersionResult",
    "IndexingStatusResult",
    "KnowledgeStatusResult",
    "MaterializeResult",
    "AgentDelegationResult",
    "SourceCatalogPort",
    "WikiReadPort",
    "ConflictsPort",
    "RestApiPort",
]
