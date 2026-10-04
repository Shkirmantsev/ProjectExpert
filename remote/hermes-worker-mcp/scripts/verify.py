#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def get(url: str, key: str = ""):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as response:
        return response.status, json.loads(response.read() or b"{}")


env = parse()
root = env["HERMES_API_BASE_URL"].rstrip("/")
status, health = get(root + "/health")
print("Hermes health:", status, health.get("status", "unknown"))
status, models = get(root + "/v1/models", env["HERMES_API_KEY"])
print("Hermes /v1/models:", status, [x.get("id") for x in models.get("data", [])])
sidecar = f"http://{env['SIDECAR_TAILSCALE_HOST']}:{env.get('SIDECAR_PORT','8775')}"
try:
    get(sidecar + "/healthz")
    raise SystemExit("FAIL: unauthenticated sidecar health unexpectedly succeeded")
except urllib.error.HTTPError as exc:
    if exc.code != 401:
        raise
    print("Unauthenticated sidecar health: 401 PASS")
status, side = get(sidecar + "/healthz", env["HERMES_SIDECAR_TOKEN"])
print("Authenticated sidecar health:", status, side.get("status"), "upstream=", side.get("upstream"))
if side.get("upstream") is not True:
    raise SystemExit("FAIL: sidecar cannot reach native Hermes API")
print("Verification: PASS")
