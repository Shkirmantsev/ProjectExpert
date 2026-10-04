#!/usr/bin/env python3
"""Print the LiteLLM model catalogue without executing .env as shell code."""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

from common import parse_env


def fetch_models(url: str, key: str) -> object:
    request = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


def main() -> int:
    env = parse_env()
    key = env.get("LITELLM_MASTER_KEY", "")
    port = env.get("LITELLM_PORT", "4000")
    if not key or key == "AUTO_GENERATE":
        print("ERROR: LITELLM_MASTER_KEY is not initialized; run `make init`.", file=sys.stderr)
        return 2
    try:
        models = fetch_models(f"http://127.0.0.1:{port}/v1/models", key)
    except (OSError, ValueError, json.JSONDecodeError, urllib.error.HTTPError) as exc:
        print(f"ERROR: LiteLLM model catalogue is unavailable: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(models, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
