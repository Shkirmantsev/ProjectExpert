"""Core UI service (architecture §57, §44.3).

The service owns the UI operation semantics and the security composition order:

``authentication (adapter)`` -> ``policy authorisation`` -> ``capability gate``

``materialize`` additionally requires a valid trusted-approval token and writes
nothing without one; ``agent-delegation`` additionally requires an ALLOW egress
decision before the orchestrator is allowed to delegate.

The module imports ports only. Transport concerns belong to
``pi_platform/adapters/ui``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from pi_platform.core.security.egress import EgressRequest
from pi_platform.ports import (
    ApprovalRequest,
    GitPort,
    KnowledgeReadinessPort,
    MaterialisePort,
    TrustedApprovalBoundary,
)
from pi_platform.ports.control.policy import (
    Capability,
    Decision,
    PolicyEnginePort,
    PolicyRequest,
    Role,
)
from pi_platform.ports.orchestration.query_orchestrator import QueryOrchestratorPort
from pi_platform.ports.retrieval import MetadataFilter
from pi_platform.ports.retrieval.multi_stage_retrieval import MultiStageRetrievalPort
from pi_platform.ports.runtime import (
    FreshnessTrackerPort,
    GraphExpansionPort,
    RuntimeStorePort,
)
from pi_platform.ports.ui.rest_api import (
    AgentDelegationRequest,
    AgentDelegationResult,
    ConflictsPort,
    GraphRequest,
    GraphResult,
    IndexingStatusResult,
    KnowledgeStatusResult,
    MaterializeRequest,
    MaterializeResult,
    ProjectVersionResult,
    QueryRequest,
    QueryResult,
    RetrieveRequest,
    RetrieveResult,
    RestApiPort,
    SourceCatalogPort,
    SourcesResult,
    UiActor,
    WikiReadPort,
    WikiRequest,
    WikiResult,
)

#: UI operation -> control-plane capability. Unknown operations never appear here
#: and are therefore denied by default.
OPERATION_CAPABILITIES: Mapping[str, Capability] = {
    "query": Capability.RETRIEVAL_QUERY,
    "retrieve": Capability.RETRIEVAL_QUERY,
    "sources": Capability.SOURCE_READ,
    "graph": Capability.GRAPH_READ,
    "wiki": Capability.KNOWLEDGE_READ,
    "project-version": Capability.GIT_READ,
    "indexing-status": Capability.KNOWLEDGE_READ,
    "knowledge-status": Capability.KNOWLEDGE_READ,
    "materialize": Capability.KNOWLEDGE_MATERIALIZE,
    "agent-delegation": Capability.AGENT_DELEGATE,
}


class UiOperationDenied(RuntimeError):
    """Raised when the policy engine or a capability gate refuses an operation.

    The HTTP adapter maps this to a refusal response; no partial work has been
    performed when it is raised.
    """

    def __init__(self, operation: str, reason: str):
        super().__init__(f"{operation} denied: {reason}")
        self.operation = operation
        self.reason = reason


@dataclass(frozen=True)
class UiContext:
    """Runtime context shared by every UI operation."""

    repo_root: Path
    project_version: str = ""
    egress_classification: str = "INTERNAL"


def _as_metadata_filter(
    filters: Optional[Mapping[str, Any]],
) -> Optional[MetadataFilter]:
    """Pass an already-typed filter through; never coerce a raw mapping.

    Transport adapters own request parsing, so the core only forwards a filter
    that a caller has already constructed as a ``MetadataFilter``.
    """
    return filters if isinstance(filters, MetadataFilter) else None


def _stale_facts(snapshot: Any) -> Sequence[Any]:
    facts = getattr(snapshot, "facts", ()) or ()
    stale = []
    for fact in facts:
        state = getattr(fact, "state", None) or getattr(fact, "status", None)
        if state is not None and str(state).upper().endswith("STALE"):
            stale.append(fact)
    return tuple(stale)


class RestService(RestApiPort):
    """Domain implementation of the ten §44.3 UI operations."""

    def __init__(
        self,
        *,
        repo_root: Path,
        policy: PolicyEnginePort,
        orchestrator: QueryOrchestratorPort,
        retrieval: MultiStageRetrievalPort,
        git: GitPort,
        readiness: KnowledgeReadinessPort,
        approval: TrustedApprovalBoundary,
        egress: Any,
        materialise: Optional[MaterialisePort] = None,
        graph: Optional[GraphExpansionPort] = None,
        freshness: Optional[FreshnessTrackerPort] = None,
        runtime_store: Optional[RuntimeStorePort] = None,
        capability_discovery: Optional[Any] = None,
        sources: Optional[SourceCatalogPort] = None,
        wiki: Optional[WikiReadPort] = None,
        conflicts: Optional[ConflictsPort] = None,
        context: Optional[UiContext] = None,
    ) -> None:
        # Approval tokens bind the canonical repository path. Use the same
        # identity as MaterialiseService, including Windows path casing.
        self._repo_root = Path(repo_root).resolve()
        self._policy = policy
        self._orchestrator = orchestrator
        self._retrieval = retrieval
        self._git = git
        self._readiness = readiness
        self._approval = approval
        self._egress = egress
        self._materialise = materialise
        self._graph = graph
        self._freshness = freshness
        self._runtime_store = runtime_store
        self._capabilities = capability_discovery
        self._sources = sources
        self._wiki = wiki
        self._conflicts = conflicts
        self._context = context or UiContext(repo_root=self._repo_root)

    # ------------------------------------------------------------------
    # security composition
    # ------------------------------------------------------------------
    def _authorise(
        self,
        operation: str,
        actor: UiActor,
        *,
        approval_token: Optional[str] = None,
    ) -> None:
        capability = OPERATION_CAPABILITIES.get(operation)
        if capability is None:
            raise UiOperationDenied(operation, "unknown operation")
        try:
            role = Role(actor.role)
        except ValueError:
            raise UiOperationDenied(operation, f"unknown role {actor.role!r}") from None
        request = PolicyRequest(
            actor_type=actor.actor_type,
            actor_id=actor.actor_id,
            role=role,
            capability=capability,
            resource=operation,
            project_version=self._context.project_version,
            correlation_id=operation,
            approval_token=approval_token,
        )
        decision = self._policy.evaluate(request)
        outcome = getattr(decision, "decision", decision)
        if outcome is Decision.ALLOW:
            return
        if outcome is Decision.REQUIRE_APPROVAL:
            if not approval_token:
                raise UiOperationDenied(operation, "approval required")
            authorize = getattr(self._policy, "authorize", None)
            if authorize is None:
                raise UiOperationDenied(operation, "approval cannot be verified")
            authorize(request)  # raises PolicyDenied when the token is invalid
            return
        raise UiOperationDenied(operation, "policy denied")

    # ------------------------------------------------------------------
    # read operations
    # ------------------------------------------------------------------
    def query(self, actor: UiActor, request: QueryRequest) -> QueryResult:
        self._authorise("query", actor)
        result = self._orchestrator.orchestrate(
            request.text, filters=_as_metadata_filter(request.filters)
        )
        retrieval = getattr(result, "retrieval", None)
        hits = tuple(getattr(retrieval, "hits", ()) or ()) if retrieval else ()
        level = getattr(result, "level", None)
        return QueryResult(
            mode=str(getattr(level, "name", level) or "unknown"),
            results=hits,
            provenance=hits,
            answer=getattr(result, "llm_completion", None),
            explanations=tuple(getattr(result, "explanations", ()) or ()),
            budget_used=int(getattr(result, "budgetUsed", 0) or 0),
        )

    def retrieve(self, actor: UiActor, request: RetrieveRequest) -> RetrieveResult:
        self._authorise("retrieve", actor)
        from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery

        result = self._retrieval.retrieve(
            RetrievalQuery(
                text=request.text,
                top_k=request.top_k,
                contextBudget=request.context_budget,
                filters=_as_metadata_filter(request.filters),
            )
        )
        return RetrieveResult(
            results=tuple(getattr(result, "hits", ()) or ()),
            context=getattr(result, "contextBundle", None),
            conflicts=tuple(getattr(result, "conflicts", ()) or ()),
            uncertainties=tuple(getattr(result, "uncertainties", ()) or ()),
            budget_used=int(getattr(result, "budgetUsed", 0) or 0),
        )

    def sources(self, actor: UiActor) -> SourcesResult:
        self._authorise("sources", actor)
        if self._sources is None:
            return SourcesResult()
        return SourcesResult(sources=tuple(self._sources.list_sources()))

    def graph(self, actor: UiActor, request: GraphRequest) -> GraphResult:
        self._authorise("graph", actor)
        if self._graph is None:
            return GraphResult()
        expansion = self._graph.expand([request.entity], hops=max(1, request.depth))
        return GraphResult(
            nodes=tuple(getattr(expansion, "expandedEntities", ()) or ()),
            edges=tuple(getattr(expansion, "expandedRelations", ()) or ()),
        )

    def wiki(self, actor: UiActor, request: WikiRequest) -> WikiResult:
        self._authorise("wiki", actor)
        if self._wiki is None:
            return WikiResult()
        return WikiResult(documents=tuple(self._wiki.read(query=request.query, id=request.id)))

    def project_version(self, actor: UiActor) -> ProjectVersionResult:
        self._authorise("project-version", actor)
        head = self._git.head(self._repo_root)
        branch = self._git.current_branch(self._repo_root)
        descriptor = (
            self._capabilities.describe() if self._capabilities is not None else None
        )
        return ProjectVersionResult(
            repo=str(self._repo_root),
            head=head,
            branch=branch,
            fingerprint=self._context.project_version,
            knowledge_schema_version=str(
                getattr(descriptor, "knowledgeSchemaVersion", "") or ""
            ),
            embedding_model_version=str(
                getattr(descriptor, "embeddingModelVersion", "") or ""
            ),
            index_schema_version=str(
                getattr(descriptor, "runtimeIndexSchemaVersion", "") or ""
            ),
        )

    def indexing_status(self, actor: UiActor) -> IndexingStatusResult:
        self._authorise("indexing-status", actor)
        snapshot = self._readiness.snapshot()
        hydration = {
            "consistent": bool(getattr(snapshot, "consistent", False)),
            "in_progress": bool(getattr(snapshot, "in_progress", False)),
            "current_head": str(getattr(snapshot, "current_head", "") or ""),
            "last_hydrate_at": int(getattr(snapshot, "last_hydrate_at", 0) or 0),
            "reason": str(getattr(snapshot, "reason", "") or ""),
        }
        indexes: Mapping[str, Any] = {}
        if self._runtime_store is not None:
            report = self._runtime_store.runtime_status()
            indexes = {
                "backend": str(getattr(report, "backend", "") or ""),
                "cache_entries": int(getattr(report, "cache_entries", 0) or 0),
                "bound_version": str(getattr(report, "bound_version", "") or ""),
                "wal_tail_length": int(getattr(report, "wal_tail_length", 0) or 0),
            }
        retrieval_stats = getattr(self._retrieval, "stats", None)
        if retrieval_stats is not None:
            indexes = {**indexes, "retrieval": dict(retrieval_stats())}
        ready = hydration["consistent"] and not hydration["in_progress"]
        return IndexingStatusResult(ready=ready, hydration=hydration, indexes=indexes)

    def knowledge_status(self, actor: UiActor) -> KnowledgeStatusResult:
        self._authorise("knowledge-status", actor)
        stale = _stale_facts(self._freshness.snapshot()) if self._freshness else ()
        conflicts = tuple(self._conflicts.conflicts()) if self._conflicts else ()
        return KnowledgeStatusResult(stale=stale, conflicts=conflicts)

    # ------------------------------------------------------------------
    # write and delegation operations
    # ------------------------------------------------------------------
    def materialize(
        self, actor: UiActor, request: MaterializeRequest
    ) -> MaterializeResult:
        token = request.approval_token
        self._authorise("materialize", actor, approval_token=token)
        if self._materialise is None:
            raise UiOperationDenied("materialize", "materialisation unavailable")
        if not token:
            # Fail closed: no approval token means no canonical write at all.
            raise UiOperationDenied("materialize", "approval token required")
        self._approval.verify(
            ApprovalRequest(action="materialise", repo_root=str(self._repo_root)),
            token,
        )
        report = self._materialise.materialise_durable_changes(
            self._repo_root,
            cache_root=self._repo_root / ".project-intelligence-cache",
            approval_token=token,
        )
        okf_errors = tuple(getattr(report, "okf_validation_errors", ()) or ())
        if okf_errors:
            return MaterializeResult(
                materialized=False,
                files=(),
                okf_validation_errors=okf_errors,
                reason="okf validation failed",
            )
        return MaterializeResult(
            materialized=True, files=tuple(getattr(report, "diff_files", ()) or ())
        )

    def agent_delegation(
        self, actor: UiActor, request: AgentDelegationRequest
    ) -> AgentDelegationResult:
        self._authorise("agent-delegation", actor)
        decision = self._egress.evaluate(
            EgressRequest(
                url=request.target or "",
                classification=self._context.egress_classification,
                actor_role=Role(actor.role),
                capability_requested="agent.delegate",
                correlation_id="agent-delegation",
                resource=request.target or "local",
            )
        )
        if not getattr(decision, "allowed", False):
            return AgentDelegationResult(
                status="denied", reason=str(getattr(decision, "rationale", "") or "")
            )
        if self._orchestrator is None:
            return AgentDelegationResult(status="unavailable", reason="no orchestrator")
        result = self._orchestrator.orchestrate(request.task, level=2)
        return AgentDelegationResult(
            status="delegated",
            result=getattr(result, "llm_completion", None) or result,
        )


__all__ = [
    "OPERATION_CAPABILITIES",
    "UiContext",
    "UiOperationDenied",
    "RestService",
]
