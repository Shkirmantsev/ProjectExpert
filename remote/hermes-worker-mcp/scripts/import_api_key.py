#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"


def parse(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


if not ENV.exists():
    raise SystemExit("Run `make init` first")
env = parse(ENV)
profile_home = env.get("HERMES_PROFILE_HOME", "").strip()
if not profile_home or profile_home.startswith("CHANGE_ME"):
    raise SystemExit("Set HERMES_PROFILE_HOME to the existing hermes-tailscale-worker profile path")
profile_env = Path(profile_home).expanduser() / ".env"
if not profile_env.is_file():
    raise SystemExit(f"Worker profile .env not found: {profile_env}")
api_key = parse(profile_env).get("API_SERVER_KEY", "")
if not api_key:
    raise SystemExit("API_SERVER_KEY not found in worker profile .env")
text = ENV.read_text(encoding="utf-8")
text = re.sub(r"(?m)^HERMES_API_KEY=.*$", f"HERMES_API_KEY={api_key}", text)
ENV.write_text(text, encoding="utf-8")
ENV.chmod(0o600)
print("Imported existing API_SERVER_KEY into sidecar .env without printing it.")
