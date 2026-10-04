from __future__ import annotations

import json
import os
from typing import Any

import httpx
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

BASE_URL = os.environ.get("CRAWL4AI_URL", "http://crawl4ai:11235").rstrip("/")
TOKEN = os.environ.get("CRAWL4AI_API_TOKEN", "").strip()
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8000"))
ALLOWED_HOSTS = [
    x.strip()
    for x in os.environ.get(
        "MCP_ALLOWED_HOSTS", "127.0.0.1:18882,localhost:18882"
    ).split(",")
    if x.strip()
]
if not TOKEN:
    raise RuntimeError("CRAWL4AI_API_TOKEN is required")

mcp = MCPServer(
    "Crawl4AI HTTP Compatibility Bridge",
    instructions="Compatibility Streamable-HTTP bridge that gives Claude Code, OpenCode and Codex one uniform local MCP endpoint for Crawl4AI.",
)


def _headers() -> dict[str, str]:
    # Crawl4AI 0.9.x accepts its static operator token as a Bearer credential.
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def _compact(value: Any, max_chars: int) -> Any:
    encoded = json.dumps(value, ensure_ascii=False)
    if len(encoded) <= max_chars:
        return value
    return {
        "truncated": True,
        "max_chars": max_chars,
        "json_prefix": encoded[:max_chars],
    }


async def _crawl(urls: list[str], max_chars: int) -> Any:
    cleaned = [u.strip() for u in urls]
    if not cleaned or any(not u.startswith(("http://", "https://")) for u in cleaned):
        raise ValueError("urls must contain public http(s) URLs")
    # Crawl4AI v0.9.2 /crawl is synchronous JSON. Empty config dictionaries
    # intentionally select server-controlled secure defaults; no hooks, JS,
    # proxy, file:// or caller-supplied executable configuration is exposed.
    payload = {"urls": cleaned, "browser_config": {}, "crawler_config": {}}
    timeout = httpx.Timeout(240.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout, headers=_headers()) as client:
        response = await client.post(f"{BASE_URL}/crawl", json=payload)
        response.raise_for_status()
        return _compact(response.json(), max_chars)


@mcp.tool()
async def crawl_url(url: str, max_chars: int = 40000) -> Any:
    """Crawl one public URL with Crawl4AI's server-side secure defaults."""
    return await _crawl([url], max(1000, min(int(max_chars), 100000)))


@mcp.tool()
async def crawl_many(urls: list[str], max_chars: int = 80000) -> Any:
    """Crawl up to 3 known public URLs; prefer crawl_url for one page."""
    if len(urls) > 3:
        raise ValueError("at most 3 URLs per call; crawl one URL at a time by default")
    return await _crawl(urls, max(1000, min(int(max_chars), 160000)))


@mcp.custom_route("/healthz", methods=["GET"])
async def health(_: Request):
    return JSONResponse({"status": "ok"})


if __name__ == "__main__":
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=ALLOWED_HOSTS,
        allowed_origins=[],
    )
    app = mcp.streamable_http_app(
        host=HOST,
        stateless_http=True,
        json_response=True,
        transport_security=security,
    )
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
