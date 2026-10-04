import json
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .core import build_index, code_symbol as find_symbol, get_document, search, validate

ROOT = Path(os.environ.get("PROJECT_ROOT", ".")).expanduser().resolve()
mcp = FastMCP(
    "project-context",
    instructions="Search first; retrieve selected Markdown only. OpenSpec proposed changes are not current behavior until adopted.",
)

@mcp.tool()
def kb_search(query: str, top_k: int = 8) -> list[dict]:
    """Search project knowledge and return compact navigation cards."""
    return search(ROOT, query, top_k)

@mcp.tool()
def kb_get(id: str, section: str | None = None, max_chars: int = 12000) -> dict:
    """Retrieve one selected Wiki document or focused section by stable knowledge ID."""
    result = get_document(ROOT, id, section, max(1000, min(max_chars, 50000)))
    return result or {"error": f"unknown knowledge id: {id}"}

@mcp.tool()
def kb_neighbors(id: str, depth: int = 1) -> dict:
    """Return explicit Markdown links from a selected knowledge document. Depth is intentionally limited."""
    doc = get_document(ROOT, id, max_chars=20000)
    if not doc:
        return {"error": f"unknown knowledge id: {id}"}
    import re
    links = re.findall(r"\[([^\]]+)\]\(([^)]+)\)", doc["content"])
    return {"id": id, "depth": min(max(depth, 1), 1), "links": [{"title": a, "target": b} for a,b in links]}

@mcp.tool()
def code_symbol(symbol: str, max_results: int = 20) -> list[dict]:
    """Find source-code occurrences of a symbol without asking the model to scan the repository."""
    return find_symbol(ROOT, symbol, max(1, min(max_results, 50)))

@mcp.tool()
def spec_context(change_id: str | None = None, max_chars: int = 16000) -> dict:
    """Retrieve current OpenSpec config/spec paths or one proposed change without mixing temporal states."""
    base = ROOT / "openspec"
    paths = [base / "config.yaml"]
    if change_id:
        change = (base / "changes" / change_id).resolve()
        if change.parent != (base / "changes").resolve() or not change.is_dir():
            return {"error": "invalid change id"}
        if not change.exists():
            return {"error": f"unknown change: {change_id}"}
        paths.extend(sorted(change.rglob("*.md")))
        state = "proposed"
    else:
        paths.extend(sorted((base / "specs").rglob("*.md")))
        state = "current"
    remaining = max(1000, min(max_chars, 50000)); items=[]
    for p in paths:
        if not p.exists() or not p.is_file(): continue
        if not p.resolve().is_relative_to(base.resolve()): continue
        text = p.read_text(encoding="utf-8")[:remaining]
        items.append({"path": p.relative_to(ROOT).as_posix(), "content": text})
        remaining -= len(text)
        if remaining <= 0: break
    return {"state": state, "changeId": change_id, "items": items}

@mcp.tool()
def jar_search(query: str) -> dict:
    """Optional Java specialization hook. Returns guidance when no Java/JAR index plugin is installed."""
    return {"query": query, "available": False, "message": "Install/enable a Java/JAR analyzer skill for deterministic Maven/JDK dependency inspection."}

@mcp.tool()
def jar_api(gav: str, class_name: str) -> dict:
    """Optional Java specialization hook; intentionally not part of the generic core."""
    return {"gav": gav, "class": class_name, "available": False, "message": "Use the optional Java/JAR analyzer skill (source JAR, javap, jdeps) when enabled."}

@mcp.tool()
def kb_validate() -> dict:
    """Validate Wiki stable IDs and local Markdown links."""
    return validate(ROOT)

@mcp.tool()
def kb_refresh() -> dict:
    """Rebuild the disposable local SQLite FTS index from canonical Markdown."""
    return build_index(ROOT)


@mcp.custom_route('/health', methods=['GET'])
async def health(request):
    from starlette.responses import JSONResponse
    return JSONResponse({'instance': os.environ.get('PROJECT_CONTEXT_MCP_INSTANCE', ''), 'pid': os.getpid()})


def main() -> None:
    import argparse
    import anyio
    global ROOT
    parser = argparse.ArgumentParser(description="Project knowledge MCP server")
    parser.add_argument("--root", default=str(ROOT), help="Absolute project repository path")
    parser.add_argument('--transport', choices=['stdio', 'streamable-http'], default='stdio')
    parser.add_argument('--port', type=int, default=18883)
    args = parser.parse_args()
    ROOT = Path(args.root).expanduser().resolve()
    if not ROOT.is_dir():
        parser.error("project root must be an existing directory")
    if not 1024 <= args.port <= 65535:
        parser.error('port must be between 1024 and 65535')
    if args.transport == 'streamable-http':
        mcp.settings.host = '127.0.0.1'
        mcp.settings.port = args.port
        mcp.settings.stateless_http = True
        mcp.run(transport='streamable-http')
        return
    # The asyncio backend can deadlock the SDK's zero-buffer stdio memory
    # streams in some supported environments. Trio uses the same MCP protocol
    # implementation without that cross-task-group scheduler failure.
    anyio.run(mcp.run_stdio_async, backend="trio")

if __name__ == "__main__":
    main()
