from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import Settings
from .native_context import instructions, native_session_id, validate_project_root
from .security import BearerAuthMiddleware

settings = Settings.from_env()
http = httpx.AsyncClient()
mcp = MCPServer(
    "Hermes Native Worker Control",
    instructions=(
        "Claude Code-only control transport for an existing native Hermes Agent. "
        "This server never reads or proxies project files."
    ),
)


async def api(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    *,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"headers": {"Authorization": f"Bearer {settings.api_key}"}}
    if payload is not None:
        kwargs["json"] = payload
    timeout_seconds = max(0.1, min(float(timeout_seconds), 30.0))
    kwargs["timeout"] = httpx.Timeout(
        timeout_seconds,
        connect=min(10.0, timeout_seconds),
    )
    response = await http.request(method, settings.api_base + path, **kwargs)
    response.raise_for_status()
    return response.json() if response.content else {}


@mcp.tool()
async def hermes_run(project_root: str, task: str, session_id: str = "") -> dict:
    """Start a fresh native Hermes run, or explicitly continue a supplied Hermes session id."""
    try:
        root = validate_project_root(project_root, settings.allowed_project_roots)
        sid = native_session_id(root, session_id)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    text = (task or "").strip()
    if not text:
        raise ToolError("task is required")
    # Do NOT send the public API model/profile name here. /v1/runs treats a
    # supplied model as an actual per-request model override. Omitting it keeps
    # the worker profile's configured provider/model as the source of truth.
    payload = {
        "input": text,
        "session_id": sid,
        "instructions": instructions(root),
    }
    result = await api("POST", "/v1/runs", payload)
    return {**result, "session_id": result.get("session_id") or sid}


@mcp.tool()
async def hermes_status(run_id: str) -> dict:
    """Return current Hermes run state, including approval-paused state when present."""
    return await api("GET", _run_path(run_id))


def _run_path(run_id: str, suffix: str = "") -> str:
    value = (run_id or "").strip()
    if not value or len(value) > 200 or any(c in value for c in "\r\n\x00"):
        raise ToolError("run_id is missing or invalid")
    return f"/v1/runs/{quote(value, safe='')}{suffix}"


@mcp.tool()
async def hermes_wait(run_id: str, timeout_seconds: float = 120, poll_seconds: float = 2) -> dict:
    """Wait until a run completes/fails/cancels, pauses for approval, or the local wait expires."""
    timeout_seconds = max(1.0, min(float(timeout_seconds), 900.0))
    poll_seconds = max(0.5, min(float(poll_seconds), 10.0))
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    last: dict[str, Any] = {}
    return_states = {"completed", "failed", "cancelled", "waiting_for_approval"}
    while asyncio.get_running_loop().time() < deadline:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            break
        try:
            last = await api(
                "GET",
                _run_path(run_id),
                timeout_seconds=remaining,
            )
        except httpx.TimeoutException:
            break
        if str(last.get("status", "")).lower() in return_states:
            return last
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining > 0:
            await asyncio.sleep(min(poll_seconds, remaining))
    return {**last, "wait_timeout": True}


@mcp.tool()
async def hermes_result(run_id: str) -> dict:
    """Return Hermes run status and final output when available."""
    return await api("GET", _run_path(run_id))


@mcp.tool()
async def hermes_steer(run_id: str, text: str) -> dict:
    """Inject guidance into a currently running Hermes run at the next tool boundary."""
    guidance = (text or "").strip()
    if not guidance:
        raise ToolError("text is required")
    return await api("POST", _run_path(run_id, "/steer"), {"input": guidance})


@mcp.tool()
async def hermes_approve(run_id: str, choice: str = "once", resolve_all: bool = False) -> dict:
    """Resolve a Hermes approval pause. Use only after the parent/user has authorized the requested action."""
    normalized = (choice or "").strip().lower()
    if normalized not in {"once", "session", "always", "deny"}:
        raise ToolError("choice must be one of: once, session, always, deny")
    return await api(
        "POST",
        _run_path(run_id, "/approval"),
        {"choice": normalized, "resolve_all": bool(resolve_all)},
    )


@mcp.tool()
async def hermes_cancel(run_id: str) -> dict:
    """Request cooperative cancellation of a running Hermes run."""
    return await api("POST", _run_path(run_id, "/stop"), {})


@mcp.custom_route("/healthz", methods=["GET"])
async def health(_: Request):
    try:
        upstream = await api("GET", "/health")
        upstream_ok = str(upstream.get("status", "")).lower() == "ok"
    except Exception:
        upstream_ok = False
    return JSONResponse(
        {
            "status": "ok" if upstream_ok else "degraded",
            "service": "hermes-native-claude-mcp",
            "upstream": upstream_ok,
        }
    )


transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=[
        f"{settings.tail_ip}:{settings.port}",
        f"{settings.tail_host}:{settings.port}",
        f"localhost:{settings.port}",
        f"127.0.0.1:{settings.port}",
    ],
    allowed_origins=[],
)
base = mcp.streamable_http_app(
    host=settings.tail_ip,
    stateless_http=True,
    json_response=True,
    transport_security=transport_security,
)
app = BearerAuthMiddleware(base, settings.token)
