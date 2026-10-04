#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def parse() -> dict[str, str]:
    if not ENV.exists():
        raise SystemExit(".env missing; run `make init`")
    out: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


env = parse()
required = ("SIDECAR_TAILSCALE_HOST", "SIDECAR_TAILSCALE_IP", "HERMES_SIDECAR_TOKEN", "HERMES_API_BASE_URL", "HERMES_API_KEY")
for key in required:
    value = env.get(key, "")
    if not value or value.startswith("CHANGE_ME") or value == "AUTO_GENERATE":
        raise SystemExit(f"{key} is not configured")
if len(env["HERMES_SIDECAR_TOKEN"]) < 32:
    raise SystemExit("HERMES_SIDECAR_TOKEN must be >= 32 characters")
try:
    ipaddress.ip_address(env["SIDECAR_TAILSCALE_IP"])
except ValueError as exc:
    raise SystemExit("SIDECAR_TAILSCALE_IP is invalid") from exc
base = env["HERMES_API_BASE_URL"].rstrip("/")
if base.endswith("/v1"):
    raise SystemExit("HERMES_API_BASE_URL must be the server root without /v1")
if base not in {"http://127.0.0.1:8642", "http://localhost:8642"}:
    print(f"WARN: non-default Hermes local upstream: {base}")
print("Configuration: PASS")
