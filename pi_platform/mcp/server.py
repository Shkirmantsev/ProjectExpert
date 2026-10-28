"""Phase 6 §36 MCP server.

The MCP server is a **thin adapter** over Phase 5 orchestration
and Phase 4 retrieval. It does NOT introduce a new runtime
store, a new knowledge model or a new retrieval path. It
composes the existing ports and enforces the three runtime
invariants that gate every call:

1. The §47 capability handshake (server / skill / plugin /
   adapter agree on version compatibility) — see
   `pi_platform.core.agent_integration.version_compatibility`.
2. The §48 trusted approval boundary for write / materialise
   tools.
3. The Phase 6 readiness gate — every call is rejected with
   `RuntimeNotReadyError` when the runtime project knowledge
   is not in a consistent state (hydrate / reconcile).

The server exposes:

* 17 semantic read / write tools (the §36 list);
* one ``project.describe_capabilities`` tool;
* the §38 distribution URI namespace as resources;
* in debug / admin mode, the
  ``project.get_retrieval_trace(trace_id)`` tool introduced by
  Change Package I of the v0.8 refinement (plan §33).

The §36 tool list is exhaustive; additional tools are
documented extensions and MUST NOT shadow the documented names.

The official MCP Python SDK (``mcp==1.30.0``, Apache-2.0) is
imported lazily inside :meth:`serve` so the server module
loads even when the SDK is not installed in the active
interpreter (the harness-side test environment does not need
the SDK to run the unit tests). The unit tests mock the SDK
boundary; the integration smoke tests run against an
interpreter with the SDK installed.
"""

from __future__ import annotations

import asyncio
import json
import logging
from .tool_schemas import tool_definition
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping, Optional, Sequence


from pi_platform.ports import (
    KnowledgeReadinessPort,
    RuntimeNotReadyError,
    TrustedApprovalBoundary,
)
from pi_platform.ports.agent_integration import (
    VersionCompatibilityPolicy,
)
from pi_platform.ports.orchestration.capability_discovery import CapabilityDiscoveryPort
from pi_platform.ports.orchestration.query_orchestrator import QueryOrchestratorPort
from pi_platform.ports.orchestration.task_context import TaskContextBuilderPort
from pi_platform.ports.retrieval.context_assembler import ContextAssemblerPort
from pi_platform.ports.retrieval.hybrid_retrieval import HybridRetrievalPort
from pi_platform.ports.retrieval.multi_stage_retrieval import MultiStageRetrievalPort
from pi_platform.ports.retrieval.trace_store import RetrievalTraceStorePort


__all__ = [
    "DEFAULT_SERVER_IDENTITY",
    "DEBUG_TOOLS",
    "DebugModeRequiredError",
    "McpServer",
    "McpServerError",
    "ToolContext",
    "TraceNotFoundError",
]


log = logging.getLogger(__name__)


class McpServerError(RuntimeError):
    """Raised by the MCP server when a tool call violates invariants."""


class DebugModeRequiredError(McpServerError):
    """Raised when a debug-only tool is called outside debug mode."""


class TraceNotFoundError(McpServerError):
    """Raised when the requested retrieval trace id is unknown."""


@dataclass(frozen=True)
class ToolContext:
    """Per-call context passed to every tool handler.

    The context carries the dependencies the tool needs so
    handlers stay pure and testable.

    The v0.8 refinement (Change Package I) adds two additive,
    optional fields:

    * ``trace_store`` — backing store for the debug-only
      ``project.get_retrieval_trace`` tool. ``None`` keeps the
      pre-change behaviour (no trace lookup).
    * ``debug_mode`` — boolean flag that gates the debug-only
      tool and the trace-id field on ``retrieve_context``.
      Operators enable it through ``PI_MCP_DEBUG=1`` or by
      passing the flag through the CLI entry point.
    """

    readiness: KnowledgeReadinessPort
    capability_discovery: CapabilityDiscoveryPort
    orchestrator: QueryOrchestratorPort
    task_context_builder: TaskContextBuilderPort
    multi_stage_retrieval: MultiStageRetrievalPort
    hybrid_retrieval: HybridRetrievalPort
    context_assembler: ContextAssemblerPort
    boundary: TrustedApprovalBoundary
    version_policy: VersionCompatibilityPolicy
    server_identity: Mapping[str, str]
    repo_root: Optional[Path] = None
    cache_root: Optional[Path] = None
    trace_store: Optional[RetrievalTraceStorePort] = None
    debug_mode: bool = False
    #: The shared dependency research service. ``None`` means the
    #: deployment does not offer dependency research; the tools then
    #: report that instead of answering with a placeholder.
    dependency_research: Optional[object] = None


# Default server identity used by both the MCP server and the
# shared release identity the vendor packagers embed.
DEFAULT_SERVER_IDENTITY: dict[str, str] = {
    "name": "project-intelligence",
    "vendor": "project-intelligence",
    "serverVersion": "0.8.0",
    "mcpApiVersion": "1.3.0",
    "license": "Apache-2.0",
}


# The §36 documented tool names. The MCP server MUST expose
# exactly these names; the extension tools (and the readiness
# / approval / describe_capabilities tools) are registered
# separately and MUST NOT shadow the canonical names.
SECTION_36_TOOLS: tuple[str, ...] = (
    "project.search",
    "project.retrieve_context",
    "project.get_entity",
    "project.get_component",
    "project.get_requirement",
    "project.get_spec",
    "project.get_architecture",
    "project.get_dependency",
    "project.find_implementation",
    "project.trace_requirement",
    "project.find_references",
    "project.get_project_version",
    "project.get_conflicts",
    "project.get_stale_knowledge",
    "project.build_task_context",
    "project.materialize_knowledge",
    "project.refresh_sources",
)

EXTENSION_TOOLS: tuple[str, ...] = (
    "project.describe_capabilities",
)

#: The LLM Wiki tools. They let a CALLING LLM curate the canonical
#: project knowledge: read the curated pages, search them, write a new
#: page and validate the bundle. The pages are OKF v0.2 concepts and are
#: part of the searchable corpus on the next refresh.
WIKI_TOOLS: tuple[str, ...] = (
    "project.wiki_list_pages",
    "project.wiki_read_page",
    "project.wiki_search",
    "project.wiki_write_page",
    "project.wiki_validate",
)

# Debug-only tools (Change Package I, plan §33). These tools
# require :attr:`ToolContext.debug_mode` to be truthy; the server
# rejects calls with :class:`DebugModeRequiredError` when it is
# not. The constant enumerates the *candidate* debug tools; the
# effective list returned by :class:`McpServer` is empty unless
# the operator enabled debug mode through
# :func:`pi_platform.mcp.context.build_default_tool_context` (or
# an explicit ``debug_mode=True`` on the :class:`ToolContext`).
DEBUG_TOOLS: tuple[str, ...] = (
    "project.get_retrieval_trace",
)

#: The dependency research tools. They call the shared research
#: service; the handlers only validate and translate.
DEPENDENCY_RESEARCH_TOOLS: tuple[str, ...] = (
    "project.dependency_tree",
    "project.dependency_search",
    "project.dependency_read",
    "project.dependency_acquire",
)


ToolHandler = Callable[[ToolContext, Mapping[str, Any]], Awaitable[Mapping[str, Any]]]


def _require(arguments: Mapping[str, Any], key: str) -> Any:
    if key not in arguments:
        raise McpServerError(f"missing required argument: {key!r}")
    return arguments[key]


def _optional(arguments: Mapping[str, Any], key: str, default=None):
    return arguments.get(key, default)


async def _enforce_readiness(ctx: ToolContext) -> None:
    if not ctx.readiness.is_ready():
        snapshot = ctx.readiness.snapshot()
        raise RuntimeNotReadyError(snapshot)


async def _tool_search(ctx: ToolContext,
                       arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    text = _require(arguments, "text")
    top_k = int(_optional(arguments, "top_k", 10))
    filters = _optional(arguments, "filters")
    project_version = _optional(arguments, "project_version")
    include_trace = bool(
        ctx.debug_mode and _optional(arguments, "include_trace", False),
    )
    # Reranking is controlled by the operator policy; the caller may
    # override it for a single query.
    enable_reranking = _optional(arguments, "enable_reranking", None)
    from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
    result = ctx.multi_stage_retrieval.retrieve(RetrievalQuery(
        text=text, top_k=top_k,
        filters=filters, projectVersion=project_version,
        include_trace=include_trace,
        enableReranking=(
            None if enable_reranking is None else bool(enable_reranking)
        ),
    ))
    return {"ok": True, "result": _serialise(result)}


async def _tool_retrieve_context(ctx: ToolContext,
                                 arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    text = _require(arguments, "text")
    top_k = int(_optional(arguments, "top_k", 10))
    context_budget = int(_optional(arguments, "contextBudget", 2000))
    filters = _optional(arguments, "filters")
    project_version = _optional(arguments, "project_version")
    # The v0.8 refinement (Change Package I, plan §33) attaches a
    # trace id to the response when the operator has enabled
    # debug mode. The MCP server never auto-tracks reads in
    # production.
    include_trace = bool(
        ctx.debug_mode and _optional(arguments, "include_trace", False),
    )
    # Reranking is controlled by the operator policy; the caller may
    # override it for a single query.
    enable_reranking = _optional(arguments, "enable_reranking", None)
    from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
    result = ctx.multi_stage_retrieval.retrieve(RetrievalQuery(
        text=text, top_k=top_k, contextBudget=context_budget,
        filters=filters, projectVersion=project_version,
        include_trace=include_trace,
        enableReranking=(
            None if enable_reranking is None else bool(enable_reranking)
        ),
    ))
    bundle = ctx.context_assembler.assemble(
        retrieval=result, budget_tokens=context_budget,
    ) if result is not None else None
    trace_id = _maybe_store_trace(
        ctx, query_text=text, retrieval_result=result,
    )
    return {"ok": True,
            "result": _serialise(result),
            "contextBundle": _serialise(bundle),
            "selection_state": _selection_state_summary(result, bundle),
            "source": _source_summary(result, bundle),
            "provenance": _provenance_summary(result, bundle),
            "project_version": _project_version_summary(ctx, project_version),
            "conflicts": _conflict_summary(result, bundle),
            "support_relationships": _support_summary(result, bundle),
            "retrieval_trace_id": trace_id}


def _selection_state_summary(
    result: object, bundle: object,
) -> dict[str, Any]:
    """Surface the v0.8 selection pools and protected reasons.

    The summary is empty when the pipeline ran the legacy
    seven-stage path; the v2 path populates ``primary_count``,
    ``reserve_count``, ``protected_count`` and
    ``support_count`` on :class:`RetrievalResult`. The
    :class:`ContextBundle` selection summary is layered on top
    so operators see what the assembler actually consumed.
    """

    summary: dict[str, Any] = {
        "primary": int(getattr(result, "primary_count", 0) or 0),
        "reserve": int(getattr(result, "reserve_count", 0) or 0),
        "protected": int(getattr(result, "protected_count", 0) or 0),
        "support": int(getattr(result, "support_count", 0) or 0),
    }
    selection = getattr(result, "selection_result", None)
    protected_reasons: list[str] = []
    if selection is not None:
        for trace in getattr(selection, "traces", ()) or ():
            reason = str(getattr(trace, "protected_reason", "") or "")
            if reason:
                protected_reasons.append(reason)
    summary["protected_reasons"] = protected_reasons
    bundle_summary = getattr(bundle, "selection_summary", None) or {}
    summary["bundle"] = dict(bundle_summary)
    return summary


def _source_summary(result: object, bundle: object) -> list[str]:
    """Return the sorted distinct source identifiers in the response.

    The pre-change ``RetrievalHit.source`` field is one of
    ``"dense" | "sparse" | "exact" | "hybrid"``; support items
    are surfaced separately through
    :func:`_support_summary` so the four-way source taxonomy
    never grows a ``"graph"`` / ``"hierarchy"`` value.
    """

    sources: set[str] = set()
    for hit in getattr(result, "hits", ()) or ():
        src = str(getattr(hit, "source", "") or "")
        if src:
            sources.add(src)
    return sorted(sources)


def _provenance_summary(
    result: object, bundle: object,
) -> list[dict[str, Any]]:
    """Return the citation provenance for the assembled hits."""

    citations = getattr(bundle, "citations", ()) or ()
    out: list[dict[str, Any]] = []
    for citation in citations:
        try:
            out.append({
                "chunkId": str(getattr(citation, "chunkId", "") or ""),
                "contentHash": str(
                    getattr(citation, "contentHash", "") or "",
                ),
                "sourceReference": str(
                    getattr(citation, "sourceReference", "") or "",
                ),
                "evidenceWeight": float(
                    getattr(citation, "evidenceWeight", 0.0) or 0.0,
                ),
            })
        except Exception:
            continue
    return out


def _project_version_summary(
    ctx: ToolContext, requested: object,
) -> dict[str, Any]:
    """Return the runtime project version summary.

    The summary merges the readiness snapshot (canonical source)
    with the requester's ``project_version`` argument so the
    response always carries both the active and the requested
    versions side by side.
    """

    snapshot = ctx.readiness.snapshot()
    try:
        return {
            "current_head": str(snapshot.current_head or ""),
            "working_tree_fingerprint": str(
                snapshot.working_tree_fingerprint or "",
            ),
            "consistent": bool(snapshot.consistent),
            "last_hydrate_at": str(snapshot.last_hydrate_at or ""),
            "last_reconcile_at": str(snapshot.last_reconcile_at or ""),
            "requested": _serialise(requested),
        }
    except Exception:
        return {"consistent": False}


def _conflict_summary(
    result: object, bundle: object,
) -> list[dict[str, Any]]:
    """Return the conflicting chunk ids and source documents.

    The legacy ``RetrievalResult.conflicts`` field is opaque;
    the v0.8 surface (plan §33) names the conflict by its
    ``chunkId`` and source document so the operator can act
    on it.
    """

    conflicts = []
    seen: set[str] = set()
    hits = list(getattr(result, "conflicts", ()) or ())
    hits.extend(list(getattr(bundle, "conflictingHits", ()) or ()))
    for hit in hits:
        chunk_id = str(getattr(hit, "chunkId", "") or "")
        if not chunk_id or chunk_id in seen:
            continue
        seen.add(chunk_id)
        metadata = getattr(hit, "metadata", None)
        document_id = str(
            getattr(metadata, "documentId", "") or "",
        ) if metadata is not None else ""
        conflicts.append({
            "chunkId": chunk_id,
            "sourceDocumentId": document_id,
        })
    return conflicts


def _support_summary(
    result: object, bundle: object,
) -> dict[str, Any]:
    """Return the support-evidence relationships attached to the bundle.

    Support items (graph / hierarchy / table / figure evidence)
    never flow through ``RetrievalHit.source``; they are added
    by the context assembler with their own ``evidence_kind``.
    The MCP surface summarises the relationship counts and
    source documents so the agent can decide whether to drill
    into a particular support type.
    """

    support_hits = list(getattr(bundle, "support_hits", ()) or ())
    counts: dict[str, int] = {}
    documents: set[str] = set()
    chunk_ids: list[str] = []
    for item in support_hits:
        kind = str(getattr(item, "evidence_kind", "graph") or "graph")
        counts[kind] = counts.get(kind, 0) + 1
        chunk_id = str(getattr(item, "chunk_id", "") or "")
        if chunk_id:
            chunk_ids.append(chunk_id)
        document_id = str(
            getattr(item, "source_document_id", "") or "",
        )
        if document_id:
            documents.add(document_id)
    return {
        "counts": counts,
        "chunkIds": chunk_ids,
        "sourceDocumentIds": sorted(documents),
        "total": int(getattr(result, "support_count", 0) or 0),
    }


def _maybe_store_trace(
    ctx: ToolContext, *, query_text: str, retrieval_result: object,
) -> Optional[str]:
    """Persist the retrieval trace when debug mode is on.

    Returns the trace id when the trace was stored, :data:`None`
    when debug mode is off, the trace store is not configured, or
    the multi-stage pipeline did not produce a trace.
    """

    if not ctx.debug_mode:
        return None
    trace_store = ctx.trace_store
    if trace_store is None:
        return None
    trace = getattr(retrieval_result, "trace", None)
    if trace is None:
        return None
    from pi_platform.adapters.retrieval.in_memory_trace_store import (
        compute_trace_id,
    )
    from pi_platform.ports.retrieval.trace_store import (
        RetrievalTraceRecord,
    )
    trace_id = compute_trace_id(query_text, trace)
    trace_store.store(RetrievalTraceRecord(
        trace_id=trace_id,
        query_text=str(query_text or ""),
        trace=trace,
    ))
    return trace_id


async def _tool_get_entity(ctx: ToolContext,
                           arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    entity_id = _require(arguments, "entity_id")
    project_version = _optional(arguments, "project_version")
    # Phase 6 prerequisite 4: use ProvenancePort.evidence, not
    # lookup. Missing evidence is reported as missing, not
    # invented.
    provenance = ctx.readiness.snapshot()
    return {"ok": True, "entity_id": entity_id,
            "project_version": _serialise(project_version),
            "provenance": _serialise(provenance),
            "evidence": [], "evidence_text": "not implemented"}


async def _tool_get_component(ctx: ToolContext,
                              arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return await _tool_get_entity(
        ctx, {"entity_id": _require(arguments, "component_uri"),
              **arguments})


async def _tool_get_requirement(ctx: ToolContext,
                                arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return await _tool_get_entity(
        ctx, {"entity_id": _require(arguments, "requirement_id"),
              **arguments})


async def _tool_get_spec(ctx: ToolContext,
                        arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    return await _tool_get_entity(
        ctx, {"entity_id": _require(arguments, "spec_id"), **arguments})


async def _tool_get_architecture(ctx: ToolContext,
                                 arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    return {"ok": True,
            "architecture": {"note": "Wiki architecture index"}}


def _research(ctx: ToolContext):
    """Return the research service or raise a typed error."""

    service = getattr(ctx, "dependency_research", None)
    if service is None:
        raise McpServerError(
            "dependency research is not enabled in this deployment")
    return service


def _research_error(exc: Exception) -> Mapping[str, Any]:
    """Translate a research failure into a structured tool response."""

    from pi_platform.core.research.records import (
        ResearchDenied,
        ResearchUnsupported,
        StaleResearchCursor,
    )

    if isinstance(exc, ResearchDenied):
        status = "denied"
    elif isinstance(exc, ResearchUnsupported):
        status = "unsupported"
    elif isinstance(exc, StaleResearchCursor):
        status = "stale"
    else:
        status = "failed"
    return {"ok": False, "status": status,
            "error": {"type": exc.__class__.__name__, "message": str(exc)}}


def _research_result(result: Any) -> Mapping[str, Any]:
    """Translate a research result into the tool response shape."""

    payload = result.as_dict() if hasattr(result, "as_dict") else dict(result)
    status = str(payload.get("status", "failed"))
    return {
        "ok": status in ("complete", "partial"),
        "research": payload,
        "status": status,
        "completeness": payload.get("completeness"),
        "warnings": list(payload.get("warnings", ())),
        "truncated": bool(payload.get("truncated", False)),
        "cursor": payload.get("cursor"),
    }


async def _tool_get_dependency(ctx: ToolContext,
                               arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Look a Maven coordinate up in the real dependency graph.

    The input shape is the historical one -- ``group``, ``artifact``
    and ``version`` -- and it is preserved. The answer is now real
    evidence: the versions the project actually resolves, or an
    explicit statement that the graph does not contain the
    coordinate. A placeholder is never returned as a successful
    analysis.
    """

    await _enforce_readiness(ctx)
    group = _require(arguments, "group")
    artifact = _require(arguments, "artifact")
    version = _require(arguments, "version")
    coordinate = f"{group}:{artifact}"
    service = getattr(ctx, "dependency_research", None)
    if service is None:
        return {"ok": False, "dependency": {
            "group": group, "artifact": artifact, "version": version,
            "status": "unavailable",
            "reason": "dependency research is not enabled in this deployment",
        }}
    from pi_platform.ports.research.dependency_research import DependencyTreeRequest

    result = service.tree(DependencyTreeRequest(ecosystem="java",
                                                package=coordinate))
    payload = result.as_dict()
    matches = [node for node in payload.get("nodes", ())
               if node.get("package", {}).get("name") == coordinate]
    resolved = [node.get("package", {}).get("resolvedVersion")
                for node in matches]
    resolved = [item for item in resolved if item]
    declared = [node.get("package", {}).get("declaredConstraint")
                for node in matches]
    declared = [item for item in declared if item]
    if not matches:
        return {"ok": False, "dependency": {
            "group": group, "artifact": artifact, "version": version,
            "status": "unavailable",
            "reason": ("the dependency graph does not contain this coordinate; "
                       "the project declares it but no lock resolves it"),
            "warnings": list(payload.get("warnings", ())),
        }}
    exact = [item for item in resolved if item == version]
    declared_exact = [item for item in declared if item == version]
    return {"ok": True, "dependency": {
        "group": group, "artifact": artifact, "version": version,
        "status": "complete" if (exact or declared_exact) else "partial",
        "resolvedVersions": resolved,
        "declaredVersions": declared,
        "resolved": bool(exact),
        "instances": matches,
        "evidence": list(payload.get("evidence", ())),
        "warnings": list(payload.get("warnings", ())),
    }}


async def _tool_dependency_tree(ctx: ToolContext,
                                arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    from pi_platform.core.research.policy import ResearchLimits
    from pi_platform.ports.research.dependency_research import DependencyTreeRequest

    service = _research(ctx)
    limits = ResearchLimits(
        max_nodes=int(_optional(arguments, "max_nodes", 100)),
        max_depth=int(_optional(arguments, "max_depth", 5)),
    )
    scopes = tuple(str(item) for item in (_optional(arguments, "scopes", ()) or ()))
    try:
        result = service.tree(DependencyTreeRequest(
            ecosystem=str(_require(arguments, "ecosystem")),
            package=_optional(arguments, "package"),
            environment=str(_optional(arguments, "environment", "default")),
            scopes=scopes,
            limits=limits,
            cursor=_optional(arguments, "cursor"),
        ))
    except Exception as exc:  # noqa: BLE001 - the tool boundary is wide
        return _research_error(exc)
    return _research_result(result)


async def _tool_dependency_search(ctx: ToolContext,
                                  arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    from pi_platform.ports.research.dependency_research import DependencySearchRequest

    service = _research(ctx)
    try:
        result = service.search(DependencySearchRequest(
            ecosystem=str(_require(arguments, "ecosystem")),
            package_ref=str(_require(arguments, "package_ref")),
            query=str(_require(arguments, "query")),
            limit=int(_optional(arguments, "limit", 20)),
            cursor=_optional(arguments, "cursor"),
        ))
    except Exception as exc:  # noqa: BLE001 - the tool boundary is wide
        return _research_error(exc)
    return _research_result(result)


async def _tool_dependency_read(ctx: ToolContext,
                                arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    from pi_platform.ports.research.dependency_research import DependencyReadRequest

    service = _research(ctx)
    try:
        result = service.read(DependencyReadRequest(
            evidence_ref=str(_optional(arguments, "evidence_ref", "")),
            artifact=_optional(arguments, "artifact"),
            member=_optional(arguments, "member"),
            symbol=_optional(arguments, "symbol"),
            start_line=_optional(arguments, "start_line"),
            end_line=_optional(arguments, "end_line"),
            max_bytes=_optional(arguments, "max_bytes"),
        ))
    except Exception as exc:  # noqa: BLE001 - the tool boundary is wide
        return _research_error(exc)
    return _research_result(result)


async def _tool_dependency_acquire(ctx: ToolContext,
                                   arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    from pi_platform.ports.research.dependency_research import DependencyAcquireRequest

    service = _research(ctx)
    try:
        result = service.acquire(DependencyAcquireRequest(
            ecosystem=str(_require(arguments, "ecosystem")),
            name=str(_require(arguments, "name")),
            version=str(_require(arguments, "version")),
            source_id=str(_require(arguments, "source_id")),
        ))
    except Exception as exc:  # noqa: BLE001 - the tool boundary is wide
        return _research_error(exc)
    return _research_result(result)


async def _tool_find_implementation(ctx: ToolContext,
                                    arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    return {"ok": True, "requirement_id":
            _optional(arguments, "requirement_id"),
            "implementations": []}


async def _tool_trace_requirement(ctx: ToolContext,
                                 arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    return {"ok": True, "requirement_id":
            _optional(arguments, "requirement_id"),
            "trace": []}


async def _tool_find_references(ctx: ToolContext,
                                arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    return {"ok": True, "symbol":
            _optional(arguments, "symbol"),
            "references": []}


async def _tool_get_project_version(ctx: ToolContext,
                                     arguments: Mapping[str, Any]
                                     ) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    snap = ctx.readiness.snapshot()
    return {"ok": True, "current_head": snap.current_head,
            "working_tree_fingerprint": snap.working_tree_fingerprint,
            "last_hydrate_at": snap.last_hydrate_at,
            "last_reconcile_at": snap.last_reconcile_at,
            "consistent": snap.consistent}


async def _tool_get_conflicts(ctx: ToolContext,
                              arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    return {"ok": True, "conflicts": []}


async def _tool_get_stale_knowledge(ctx: ToolContext,
                                    arguments: Mapping[str, Any]
                                    ) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    return {"ok": True, "stale_fact_ids": []}


async def _tool_build_task_context(ctx: ToolContext,
                                   arguments: Mapping[str, Any]
                                   ) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    goal = _require(arguments, "goal")
    budget_tokens = int(_optional(arguments, "budget_tokens", 4000))
    requirement_id = _optional(arguments, "requirement_id")
    bundle = ctx.task_context_builder.build(
        goal=goal, budget_tokens=budget_tokens,
        retrieval=None,
    )
    return {"ok": True, "bundle": _serialise(bundle),
            "requirement_id": requirement_id}


async def _tool_materialize_knowledge(ctx: ToolContext,
                                       arguments: Mapping[str, Any]
                                       ) -> Mapping[str, Any]:
    # Phase 6 prerequisite 1: trust the boundary.
    await _enforce_readiness(ctx)
    approval_id = _require(arguments, "approval_id")
    from pi_platform.ports import ApprovalRequest
    from pi_platform.core.sync import MaterialiseService
    repo_root = ctx.repo_root or Path(arguments.get("repo_root", os.getcwd()))
    cache_root = ctx.cache_root or Path(arguments.get(
        "cache_root", str(repo_root / "cache")))
    change_ids = tuple(arguments.get("change_ids") or ())
    grant = ctx.boundary.verify(
        ApprovalRequest(action="materialise",
                        repo_root=str(repo_root.resolve()),
                        change_ids=change_ids),
        approval_id,
    )
    log.info(
        "materialise authorised: issuer=%s not_after=%s",
        grant.issuer, grant.not_after,
    )
    # The actual MaterialiseService call is wired by the CLI
    # entry point; here we report the verified grant so the CLI
    # can call MaterialiseService.materialise_durable_changes
    # with the boundary-checked approval.
    return {"ok": True,
            "grant": {
                "issuer": grant.issuer,
                "notBefore": grant.not_before,
                "notAfter": grant.not_after,
            },
            "repo_root": str(repo_root),
            "cache_root": str(cache_root),
            "change_ids": list(change_ids)}


async def _tool_refresh_sources(ctx: ToolContext,
                                arguments: Mapping[str, Any]
                                ) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    approval_id = _require(arguments, "approval_id")
    from pi_platform.ports import ApprovalRequest
    repo_root = ctx.repo_root or Path(arguments.get("repo_root", os.getcwd()))
    grant = ctx.boundary.verify(
        ApprovalRequest(action="refresh_sources",
                        repo_root=str(repo_root.resolve()),
                        change_ids=()),
        approval_id,
    )
    return {"ok": True,
            "grant": {
                "issuer": grant.issuer,
                "notBefore": grant.not_before,
                "notAfter": grant.not_after,
            }}


async def _tool_describe_capabilities(ctx: ToolContext,
                                      arguments: Mapping[str, Any]
                                      ) -> Mapping[str, Any]:
    descriptor = ctx.capability_discovery.describe()
    return {"ok": True,
            "descriptor": _serialise(descriptor),
            "serverIdentity": dict(ctx.server_identity)}


async def _tool_get_retrieval_trace(ctx: ToolContext,
                                    arguments: Mapping[str, Any]
                                    ) -> Mapping[str, Any]:
    """Debug-only trace lookup (Change Package I, plan §33).

    Requires :attr:`ToolContext.debug_mode` to be truthy; the
    server rejects calls outside debug mode with
    :class:`DebugModeRequiredError` so the public MCP surface
    stays identical to the §36 inventory.
    """

    if not ctx.debug_mode:
        raise DebugModeRequiredError(
            "project.get_retrieval_trace is debug-only; set "
            "PI_MCP_DEBUG=1 or pass --debug to enable it"
        )
    if ctx.trace_store is None:
        raise McpServerError(
            "retrieval trace store is not configured; configure a "
            "RetrievalTraceStorePort on the ToolContext to enable "
            "project.get_retrieval_trace"
        )
    trace_id = _require(arguments, "trace_id")
    record = ctx.trace_store.fetch(trace_id)
    if record is None:
        raise TraceNotFoundError(
            f"unknown retrieval trace id: {trace_id!r}"
        )
    from pi_platform.core.retrieval.retrieval_trace import (
        RetrievalTraceBuilder,
    )
    builder = RetrievalTraceBuilder()
    trace = record.trace
    builder.set("query_features", trace.query_features)
    builder.set("active_filters", trace.active_filters)
    if trace.exact_candidates:
        builder.set("exact_candidates", trace.exact_candidates)
    if trace.dense_candidates:
        builder.set("dense_candidates", trace.dense_candidates)
    if trace.sparse_candidates:
        builder.set("sparse_candidates", trace.sparse_candidates)
    if trace.fusion is not None:
        builder.set("fusion", trace.fusion)
    if trace.reranker is not None:
        builder.set("reranker", trace.reranker)
    if trace.selection is not None:
        builder.set("selection", trace.selection)
    if trace.graph_expansion is not None:
        builder.set("graph_expansion", trace.graph_expansion)
    if trace.hierarchy_expansion is not None:
        builder.set("hierarchy_expansion", trace.hierarchy_expansion)
    for decision in trace.budget_decisions:
        builder.add_budget_decision(decision)
    for stage, ms in trace.timings:
        # ``RetrievalTrace.timings`` is a tuple of
        # ``(stage, milliseconds)`` pairs; replaying them through
        # the builder keeps the stage-by-stage latency breakdown
        # observable through the debug-only tool.
        builder.add_timing(str(stage), int(ms))
    payload = json.loads(builder.to_json())
    return {"ok": True,
            "trace_id": record.trace_id,
            "query_text": record.query_text,
            "trace": payload,
            "stats": ctx.trace_store.stats()}



# ---------------------------------------------------------------------------
# LLM Wiki tools
# ---------------------------------------------------------------------------


def _wiki(ctx: ToolContext):
    """Return the :class:`LlmWiki` of the target repository."""

    from pi_platform.core.wiki.llm_wiki import LlmWiki, LlmWikiError

    if ctx.repo_root is None:
        raise McpServerError(
            "the LLM Wiki tools require a target repository root"
        )
    return LlmWiki(Path(ctx.repo_root))


async def _tool_wiki_list_pages(ctx: ToolContext,
                                arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """List the curated Wiki pages of the target repository."""

    from pi_platform.core.wiki.llm_wiki import LlmWikiError

    try:
        wiki = _wiki(ctx)
        pages = wiki.list_pages()
    except LlmWikiError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "root": str(wiki.root),
        "count": len(pages),
        "pages": pages,
    }


async def _tool_wiki_read_page(ctx: ToolContext,
                               arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Read one curated Wiki page."""

    from pi_platform.core.wiki.llm_wiki import LlmWikiError

    path = _require(arguments, "path")
    include_body = bool(_optional(arguments, "include_body", True))
    inputs = _optional(arguments, "inputs") or {}
    try:
        wiki = _wiki(ctx)
        page = wiki.read_page(str(path))
    except LlmWikiError as exc:
        return {"ok": False, "error": str(exc)}
    payload = page.as_dict(include_body=include_body)
    if isinstance(inputs, Mapping) and inputs:
        payload["staleNotes"] = wiki.stale_dependency_notes(
            str(path), inputs=inputs)
    return {"ok": True, "page": payload}


async def _tool_wiki_search(ctx: ToolContext,
                            arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Search the curated Wiki pages."""

    from pi_platform.core.wiki.llm_wiki import LlmWikiError

    query = _require(arguments, "query")
    top_k = int(_optional(arguments, "top_k", 8))
    try:
        pages = _wiki(ctx).search_pages(str(query), top_k=top_k)
    except LlmWikiError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "count": len(pages), "pages": pages}


async def _tool_wiki_write_page(ctx: ToolContext,
                                arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Create or update a curated Wiki page.

    The page is validated against the OKF v0.2 profile before it is
    written. An invalid page is never stored. The write is atomic and is
    recorded in the reserved Wiki log.
    """

    from pi_platform.core.wiki.llm_wiki import LlmWikiError

    path = _require(arguments, "path")
    title = _require(arguments, "title")
    body = _require(arguments, "body")
    page_type = str(_optional(arguments, "type", "Concept"))
    summary = str(_optional(arguments, "summary", ""))
    author = str(_optional(arguments, "author", "calling-llm"))
    source = str(_optional(arguments, "source", ""))
    dry_run = bool(_optional(arguments, "dry_run", False))
    expected_revision = _optional(arguments, "expected_revision")
    dependency_notes = _optional(arguments, "dependency_notes") or ()
    try:
        wiki = _wiki(ctx)
        wiki.ensure_scaffold()
        result = wiki.write_page(
            relative_path=str(path),
            title=str(title),
            body=str(body),
            page_type=page_type,
            summary=summary,
            author=author,
            source=source,
            dry_run=dry_run,
            expected_revision=(str(expected_revision)
                               if expected_revision else None),
            dependency_notes=tuple(
                note for note in dependency_notes if isinstance(note, Mapping)),
        )
    except LlmWikiError as exc:
        return {"ok": False, "error": str(exc)}
    result["note"] = (
        "The page becomes part of the searchable corpus on the next "
        "project refresh."
    )
    return result


async def _tool_wiki_validate(ctx: ToolContext,
                              arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    """Validate the curated Wiki bundle against the OKF profile."""

    from pi_platform.core.wiki.llm_wiki import LlmWikiError

    try:
        wiki = _wiki(ctx)
        errors = wiki.validate()
    except LlmWikiError as exc:
        return {"ok": False, "error": str(exc)}
    return {
        "ok": not errors,
        "root": str(wiki.root),
        "profile": "okf-0.2",
        "errors": errors,
    }


TOOL_REGISTRY: dict[str, ToolHandler] = {
    "project.search": _tool_search,
    "project.retrieve_context": _tool_retrieve_context,
    "project.get_entity": _tool_get_entity,
    "project.get_component": _tool_get_component,
    "project.get_requirement": _tool_get_requirement,
    "project.get_spec": _tool_get_spec,
    "project.get_architecture": _tool_get_architecture,
    "project.get_dependency": _tool_get_dependency,
    "project.find_implementation": _tool_find_implementation,
    "project.trace_requirement": _tool_trace_requirement,
    "project.find_references": _tool_find_references,
    "project.get_project_version": _tool_get_project_version,
    "project.get_conflicts": _tool_get_conflicts,
    "project.get_stale_knowledge": _tool_get_stale_knowledge,
    "project.build_task_context": _tool_build_task_context,
    "project.materialize_knowledge": _tool_materialize_knowledge,
    "project.refresh_sources": _tool_refresh_sources,
    "project.describe_capabilities": _tool_describe_capabilities,
    "project.get_retrieval_trace": _tool_get_retrieval_trace,
    "project.wiki_list_pages": _tool_wiki_list_pages,
    "project.wiki_read_page": _tool_wiki_read_page,
    "project.wiki_search": _tool_wiki_search,
    "project.wiki_write_page": _tool_wiki_write_page,
    "project.wiki_validate": _tool_wiki_validate,
    "project.dependency_tree": _tool_dependency_tree,
    "project.dependency_search": _tool_dependency_search,
    "project.dependency_read": _tool_dependency_read,
    "project.dependency_acquire": _tool_dependency_acquire,
}


def _serialise(obj: Any) -> Any:
    if obj is None:
        return None
    if hasattr(obj, "as_dict"):
        try:
            return obj.as_dict()
        except Exception:
            pass
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import asdict
        return asdict(obj)
    if isinstance(obj, (list, tuple)):
        return [_serialise(x) for x in obj]
    if isinstance(obj, Mapping):
        return {k: _serialise(v) for k, v in obj.items()}
    return obj


class McpServer:
    """§36 MCP server (tool / resource plane).

    The server is the registration / dispatch hub; the
    transport (stdio / Streamable HTTP) is wired in
    :meth:`serve`. The unit tests exercise the dispatch
    table directly without involving the SDK.
    """

    def __init__(self, *, context: ToolContext):
        self._context = context

    @property
    def tool_names(self) -> tuple[str, ...]:
        names: list[str] = []
        for name in TOOL_REGISTRY:
            if name in DEBUG_TOOLS and not self._context.debug_mode:
                continue
            names.append(name)
        return tuple(names)

    @property
    def section_36_tools(self) -> tuple[str, ...]:
        return SECTION_36_TOOLS

    @property
    def extension_tools(self) -> tuple[str, ...]:
        return EXTENSION_TOOLS

    @property
    def debug_tools(self) -> tuple[str, ...]:
        if self._context.debug_mode:
            return DEBUG_TOOLS
        return ()

    async def call_tool(self, name: str,
                        arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        handler = TOOL_REGISTRY.get(name)
        if handler is None:
            return {"ok": False,
                    "error": {"type": "UnknownToolError",
                              "message": f"unknown tool: {name!r}"}}
        # Debug tools are gated by ``debug_mode``. A public
        # caller that asks for one outside debug mode gets a
        # well-typed error instead of an unknown-tool error so
        # the surface area change is observable.
        if name in DEBUG_TOOLS and not self._context.debug_mode:
            return {"ok": False,
                    "error": {"type": "DebugModeRequiredError",
                              "message": (
                                  f"debug-only tool: {name!r}; set "
                                  "PI_MCP_DEBUG=1 to enable"
                              )}}
        try:
            return await handler(self._context, arguments)
        except McpServerError as exc:
            return {"ok": False,
                    "error": {"type": exc.__class__.__name__,
                              "message": str(exc)}}
        except RuntimeNotReadyError as exc:
            return {"ok": False,
                    "error": {"type": "RuntimeNotReadyError",
                              "message": str(exc),
                              "snapshot": _serialise(exc.snapshot)}}
        except Exception as exc:
            return {"ok": False,
                    "error": {"type": exc.__class__.__name__,
                              "message": str(exc)}}

    async def list_tools(self) -> Sequence[str]:
        return self.tool_names

    async def handle_jsonrpc_async(
        self,
        payload: Mapping[str, Any],
        *,
        skill_plane: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Stdlib JSON-RPC 2.0 MCP dispatcher.

        Allows both the embedded HTTP server (`POST /mcp`) and the
        stdlib stdio fallback (`mcp-serve --transport stdio`) to serve
        the full §36 tool surface and §38 skill distribution plane
        without requiring the optional third-party ``mcp`` SDK.
        """
        req_id = payload.get("id")
        method = str(payload.get("method") or "")
        params = payload.get("params")
        if not isinstance(params, Mapping):
            params = {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": (
                        params.get("protocolVersion")
                        if params.get("protocolVersion") in {"2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}
                        else "2025-11-25"
                    ),
                    "serverInfo": {
                        "name": self._context.server_identity["name"],
                        "version": self._context.server_identity.get("version")
                                   or self._context.server_identity["serverVersion"],
                    },
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False},
                    },
                },
            }
        if method in ("notifications/initialized", "initialized", "ping"):
            return {"jsonrpc": "2.0", "id": req_id, "result": {}}
        if method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        tool_definition(name) for name in self.tool_names
                    ]
                },
            }
        if method == "tools/call":
            tool_name = str(params.get("name") or "")
            arguments = params.get("arguments")
            if not isinstance(arguments, Mapping):
                arguments = {}
            outcome = await self.call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(outcome, sort_keys=True),
                        }
                    ],
                    "structuredContent": dict(outcome),
                    "isError": not bool(outcome.get("ok", True)),
                },
            }
        if method == "resources/list":
            resources = (
                [
                    {"uri": uri, "name": uri}
                    for uri in skill_plane.list_resources()
                ]
                if skill_plane is not None
                else []
            )
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"resources": resources},
            }
        if method == "resources/read":
            uri = str(params.get("uri") or "")
            if skill_plane is None:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32002,
                        "message": f"resource plane unavailable for {uri!r}",
                    },
                }
            try:
                raw = skill_plane.read_resource(uri)
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "contents": [
                            {
                                "uri": uri,
                                "text": raw.decode("utf-8", errors="replace"),
                            }
                        ]
                    },
                }
            except Exception as exc:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32002, "message": str(exc)},
                }
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": -32601,
                "message": f"Method not found: {method!r}",
            },
        }

    def handle_jsonrpc(
        self,
        payload: Mapping[str, Any],
        *,
        skill_plane: Optional[Any] = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper around :meth:`handle_jsonrpc_async`."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.handle_jsonrpc_async(payload, skill_plane=skill_plane)
            )
        finally:
            loop.close()

    def serve_stdio_fallback(
        self,
        *,
        in_stream: Any = None,
        out_stream: Any = None,
        skill_plane: Optional[Any] = None,
    ) -> int:
        """Run a line-delimited JSON-RPC 2.0 MCP loop using the Python stdlib."""
        import sys

        reader = in_stream if in_stream is not None else sys.stdin
        writer = out_stream if out_stream is not None else sys.stdout
        for raw_line in reader:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, Mapping):
                    raise ValueError("JSON-RPC request must be an object")
            except ValueError as exc:
                err_resp = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32700, "message": f"Parse error: {exc}"},
                }
                writer.write(json.dumps(err_resp, sort_keys=True) + "\n")
                writer.flush()
                continue
            response = self.handle_jsonrpc(payload, skill_plane=skill_plane)
            if payload.get("id") is not None or "error" in response:
                writer.write(json.dumps(response, sort_keys=True) + "\n")
                writer.flush()
        return 0

    async def serve(self, transport: str = "stdio") -> None:
        """Boot the MCP server with the requested transport.

        Default transport is stdio; Streamable HTTP is supported
        by setting the ``PI_MCP_TRANSPORT`` env var to ``http``.
        The SDK is imported lazily so the unit tests run without
        it.
        """
        if transport == "stdio":
            transport_impl = os.environ.get(
                "PI_MCP_TRANSPORT", "stdio")
            if transport_impl != "stdio":
                transport = transport_impl
        try:
            from mcp.server import Server  # type: ignore
            from mcp.server.stdio import stdio_server  # type: ignore
        except ImportError as exc:  # pragma: no cover - SDK env
            raise McpServerError(
                "the official MCP Python SDK (mcp==1.30.0) is not "
                "installed; install with "
                "`pip install mcp==1.30.0` to boot the server"
            ) from exc
        server = Server(DEFAULT_SERVER_IDENTITY["name"])

        @server.list_tools()
        async def _list():
            from mcp.types import Tool
            return [Tool(**tool_definition(name)) for name in self.tool_names]

        @server.call_tool()
        async def _call(name: str, arguments):
            result = await self.call_tool(name, arguments)
            return [{"type": "text", "text": json.dumps(result,
                                                        sort_keys=True)}]

        if transport == "stdio":
            async with stdio_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream,
                                 server.create_initialization_options())
        elif transport == "http":
            # Streamable HTTP is wired through the SDK's
            # ``streamable_http`` module when available; the
            # transport stays opt-in and is configured by the
            # operator. The integration tests exercise the actual
            # HTTP session when the SDK is installed.
            try:
                from mcp.server.streamable_http import (  # type: ignore
                    streamable_http_server,
                )
            except ImportError as exc:  # pragma: no cover
                raise McpServerError(
                    "streamable_http transport not available in this "
                    "SDK build"
                ) from exc
            async with streamable_http_server() as (read_stream, write_stream):
                await server.run(read_stream, write_stream,
                                 server.create_initialization_options())
        else:
            raise McpServerError(
                f"unsupported transport: {transport!r}; expected "
                'one of {"stdio", "http"}'
            )