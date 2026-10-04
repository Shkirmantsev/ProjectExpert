#!/usr/bin/env python3
from __future__ import annotations
import subprocess, sys
from common import ROOT, parse_env, bool_env

PROFILE_FLAGS = [
    ("LITELLM_ENABLED", "litellm"),
    ("WEB_SEARCH_ENABLED", "web-search"),
    ("CRAWL4AI_ENABLED", "crawl4ai"),
    ("PLAYWRIGHT_ENABLED", "playwright"),
    ("LITELLM_EXPOSE_ON_TAILSCALE", "tailscale-expose"),
]
PROFILE_SERVICES = {
    "litellm": ["litellm"],
    "web-search": ["searxng", "searxng-mcp"],
    "crawl4ai": ["crawl4ai", "crawl4ai-http-bridge"],
    "playwright": ["playwright-mcp"],
    "tailscale-expose": ["litellm-edge"],
}

def profiles(env):
    out = [profile for key, profile in PROFILE_FLAGS if bool_env(env, key)]
    if "tailscale-expose" in out and "litellm" not in out:
        raise RuntimeError("LITELLM_EXPOSE_ON_TAILSCALE=true requires LITELLM_ENABLED=true")
    return out

def compose(args: list[str]) -> int:
    return subprocess.run([sys.executable, str(ROOT / "scripts/docker_compose.py"), *args]).returncode

def profiled_args(ps: list[str], rest: list[str]) -> list[str]:
    args = []
    for p in ps:
        args += ["--profile", p]
    return args + rest

def main() -> int:
    if len(sys.argv) < 2:
        raise SystemExit("usage: stack.py plan|up|start|stop|down|status|logs|pull|build|config")
    action = sys.argv[1]
    env = parse_env()
    ps = profiles(env)
    if action == "plan":
        print("Enabled local profiles:", ", ".join(ps) if ps else "none")
        services = []
        for p in ps:
            services.extend(PROFILE_SERVICES[p])
        print("Local services:", ", ".join(services) if services else "none")
        print(f"Declared local service count: {sum(len(v) for v in PROFILE_SERVICES.values())}; enabled: {len(services)}")
        print("Remote Hermes:", "enabled (external; no local container)" if bool_env(env, "HERMES_ENABLED") else "disabled")
        return 0
    if action in {"stop", "down", "status", "logs"}:
        prefix = ["--profile", "*"]
        cmd = {
            "stop": ["stop"],
            "down": ["down", "--remove-orphans"],
            "status": ["ps", "-a"],
            "logs": ["logs", "--tail=200"],
        }[action]
        return compose(prefix + cmd + sys.argv[2:])
    if action == "up":
        rc = compose(["--profile", "*", "down", "--remove-orphans"])
        if rc:
            return rc
        if not ps:
            print("No local services enabled. Remote Hermes, if enabled, is managed on its own host.")
            return 0
        return compose(profiled_args(ps, ["up", "-d", "--build", "--remove-orphans", *sys.argv[2:]]))
    if action == "start":
        return 0 if not ps else compose(profiled_args(ps, ["start", *sys.argv[2:]]))
    if action == "pull":
        # Pull real upstream images (LiteLLM, SearXNG, Crawl4AI, Playwright)
        # while skipping services that are intentionally built from local
        # harness Dockerfiles (MCP adapters / edge helpers).
        return 0 if not ps else compose(profiled_args(ps, ["pull", "--ignore-buildable", *sys.argv[2:]]))
    if action in {"build", "config"}:
        return 0 if not ps else compose(profiled_args(ps, [{"build":"build","config":"config"}[action], *sys.argv[2:]]))
    raise SystemExit(f"unknown action: {action}")

if __name__ == "__main__":
    raise SystemExit(main())
