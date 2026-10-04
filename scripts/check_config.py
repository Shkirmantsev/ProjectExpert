#!/usr/bin/env python3
from __future__ import annotations
import re, sys
from common import ROOT, ENV, parse_env, bool_env, project_root, validate_project_root

def fail(msg):
    print("ERROR:", msg, file=sys.stderr)
    return 1

def configured(value: str) -> bool:
    return bool(value) and not value.startswith("CHANGE_ME") and value not in {"auto", "AUTO_GENERATE"}

def main() -> int:
    if not ENV.exists():
        return fail(".env does not exist; run `make init`")
    env = parse_env()
    errors, warnings = [], []
    try:
        root = project_root(env)
        validate_project_root(root)
    except Exception as exc:
        errors.append(str(exc))
        root = None

    for key in ("LITELLM_MASTER_KEY", "SEARXNG_SECRET", "CRAWL4AI_API_TOKEN"):
        if env.get(key) == "AUTO_GENERATE":
            errors.append(f"{key} is not initialized; run make init")

    if bool_env(env, "HERMES_ENABLED"):
        for key in ("HERMES_REMOTE_HOST", "HERMES_REMOTE_API_KEY", "HERMES_REMOTE_MODEL", "HERMES_SIDECAR_TOKEN", "MAIN_TAILSCALE_HOST", "HERMES_REMOTE_OS_USER", "HERMES_REMOTE_RUNTIME_USER", "HERMES_REMOTE_RUNTIME_HOME", "HERMES_REMOTE_STAGING_DIR"):
            if not configured(env.get(key, "")):
                errors.append(f"{key} must be configured when HERMES_ENABLED=true")
        if len(env.get("HERMES_SIDECAR_TOKEN", "")) < 32 and configured(env.get("HERMES_SIDECAR_TOKEN", "")):
            errors.append("HERMES_SIDECAR_TOKEN must be at least 32 characters")
        for key in ("HERMES_REMOTE_SCHEME", "HERMES_SIDECAR_SCHEME"):
            if env.get(key, "http") not in {"http", "https"}:
                errors.append(f"{key} must be http or https")
        for key in ("HERMES_REMOTE_RUNTIME_HOME", "HERMES_REMOTE_STAGING_DIR"):
            value = env.get(key, "")
            if configured(value) and not value.startswith("/"):
                errors.append(f"{key} must be an absolute remote path")


    generation = env.get("OPENCODE_CONFIG_GENERATION", "v1").strip().lower()
    if generation not in {"v1", "v2"}:
        errors.append("OPENCODE_CONFIG_GENERATION must be v1 (stable/default) or v2 (beta opt-in)")
    if bool_env(env, "PROJECT_CONTEXT_MCP_ENABLED", True):
        from project_mcp import settings
        try:
            settings(env)
        except ValueError as exc:
            errors.append(str(exc))
        import os
        exe = ROOT / ("tmp/local/project-context/venv/Scripts/project-context-mcp.exe" if os.name == "nt" else "tmp/local/project-context/venv/bin/project-context-mcp")
        if not exe.exists():
            warnings.append("project-context MCP is enabled but not installed; run `python harness.py mcp-install`, then regenerate client config")

    if bool_env(env, "MINIMAX_ENABLED"):
        key = env.get("MINIMAX_TOKEN_PLAN_KEY", "")
        if not key.startswith("sk-cp-"):
            warnings.append("MINIMAX_TOKEN_PLAN_KEY does not look like an sk-cp Token Plan key")

    if bool_env(env, "LITELLM_EXPOSE_ON_TAILSCALE") and not bool_env(env, "LITELLM_ENABLED"):
        errors.append("LITELLM_EXPOSE_ON_TAILSCALE requires LITELLM_ENABLED")

    compose = (ROOT / "infra/compose.yaml").read_text(encoding="utf-8").lower()
    forbidden = (
        "firecrawl", "rabbitmq", "postgres", "project-bridge-edge", "project-dev",
        "hermes-bridge", "hermes-control-mcp",
    )
    for token in forbidden:
        if token in compose:
            errors.append(f"removed runtime component still present in compose: {token}")
    if re.search(r"(?m)^volumes:\s*$", compose):
        warnings.append("Compose contains a top-level named-volumes section; review disk persistence")

    for warning in warnings:
        print("WARN:", warning)
    if errors:
        for error in errors:
            print("ERROR:", error, file=sys.stderr)
        return 2
    print("Configuration: PASS")
    print("PROJECT_ROOT:", root)
    if bool_env(env, "HERMES_ENABLED"):
        print("Hermes client split: Claude=remote MCP sidecar; OpenCode=direct native Hermes Runs API tools; Codex=no Hermes transport")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
