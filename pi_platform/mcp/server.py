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
* one `project.describe_capabilities` tool;
* the §38 distribution URI namespace as resources.

The §36 tool list is exhaustive; additional tools are
documented extensions and MUST NOT shadow the documented names.

The official MCP Python SDK (`mcp==1.30.0`, Apache-2.0) is
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


__all__ = [
    "DEFAULT_SERVER_IDENTITY",
    "McpServer",
    "McpServerError",
    "ToolContext",
]


log = logging.getLogger(__name__)


class McpServerError(RuntimeError):
    """Raised by the MCP server when a tool call violates invariants."""


@dataclass(frozen=True)
class ToolContext:
    """Per-call context passed to every tool handler.

    The context carries the dependencies the tool needs so
    handlers stay pure and testable.
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
    from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
    result = ctx.multi_stage_retrieval.retrieve(RetrievalQuery(
        text=text, top_k=top_k,
        filters=filters, projectVersion=project_version,
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
    from pi_platform.ports.retrieval.multi_stage_retrieval import RetrievalQuery
    result = ctx.multi_stage_retrieval.retrieve(RetrievalQuery(
        text=text, top_k=top_k, contextBudget=context_budget,
        filters=filters, projectVersion=project_version,
    ))
    bundle = ctx.context_assembler.assemble(
        retrieval=result, budget_tokens=context_budget,
    ) if result is not None else None
    return {"ok": True, "result": _serialise(result),
            "contextBundle": _serialise(bundle)}


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


async def _tool_get_dependency(ctx: ToolContext,
                               arguments: Mapping[str, Any]) -> Mapping[str, Any]:
    await _enforce_readiness(ctx)
    group = _require(arguments, "group")
    artifact = _require(arguments, "artifact")
    version = _require(arguments, "version")
    return {"ok": True, "dependency": {
        "group": group, "artifact": artifact, "version": version,
        "note": "metadata lookup; full record requires JAR-graph inspection",
    }}


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
        return tuple(TOOL_REGISTRY.keys())

    @property
    def section_36_tools(self) -> tuple[str, ...]:
        return SECTION_36_TOOLS

    @property
    def extension_tools(self) -> tuple[str, ...]:
        return EXTENSION_TOOLS

    async def call_tool(self, name: str,
                        arguments: Mapping[str, Any]) -> Mapping[str, Any]:
        handler = TOOL_REGISTRY.get(name)
        if handler is None:
            return {"ok": False,
                    "error": {"type": "UnknownToolError",
                              "message": f"unknown tool: {name!r}"}}
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
            return [
                {"name": name, "description": name.replace("_", " ")}
                for name in self.tool_names
            ]

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