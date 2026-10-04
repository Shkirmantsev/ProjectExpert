#!/usr/bin/env python3
"""Project-scoped Docker Compose wrapper with optional anonymous registry auth."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from common import ROOT, parse_env

PUBLIC_DOCKER_CONFIG = ROOT / ".generated" / "docker-public"


def docker_environment(mode: str, base: dict[str, str] | None = None, public_config: Path = PUBLIC_DOCKER_CONFIG) -> dict[str, str]:
    """Return Docker CLI env without creating a custom BuildKit builder.

    anonymous: use an empty project-local auth map for public images. This keeps
    stale/personal GHCR credentials out of this harness while still using the
    daemon's normal builder/cache. inherit: use the caller's normal Docker auth.
    """
    result = dict(os.environ if base is None else base)
    mode = (mode or "anonymous").strip().lower()
    if mode == "inherit":
        return result
    if mode != "anonymous":
        raise ValueError("HARNESS_DOCKER_AUTH_MODE must be 'anonymous' or 'inherit'")
    public_config.mkdir(parents=True, exist_ok=True)
    (public_config / "config.json").write_text(json.dumps({"auths": {}}, indent=2) + "\n")
    result["DOCKER_CONFIG"] = str(public_config)
    return result


def compose_command(arguments: list[str]) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-directory",
        str(ROOT),
        "--env-file",
        str(ROOT / ".env"),
        "-f",
        str(ROOT / "infra" / "compose.yaml"),
        *arguments,
    ]


def main() -> int:
    env = parse_env()
    try:
        process_env = docker_environment(env.get("HARNESS_DOCKER_AUTH_MODE", "anonymous"))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return subprocess.run(compose_command(sys.argv[1:]), env=process_env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
