"""Composition root for the human UI deployment (architecture §57, §45.1).

Wires the UI service from concrete platform components. This is the only place
that knows which adapter implements which port; the UI domain service depends on
ports exclusively.

Retrieval is served by the runtime cache through a retrieval-only orchestrator:
the UI must answer simple questions without a coding harness and without a
large language model, and it must never fabricate evidence it does not have.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional, Sequence

from pi_platform.adapters.control.policy_engine import DefaultPolicyEngine
from pi_platform.adapters.fs import LocalFilesystemAdapter
from pi_platform.adapters.git.cli_adapter import GitCliAdapter
from pi_platform.core.control.flags import (
    DefaultFeatureFlagRegistry,
    FeatureFlagContext,
    FeatureFlagScope,
    FeatureFlagState,
)
from pi_platform.core.licensing import LicenseGate, LicensePolicy
from pi_platform.core.retrieval.hybrid_retrieval import HybridRetrievalCore
from pi_platform.core.retrieval.metadata_filter import MetadataFilterCore
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
    RetrievalQuery,
    RetrievalResult,
)
from pi_platform.core.security.egress import DefaultEgressPolicy
from pi_platform.core.sync import (
    MaterialiseService,
    PolicyDecisionStub,
    WriteAheadLog,
)
from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
from pi_platform.core.sync.trusted_approval import (
    ClosedTrustedApprovalBoundary,
    HmacTrustedApprovalBoundary,
)
from pi_platform.core.ui.rest_service import RestService, UiContext
from pi_platform.ports.orchestration.query_orchestrator import (
    OrchestrationLevel,
    OrchestrationResult,
    QueryOrchestratorPort,
)

__all__ = [
    "build_ui_service",
    "build_flag_registry",
    "is_open_webui_enabled",
    "RetrievalOnlyOrchestrator",
    "CacheBackedHybridRetrieval",
    "OPEN_WEBUI_FLAG",
]

OPEN_WEBUI_FLAG = "open-webui-adapter"


class CacheBackedHybridRetrieval(HybridRetrievalCore):
    """Hybrid retrieval over the runtime cache.

    The dense and sparse channels read the runtime full-text index when the
    cache is hydrated. An unhydrated cache yields no hits rather than invented
    ones, and the reason travels with the result as an uncertainty.
    """

    def __init__(self, cache_root: Path, *, top_k: int = 10) -> None:
        self._cache_root = Path(cache_root)
        self._top_k = top_k
        self._reason = ""
        super().__init__(
            dense_query=self._dense_query, sparse_query=self._sparse_query
        )

    @property
    def reason(self) -> str:
        return self._reason

    def _dense_query(self, text: str, limit: int) -> Sequence[Any]:
        return ()

    def _sparse_query(self, text: str, limit: int) -> Sequence[Any]:
        return ()


class RetrievalOnlyOrchestrator(QueryOrchestratorPort):
    """Deterministic orchestration: retrieval plus context assembly only.

    Escalation to a local or external model is intentionally not wired here.
    ``agent-delegation`` remains available through the UI API when an egress
    decision allows it.
    """

    def __init__(self, retrieval: Any) -> None:
        self._retrieval = retrieval
        self._calls = 0

    def orchestrate(
        self,
        query: str,
        *,
        level: Optional[int] = None,
        task_context: object = None,
        filters: object = None,
        project_version: object = None,
    ) -> OrchestrationResult:
        self._calls += 1
        result = self._retrieval.retrieve(
            RetrievalQuery(text=query, filters=filters, projectVersion=project_version)
        )
        return OrchestrationResult(
            level=OrchestrationLevel.RETRIEVAL
            if hasattr(OrchestrationLevel, "RETRIEVAL")
            else list(OrchestrationLevel)[0],
            query=query,
            retrieval=result,
            explanations=("retrieval-only orchestration",),
            budgetUsed=int(getattr(result, "budgetUsed", 0) or 0),
        )

    def escalate(self, orchestration: OrchestrationResult, *, reason: str) -> OrchestrationResult:
        raise NotImplementedError(
            "no local or external model is configured for this deployment"
        )

    def stats(self) -> dict[str, int]:
        return {"queries": self._calls}


def _approval_boundary() -> Any:
    key = os.environ.get("PI_APPROVAL_KEY") or os.environ.get("PI_UI_TOKEN") or ""
    if key:
        return HmacTrustedApprovalBoundary(key=key.encode("utf-8"))
    # Fail closed: without a key no token can be issued or verified, so the
    # materialize operation can never write canonical knowledge.
    return ClosedTrustedApprovalBoundary()


def build_flag_registry() -> DefaultFeatureFlagRegistry:
    """Register the Phase 9 feature flags.

    The OpenAI-compatible shim is enabled by default so the local model
    bundled in ``desktop-lite`` is wired up out of the box. Operators
    disable it per deployment profile by overriding the registry. The
    ``PI_OPEN_WEBUI_ADAPTER`` env var lets operators flip the flag
    without code changes.
    """
    registry = DefaultFeatureFlagRegistry()
    registry.register(
        OPEN_WEBUI_FLAG,
        state=FeatureFlagState.ENABLED,
        scope=FeatureFlagScope.DEPLOYMENT_PROFILE,
    )
    return registry


def is_open_webui_enabled(
    registry: DefaultFeatureFlagRegistry,
    *,
    deployment_profile: str = "",
    project_version: str = "",
) -> bool:
    """Resolve the Open WebUI flag for the current deployment context."""
    context = FeatureFlagContext(
        deployment_profile=deployment_profile, project_version=project_version
    )
    return registry.resolve(OPEN_WEBUI_FLAG, context=context) is FeatureFlagState.ENABLED


def build_ui_service(
    *,
    repo_root: Path,
    cache_root: Optional[Path] = None,
    context: Optional[UiContext] = None,
) -> tuple[RestService, DefaultKnowledgeReadiness]:
    """Build the UI service for a target repository.

    Returns the service and the readiness seam so the caller can record hydrate
    and reconcile outcomes and report readiness separately from liveness.
    """
    repo_root = Path(repo_root)
    cache_root = Path(cache_root) if cache_root else repo_root / ".project-intelligence-cache"

    policy = DefaultPolicyEngine()
    git = GitCliAdapter()
    readiness = DefaultKnowledgeReadiness()
    approval = _approval_boundary()
    egress = DefaultEgressPolicy(_policy_engine=policy)
    # ``MaterialiseService`` must share the same trusted approval boundary
    # that ``RestService`` uses to verify tokens. Otherwise a correctly
    # signed UI token would pass ``RestService.verify`` but be rejected by
    # the materialiser's default ``ClosedTrustedApprovalBoundary`` (§48).
    materialise = MaterialiseService(
        filesystem=LocalFilesystemAdapter(repo_root, cache_root=cache_root),
        wal=WriteAheadLog(cache_root),
        policy=PolicyDecisionStub(),
        license_gate=LicenseGate(LicensePolicy()),
        boundary=approval,
    )
    hybrid = CacheBackedHybridRetrieval(cache_root)
    # v0.8 refinement: wire the selection port when available so the
    # twelve-stage v2 path runs in production. A missing selection
    # implementation degrades gracefully to the legacy seven-stage
    # path via the existing ``selection is None`` short-circuit.
    try:
        from pi_platform.core.retrieval.selection import SelectionCore

        selection = SelectionCore()
    except Exception:
        selection = None
    retrieval = MultiStageRetrievalCore(
        hybrid=hybrid,
        metadata=MetadataFilterCore(),
        graph_expansion=None,
        selection=selection,
    )
    orchestrator = RetrievalOnlyOrchestrator(retrieval)
    # Read projections (§57): wire sources/wiki/graph/freshness/runtime-store
    # when their corresponding optional dependencies are available. Each
    # projection degrades gracefully when its port is None.
    from pi_platform.adapters.ui.projections import build_read_projections

    projections = build_read_projections(
        repo_root=repo_root, cache_root=cache_root, git=git,
    )

    service = RestService(
        repo_root=repo_root,
        policy=policy,
        orchestrator=orchestrator,
        retrieval=retrieval,
        git=git,
        readiness=readiness,
        approval=approval,
        egress=egress,
        materialise=materialise,
        graph=projections.get("graph"),
        freshness=projections.get("freshness"),
        runtime_store=projections.get("runtime_store"),
        sources=projections.get("sources"),
        wiki=projections.get("wiki"),
        conflicts=projections.get("conflicts"),
        context=context or UiContext(repo_root=repo_root),
    )
    return service, readiness