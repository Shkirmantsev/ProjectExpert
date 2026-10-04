from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
import uvicorn

BASE_URL = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
HOST = os.environ.get("MCP_HOST", "0.0.0.0")
PORT = int(os.environ.get("MCP_PORT", "8000"))
ALLOWED_HOSTS = [x.strip() for x in os.environ.get("MCP_ALLOWED_HOSTS", "127.0.0.1:18880,localhost:18880").split(",") if x.strip()]

mcp = MCPServer("SearXNG", instructions="Search the public web through the local SearXNG instance.")

@mcp.tool()
async def web_search(query: str, max_results: int = 5, categories: str = "general", language: str = "all") -> dict[str, Any]:
    """Search the public web once. Prefer <=5 results; maximum is 10."""
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")
    max_results = max(1, min(int(max_results), 10))
    params = {"q": query, "format": "json", "categories": categories, "language": language}
    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.get(f"{BASE_URL}/search", params=params)
        response.raise_for_status()
        payload = response.json()
    normalized = []
    for item in payload.get("results", [])[:max_results]:
        normalized.append({
            "title": item.get("title"), "url": item.get("url"), "content": item.get("content"),
            "engine": item.get("engine"), "publishedDate": item.get("publishedDate"), "score": item.get("score"),
        })
    return {"query": query, "number_of_results": len(normalized), "results": normalized}

@mcp.custom_route("/healthz", methods=["GET"])
async def health(_: Request):
    return JSONResponse({"status": "ok"})

if __name__ == "__main__":
    security = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=ALLOWED_HOSTS, allowed_origins=[])
    app = mcp.streamable_http_app(host=HOST, stateless_http=True, json_response=True, transport_security=security)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
