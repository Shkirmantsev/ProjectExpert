"""MCP server :class:`ToolContext` factory (Change Package I).

The v0.8 refinement adds the ``PI_MCP_DEBUG=1`` activation path
documented in the agent skill and the MCP server error messages.
This module ships the :func:`build_default_tool_context` factory
that:

* reads the ``PI_MCP_DEBUG`` env var to default
  :attr:`ToolContext.debug_mode`;
* constructs an
  :class:`~pi_platform.adapters.retrieval.in_memory_trace_store.InMemoryRetrievalTraceStore`
  when debug mode is on, so the
  ``project.get_retrieval_trace(trace_id)`` tool has a backing
  store out of the box;
* wires the default production adapters for the rest of the
  :class:`ToolContext` ports (readiness, capability discovery,
  retrieval pipeline, orchestrator, task-context builder, etc.)
  so the factory is usable as the entry point for an MCP server
  process.

Operators can override any port by passing it to the factory; the
defaults are the production ones documented in
``pi_platform/cli/main.py::_cmd_retrieval_status`` so behaviour
stays consistent between the MCP server and the CLI status
command.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from pi_platform.adapters.orchestration.capability_discovery import (
    DefaultCapabilityDiscoveryAdapter,
)
from pi_platform.adapters.orchestration.query_orchestrator import (
    DefaultQueryOrchestratorAdapter,
)
from pi_platform.adapters.orchestration.stub_local_llm import (
    StubLocalLLMAdapter,
)
from pi_platform.adapters.orchestration.task_context import (
    DefaultTaskContextBuilderAdapter,
)
from pi_platform.adapters.retrieval.bm25_light_reranker import (
    Bm25LightRerankerAdapter,
)
from pi_platform.adapters.retrieval.context_assembler_adapter import (
    ContextAssemblerAdapter,
)
from pi_platform.adapters.retrieval.hashing_embedding_model import (
    HashingEmbeddingAdapter,
)
from pi_platform.adapters.retrieval.hybrid_retrieval import (
    HybridRetrievalAdapter,
)
from pi_platform.adapters.retrieval.metadata_filter_adapter import (
    MetadataFilterAdapter,
)
from pi_platform.adapters.runtime.graph_expansion import (
    ProductionGraphExpansion,
)
from pi_platform.core.agent_integration.version_compatibility import (
    DefaultVersionCompatibilityPolicy,
)
from pi_platform.core.orchestration.capability_discovery import (
    DefaultCapabilityDiscovery,
)
from pi_platform.core.retrieval.multi_stage_retrieval import (
    MultiStageRetrievalCore,
)
from pi_platform.core.sync.readiness import DefaultKnowledgeReadiness
from pi_platform.core.sync.trusted_approval import HmacTrustedApprovalBoundary
from pi_platform.mcp.server import (
    DEFAULT_SERVER_IDENTITY,
    ToolContext,
)
from pi_platform.ports.agent_integration import (
    CompatibilityRange,
    VersionRange,
)


__all__ = [
    "DEBUG_ENV_VAR",
    "TRUTHY_DEBUG_VALUES",
    "build_default_tool_context",
    "default_debug_mode",
]


# The environment variable name operators set to enable the
# debug-only ``project.get_retrieval_trace(trace_id)`` tool and
# the ``retrieval_trace_id`` field on
# ``project.retrieve_context``. Any value in :data:`TRUTHY_DEBUG_VALUES`
# (case-insensitively) enables the mode; everything else (including
# unset) keeps the public surface unchanged.
DEBUG_ENV_VAR = "PI_MCP_DEBUG"
TRUTHY_DEBUG_VALUES: frozenset[str] = frozenset({
    "1", "true", "yes", "on",
})


def default_debug_mode(env: Optional[dict[str, str]] = None) -> bool:
    """Return the debug-mode flag implied by the environment.

    ``env`` defaults to :data:`os.environ`; callers can pass a
    custom mapping for unit tests. The check is case-insensitive
    and treats the absence of the variable as ``False`` so the
    default is the public, debug-free surface.
    """

    source = env if env is not None else os.environ
    value = str(source.get(DEBUG_ENV_VAR, "") or "").strip().lower()
    return value in TRUTHY_DEBUG_VALUES


# -- internal helpers -----------------------------------------------------


class _NoOpGraphAdapter:
    """In-memory graph stub used by the default retrieval pipeline.

    The default MCP context wires the production graph expansion
    port against this stub when no real Phase 3 graph is
    available; tests can replace the wiring explicitly.
    """

    def expand(self, seeds, *, hops, edge_types, budget):
        from pi_platform.ports.runtime.graph_expansion import (
            GraphExpansion,
        )
        return GraphExpansion(
            seeds=tuple(seeds), expandedEntities=(),
            expandedRelations=(), hops=hops, budget_exhausted=False,
        )

    def stats(self) -> dict:
        return {}


def _default_retrieval_pipeline() -> tuple[
    MultiStageRetrievalCore,
    HybridRetrievalAdapter,
    ContextAssemblerAdapter,
]:
    """Build a safe zero-network retrieval pipeline.

    The pipeline uses the hashing embedding adapter, the BM25-light
    reranker, the default metadata filter and the default context
    assembler so the server can answer basic ``project.search`` /
    ``project.retrieve_context`` calls without external models.
    Operators running a real production deployment should override
    these ports with the real adapters.
    """

    hybrid = HybridRetrievalAdapter(
        dense_query=lambda text, k: (),
        sparse_query=lambda text, k: (),
    )
    pipeline = MultiStageRetrievalCore(
        hybrid=hybrid,
        metadata=MetadataFilterAdapter(),
        graph_expansion=ProductionGraphExpansion(_NoOpGraphAdapter()),
        reranker=Bm25LightRerankerAdapter(),
        context_assembler=ContextAssemblerAdapter(),
    )
    return pipeline, hybrid, ContextAssemblerAdapter()


# -- public factory -------------------------------------------------------


def build_default_tool_context(
    *, debug_mode: Optional[bool] = None,
    trace_store: "object | None" = None,
    repo_root: Optional[Path] = None,
    cache_root: Optional[Path] = None,
    env: Optional[dict[str, str]] = None,
    boundary: "object | None" = None,
    version_policy: "object | None" = None,
    multi_stage_retrieval: "object | None" = None,
    hybrid_retrieval: "object | None" = None,
    context_assembler: "object | None" = None,
    orchestrator: "object | None" = None,
    task_context_builder: "object | None" = None,
    capability_discovery: "object | None" = None,
    readiness: "object | None" = None,
) -> ToolContext:
    """Build a production-default :class:`ToolContext`.

    Parameters
    ----------
    debug_mode:
        Explicit override for the debug-mode flag. When ``None``
        the value comes from :func:`default_debug_mode`.
    trace_store:
        Explicit override for the retrieval trace store. When
        ``None`` and ``debug_mode`` is truthy, the factory builds
        an in-memory store; otherwise no store is attached.
    repo_root, cache_root:
        Optional repository / cache roots surfaced to the
        materialise / refresh_sources tools.
    env:
        Optional environment mapping for :func:`default_debug_mode`
        (test seam).
    boundary, version_policy, multi_stage_retrieval,
    hybrid_retrieval, context_assembler, orchestrator,
    task_context_builder, capability_discovery, readiness:
        Optional overrides for any individual port. The factory
        defaults are the production adapters from
        :mod:`pi_platform.adapters` so a bare
        ``build_default_tool_context()`` call yields a working
        server.
    """

    effective_debug = (
        default_debug_mode(env) if debug_mode is None else bool(debug_mode)
    )
    if trace_store is None and effective_debug:
        from pi_platform.adapters.retrieval.in_memory_trace_store import (
            InMemoryRetrievalTraceStore,
        )
        trace_store = InMemoryRetrievalTraceStore()
    if multi_stage_retrieval is None or hybrid_retrieval is None:
        if (context_assembler is None
                or multi_stage_retrieval is None
                or hybrid_retrieval is None):
            default_pipeline, default_hybrid, default_assembler = (
                _default_retrieval_pipeline()
            )
            multi_stage_retrieval = (
                multi_stage_retrieval or default_pipeline
            )
            hybrid_retrieval = hybrid_retrieval or default_hybrid
            context_assembler = context_assembler or default_assembler
    if orchestrator is None:
        orchestrator = DefaultQueryOrchestratorAdapter(
            retrieval=multi_stage_retrieval,
            local_llm=StubLocalLLMAdapter(),
            task_context_builder=(
                task_context_builder
                or DefaultTaskContextBuilderAdapter()
            ),
        )
    if task_context_builder is None:
        task_context_builder = DefaultTaskContextBuilderAdapter()
    if capability_discovery is None:
        capability_discovery = DefaultCapabilityDiscoveryAdapter(
            local_llm=StubLocalLLMAdapter(),
        )
    if readiness is None:
        readiness = DefaultKnowledgeReadiness()
    if boundary is None:
        # The default boundary uses an ephemeral HMAC key
        # generated for this process; operators wiring the
        # production server should pass the persistent boundary
        # explicitly so the approval IDs survive a restart.
        import secrets
        boundary = HmacTrustedApprovalBoundary(key=secrets.token_bytes(32))
    if version_policy is None:
        # The default range is the v0.8 server identity with a
        # permissive envelope (any 0.x / 1.x) so the policy lets
        # a fresh operator connect without a per-deployment
        # manifest. Operators wiring a locked-down server should
        # pass an explicit ``version_policy`` built from the
        # distribution manifest.
        version_policy = DefaultVersionCompatibilityPolicy(
            range_=CompatibilityRange(
                platform_version=VersionRange("0.0.0", "2.0.0"),
                mcp_api_version=VersionRange("1.0.0", "2.0.0"),
                knowledge_schema_version=VersionRange(
                    "0.7.0", "1.0.0",
                ),
                skill_version=VersionRange("1.0.0", "2.0.0"),
                okf_profile_set=("0.2",),
                plugin_distribution_schema=("1",),
            ),
        )
    return ToolContext(
        readiness=readiness,
        capability_discovery=capability_discovery,
        orchestrator=orchestrator,
        task_context_builder=task_context_builder,
        multi_stage_retrieval=multi_stage_retrieval,
        hybrid_retrieval=hybrid_retrieval,
        context_assembler=context_assembler,
        boundary=boundary,
        version_policy=version_policy,
        server_identity=dict(DEFAULT_SERVER_IDENTITY),
        repo_root=repo_root,
        cache_root=cache_root,
        trace_store=trace_store,
        debug_mode=effective_debug,
    )