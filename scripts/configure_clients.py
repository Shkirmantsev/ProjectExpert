#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

from common import ROOT, atomic_write_text, bool_env, parse_env, slug

GEN = ROOT / ".generated"

LOCAL_WORKER_INSTRUCTIONS = (
    "Before non-trivial work, route the compact task through "
    "`python scripts/skill_router.py --profile local-small` and read only the "
    "returned skill paths. Work from the supplied objective, acceptance criteria, "
    "constraints, and ContextPack. Verify observable behavior and return result, "
    "evidence, changed paths, checks, and unresolved risk.\n"
)


def write_json(path: Path, obj: dict, *, mode: int | None = None) -> None:
    atomic_write_text(path, json.dumps(obj, indent=2) + "\n", mode=mode)


def model_catalog(env: dict[str, str], v2: bool = False) -> dict:
    out: dict[str, dict] = {}
    for i in range(1, 5):
        if bool_env(env, f"LOCAL_MODEL_{i}_ENABLED"):
            alias = env.get(f"LOCAL_MODEL_{i}_ALIAS", f"local-{i}")
            model = {"name": env.get(f"LOCAL_MODEL_{i}_DISPLAY_NAME", alias)}
            if v2:
                model["modelID"] = env.get(f"LOCAL_MODEL_{i}_MODEL_ID", alias)
            out[alias] = model
    if bool_env(env, "MINIMAX_ENABLED"):
        alias = env.get("MINIMAX_ALIAS", "minimax")
        model = {"name": env.get("MINIMAX_DISPLAY_NAME", "MiniMax")}
        if v2:
            model["modelID"] = env.get("MINIMAX_MODEL_ID", alias)
        out[alias] = model
    return out


def context_command() -> list[str]:
    if os.name == "nt":
        exe = ROOT / "tmp/local/project-context/venv/Scripts/project-context-mcp.exe"
    else:
        exe = ROOT / "tmp/local/project-context/venv/bin/project-context-mcp"
    return [str(exe)]


def logical_mcp_catalog(env: dict[str, str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if bool_env(env, "PROJECT_CONTEXT_MCP_ENABLED", True):
        from common import project_root, validate_project_root
        root = project_root(env)
        validate_project_root(root)
        from project_mcp import settings
        transport, port = settings(env)
        out["project-context"] = (
            {"type": "remote", "url": f"http://127.0.0.1:{port}/mcp"} if transport == "http"
            else {"type": "local", "command": context_command() + ["--root", str(root)]}
        )
    if bool_env(env, "CONTEXT7_MCP_ENABLED"):
        url = env.get("CONTEXT7_MCP_URL", "https://mcp.context7.com/mcp").strip() or "https://mcp.context7.com/mcp"
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("CONTEXT7_MCP_URL must be an HTTPS URL without embedded credentials")
        spec = {"type": "remote", "url": url}
        api_key = env.get("CONTEXT7_MCP_API_KEY", "").strip()
        if api_key:
            spec["headers"] = {"Authorization": f"Bearer {api_key}"}
        out["context7"] = spec
    if bool_env(env, "WEB_SEARCH_ENABLED"):
        out["searxng"] = {"type": "remote", "url": f"http://127.0.0.1:{env.get('SEARXNG_MCP_PORT','18880')}/mcp"}
    if bool_env(env, "CRAWL4AI_ENABLED"):
        out["crawl4ai"] = {"type": "remote", "url": f"http://127.0.0.1:{env.get('CRAWL4AI_MCP_BRIDGE_PORT','18882')}/mcp"}
    if bool_env(env, "PLAYWRIGHT_ENABLED"):
        out["playwright"] = {"type": "remote", "url": f"http://127.0.0.1:{env.get('PLAYWRIGHT_MCP_PORT','8931')}/mcp"}
    return out


def hermes_base(env: dict[str, str], sidecar: bool = False) -> str:
    scheme = env.get("HERMES_SIDECAR_SCHEME" if sidecar else "HERMES_REMOTE_SCHEME", "http")
    host = env.get("HERMES_REMOTE_HOST", "")
    port = env.get("HERMES_REMOTE_SIDECAR_PORT" if sidecar else "HERMES_REMOTE_OPENAI_PORT", "8775" if sidecar else "8642")
    return f"{scheme}://{host}:{port}"


def configure_claude(env: dict[str, str], mcp: dict[str, dict]) -> None:
    claude_mcp: dict[str, dict] = {}
    for name, spec in mcp.items():
        if spec["type"] == "local":
            claude_mcp[name] = {"type": "stdio", "command": spec["command"][0], "args": spec["command"][1:]}
        else:
            claude_mcp[name] = {"type": "http", "url": spec["url"]}
            if spec.get("headers"):
                claude_mcp[name]["headers"] = spec["headers"]
    write_json(ROOT / ".mcp.json", {"mcpServers": claude_mcp}, mode=0o600)

    agents = ROOT / ".claude/agents"
    agents.mkdir(parents=True, exist_ok=True)
    for p in agents.glob("generated-*.md"):
        p.unlink()

    if bool_env(env, "CLAUDE_CODE_USE_LITELLM"):
        for i in range(1, 5):
            if not bool_env(env, f"LOCAL_MODEL_{i}_ENABLED"):
                continue
            alias = env.get(f"LOCAL_MODEL_{i}_ALIAS", f"local-{i}")
            claude_alias = env.get(f"LOCAL_MODEL_{i}_CLAUDE_ALIAS", f"claude-{alias}")
            name = f"{slug(alias)}-worker"
            (agents / f"generated-{name}.md").write_text(
                f"---\nname: {name}\ndescription: Independent local-model worker using {alias}.\nmodel: {claude_alias}\n---\n" + LOCAL_WORKER_INSTRUCTIONS,
                encoding="utf-8",
            )

    if bool_env(env, "HERMES_ENABLED"):
        project_root = str(Path(env["PROJECT_ROOT"]).expanduser().resolve())
        token = env["HERMES_SIDECAR_TOKEN"]
        sidecar = hermes_base(env, sidecar=True)
        text = f'''---
name: hermes-worker
description: Delegate bounded autonomous repository work to native remote Hermes through the Claude-specific MCP sidecar.
model: {env.get('CLAUDE_DISPATCHER_MODEL','haiku')}
maxTurns: 12
mcpServers:
  - hermes-native:
      type: http
      url: {sidecar}/mcp
      headers:
        Authorization: "Bearer {token}"
tools:
  - mcp__hermes-native__hermes_run
  - mcp__hermes-native__hermes_wait
  - mcp__hermes-native__hermes_status
  - mcp__hermes-native__hermes_result
  - mcp__hermes-native__hermes_steer
  - mcp__hermes-native__hermes_approve
  - mcp__hermes-native__hermes_cancel
---
You are a dispatcher. The working repository is `{project_root}`. Call `hermes_run` once with a complete bounded task and preserve returned run/session IDs. Hermes accesses repository files with its own configured backend; do not proxy project files through MCP. Never launch Claude Code, OpenCode, or Codex recursively.
'''
        path = agents / "generated-hermes-worker.md"
        atomic_write_text(path, text, mode=0o600)


def configure_claude_gateway(env: dict[str, str]) -> None:
    path = ROOT / ".claude/settings.local.json"
    if not bool_env(env, "CLAUDE_CODE_USE_LITELLM"):
        if path.exists():
            path.unlink()
        return
    write_json(path, {
        "env": {
            "ANTHROPIC_BASE_URL": f"http://127.0.0.1:{env.get('LITELLM_PORT','18400')}",
            "ANTHROPIC_AUTH_TOKEN": env.get("LITELLM_MASTER_KEY", ""),
        },
        "model": env.get("CLAUDE_DEFAULT_MODEL", "opus"),
        "effortLevel": env.get("CLAUDE_DEFAULT_EFFORT", "medium"),
    }, mode=0o600)


def render_opencode_v1(env: dict[str, str], mcp: dict[str, dict]) -> dict:
    config: dict = {
        "$schema": "https://opencode.ai/config.json",
        "permission": {
            "read": {".env": "deny", ".env.*": "deny", "**/.env": "deny", "**/.env.*": "deny", ".env.example": "allow"},
        },
        "mcp": {},
    }
    for name, spec in mcp.items():
        if spec["type"] == "local":
            config["mcp"][name] = {"type": "local", "command": spec["command"], "enabled": True}
        else:
            config["mcp"][name] = {"type": "remote", "url": spec["url"], "enabled": True}
            if spec.get("headers"):
                config["mcp"][name]["headers"] = spec["headers"]
    if bool_env(env, "LITELLM_ENABLED"):
        config["provider"] = {
            "harness": {
                "name": "Harness LiteLLM",
                "npm": "@ai-sdk/openai-compatible",
                "options": {"baseURL": f"http://127.0.0.1:{env.get('LITELLM_PORT','18400')}/v1", "apiKey": "{file:.generated/litellm-master-key}"},
                "models": model_catalog(env),
            }
        }
    return config


def render_opencode_v2(env: dict[str, str], mcp: dict[str, dict]) -> dict:
    config: dict = {
        "$schema": "https://opencode.ai/config.json",
        "permissions": [
            {"action": "read", "resource": "*", "effect": "allow"},
            {"action": "read", "resource": "*.env", "effect": "deny"},
            {"action": "read", "resource": "*.env.*", "effect": "deny"},
            {"action": "read", "resource": "*.env.example", "effect": "allow"},
        ],
        "mcp": {"servers": {}},
    }
    for name, spec in mcp.items():
        if spec["type"] == "local":
            config["mcp"]["servers"][name] = {"type": "local", "command": spec["command"], "disabled": False}
        else:
            config["mcp"]["servers"][name] = {"type": "remote", "url": spec["url"], "disabled": False}
            if spec.get("headers"):
                config["mcp"]["servers"][name]["headers"] = spec["headers"]
    if bool_env(env, "LITELLM_ENABLED"):
        config["providers"] = {
            "harness": {
                "name": "Harness LiteLLM",
                "package": "@opencode-ai/ai/providers/openai-compatible",
                "settings": {"baseURL": f"http://127.0.0.1:{env.get('LITELLM_PORT','18400')}/v1", "apiKey": "{file:.generated/litellm-master-key}"},
                "models": model_catalog(env, v2=True),
            }
        }
    return config


def configure_opencode(env: dict[str, str], mcp: dict[str, dict]) -> str:
    generation = env.get("OPENCODE_CONFIG_GENERATION", "v1").strip().lower()
    if generation not in {"v1", "v2"}:
        raise SystemExit("OPENCODE_CONFIG_GENERATION must be v1 or v2")
    config = render_opencode_v2(env, mcp) if generation == "v2" else render_opencode_v1(env, mcp)

    tool_dir = ROOT / ".opencode/tools"
    tool_dir.mkdir(parents=True, exist_ok=True)
    for p in [*tool_dir.glob("generated-hermes.*"), tool_dir / "hermes.js"]:
        if p.exists():
            p.unlink()
    agent_dir = ROOT / ".opencode/agents"
    agent_dir.mkdir(parents=True, exist_ok=True)
    for p in agent_dir.glob("generated-hermes*.md"):
        p.unlink()

    runtime_path = GEN / "opencode-hermes-runtime.json"
    if bool_env(env, "HERMES_ENABLED"):
        project_root = str(Path(env["PROJECT_ROOT"]).expanduser().resolve())
        write_json(
            runtime_path,
            {"apiBase": hermes_base(env), "projectRoot": project_root},
            mode=0o600,
        )
        template = ROOT / "templates/opencode/hermes.js"
        target = tool_dir / "hermes.js"
        target.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        target.chmod(0o600)
        if generation == "v1":
            config["permission"]["hermes_*"] = "allow"
            config["permission"]["hermes_approve"] = "ask"
        else:
            config["permissions"].extend([
                {"action": "hermes_*", "resource": "*", "effect": "allow"},
                {"action": "hermes_approve", "resource": "*", "effect": "ask"},
            ])
    elif runtime_path.exists():
        runtime_path.unlink()

    write_json(ROOT / "opencode.json", config, mode=0o600)
    write_json(
        ROOT / ".opencode/package.json",
        {
            "type": "module",
            "dependencies": {"@opencode-ai/plugin": "1.18.28"},
        },
    )
    return generation


def configure_codex(env: dict[str, str], mcp: dict[str, dict]) -> None:
    lines: list[str] = []
    for name, spec in mcp.items():
        key = name.replace("-", "_")
        lines.append(f"[mcp_servers.{key}]")
        if spec["type"] == "local":
            lines.append(f'command = {json.dumps(spec["command"][0])}')
            if len(spec["command"]) > 1:
                args = ", ".join(json.dumps(a) for a in spec["command"][1:])
                lines.append(f"args = [{args}]")
        else:
            lines.append(f'url = {json.dumps(spec["url"])}')
            if spec.get("headers"):
                lines.append(f"[mcp_servers.{key}.http_headers]")
                for header, value in spec["headers"].items():
                    lines.append(f"{json.dumps(header)} = {json.dumps(value)}")
        lines.append("")
    path = ROOT / ".codex/config.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, "\n".join(lines), mode=0o600)


def write_secrets(env: dict[str, str]) -> None:
    GEN.mkdir(exist_ok=True)
    for name, value in (("litellm-master-key", env.get("LITELLM_MASTER_KEY", "")), ("hermes-api-key", env.get("HERMES_REMOTE_API_KEY", ""))):
        p = GEN / name
        atomic_write_text(p, value + "\n", mode=0o600)


def main() -> None:
    env = parse_env()
    GEN.mkdir(exist_ok=True)
    mcp = logical_mcp_catalog(env)
    write_secrets(env)
    configure_claude_gateway(env)
    configure_claude(env, mcp)
    generation = configure_opencode(env, mcp)
    configure_codex(env, mcp)
    print(f"Client configurations generated. OpenCode generation={generation}; project-context MCP={'enabled' if 'project-context' in mcp else 'disabled'}.")

if __name__ == "__main__":
    main()
