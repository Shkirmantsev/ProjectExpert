#!/usr/bin/env python3
from __future__ import annotations
import json, os, re, sys, urllib.request
from pathlib import Path
from common import parse_env, bool_env, project_root

def get(url, key="", timeout=8):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.loads(response.read() or b"{}")

def post(url, payload, key="", timeout=120):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.status, json.loads(response.read() or b"{}")

def ver_tuple(value):
    return tuple(int(x) for x in re.findall(r"\d+", value)[:3])

def main():
    only_hermes = "--only-hermes" in sys.argv[1:]
    env = parse_env()
    failures = []

    if not only_hermes and bool_env(env, "LITELLM_ENABLED"):
        try:
            st, _ = get(f"http://127.0.0.1:{env.get('LITELLM_PORT','18400')}/health/liveliness", env.get("LITELLM_MASTER_KEY", ""))
            print("LiteLLM:", st)
        except Exception as exc:
            failures.append(f"LiteLLM: {exc}")

    if bool_env(env, "HERMES_ENABLED"):
        base = f"{env.get('HERMES_REMOTE_SCHEME','http')}://{env['HERMES_REMOTE_HOST']}:{env.get('HERMES_REMOTE_OPENAI_PORT','8642')}"
        sidecar = f"{env.get('HERMES_SIDECAR_SCHEME','http')}://{env['HERMES_REMOTE_HOST']}:{env.get('HERMES_REMOTE_SIDECAR_PORT','8775')}"
        try:
            st, health = get(base + "/health")
            print("Hermes native API health:", st, health.get("version", "unknown"))
            version = str(health.get("version", "")).lstrip("v")
            if version and ver_tuple(version) < ver_tuple(env.get("HERMES_MIN_VERSION", "0.20.5")):
                failures.append(f"Hermes {version} is older than required {env.get('HERMES_MIN_VERSION')}")
            st, models = get(base + "/v1/models", env["HERMES_REMOTE_API_KEY"])
            ids = {item.get("id") for item in models.get("data", [])}
            print("Hermes models:", sorted(x for x in ids if x))
            if env.get("HERMES_REMOTE_MODEL") not in ids:
                failures.append("Configured HERMES_REMOTE_MODEL is not advertised")
            st, capabilities = get(
                base + "/v1/capabilities", env["HERMES_REMOTE_API_KEY"]
            )
            features = capabilities.get("features", {})
            resolver = features.get("resolver_scoped_run_approvals") is True
            print("Hermes resolver-scoped run approvals:", "PASS" if resolver else "MISSING")
            if not resolver:
                failures.append(
                    "Hermes lacks resolver_scoped_run_approvals; apply the "
                    "harness compatibility patch before OpenCode delegation"
                )
        except Exception as exc:
            failures.append(f"Hermes native API: {exc}")

        try:
            st, state = get(sidecar + "/healthz", env["HERMES_SIDECAR_TOKEN"])
            print("Claude Hermes MCP sidecar:", st, state.get("status", "unknown"))
            if state.get("status") not in {"ok", "degraded"}:
                failures.append("Hermes MCP sidecar returned unexpected status")
            if state.get("upstream") is False:
                failures.append("Hermes MCP sidecar cannot reach native Hermes API")
        except Exception as exc:
            failures.append(f"Claude Hermes MCP sidecar: {exc}")

        if os.getenv("VERIFY_REMOTE_INFERENCE", "0").lower() in {"1", "true", "yes"}:
            root = str(project_root(env).resolve())
            payload = {
                "input": "Report the repository working directory and list the root without modifying files.",
                "session_id": "harness-verify-native",
                "instructions": f"Use your own native SSH-backed tools. Establish repository context at {root} and stay inside that repository.",
            }
            try:
                st, result = post(base + "/v1/runs", payload, env["HERMES_REMOTE_API_KEY"], 30)
                print("Hermes native run submission:", st, result.get("run_id", "missing"))
            except Exception as exc:
                failures.append(f"Hermes native inference submission: {exc}")
        else:
            print("Hermes native inference: NOT RUN (set VERIFY_REMOTE_INFERENCE=1)")

    if not only_hermes:
        for key, port, path in (
            ("WEB_SEARCH_ENABLED", "SEARXNG_MCP_PORT", "/healthz"),
            ("CRAWL4AI_ENABLED", "CRAWL4AI_MCP_BRIDGE_PORT", "/healthz"),
        ):
            if bool_env(env, key):
                try:
                    st, _ = get(f"http://127.0.0.1:{env[port]}{path}")
                    print(key, st)
                except Exception as exc:
                    failures.append(f"{key}: {exc}")

    if failures:
        for failure in failures:
            print("FAIL:", failure, file=sys.stderr)
        return 2
    print("Verification: PASS (subject to NOT RUN items above)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
