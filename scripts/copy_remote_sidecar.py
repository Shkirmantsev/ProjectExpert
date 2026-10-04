#!/usr/bin/env python3
from __future__ import annotations
import shutil, subprocess
from common import ROOT, parse_env


def main():
    env = parse_env()
    host = env.get("HERMES_REMOTE_HOST", "")
    user = env.get("HERMES_REMOTE_OS_USER", "hermes")
    staging = env.get("HERMES_REMOTE_STAGING_DIR", "/var/tmp/harness-hermes-worker-mcp")
    if not host or host.startswith("CHANGE_ME"):
        raise SystemExit("Configure HERMES_REMOTE_HOST in .env first")
    if not user or user.startswith("CHANGE_ME"):
        raise SystemExit("Configure HERMES_REMOTE_OS_USER in .env first (the SSH/login user used for copying)")
    if not staging.startswith("/"):
        raise SystemExit("HERMES_REMOTE_STAGING_DIR must be an absolute remote path")
    if not shutil.which("rsync"):
        raise SystemExit("rsync is required: sudo apt install rsync")

    src = ROOT / "remote/hermes-worker-mcp"
    remote = f"{user}@{host}"

    # Stage source in /var/tmp instead of the SSH user's home. The actual Hermes
    # runtime may be a different Linux user (for example SSH user=dimitri,
    # runtime user=hermes). The staged source contains no secrets and is made
    # read-only to other users so the Hermes runtime can import it safely.
    subprocess.run(["ssh", remote, "mkdir", "-p", staging], check=True)
    dest = f"{remote}:{staging.rstrip('/')}/"
    subprocess.run([
        "rsync", "-az", "--delete",
        "--exclude=.env", "--exclude=.venv", "--exclude=__pycache__", "--exclude=*.pyc",
        str(src) + "/", dest,
    ], check=True)
    subprocess.run([
        "ssh", remote,
        "chmod", "-R", "a+rX,go-w", staging,
    ], check=True)

    print("Remote Claude MCP sidecar source staged at", f"{remote}:{staging}/")
    print("No API key or sidecar token was copied. The remote setup instruction installs this source as the Hermes runtime user and creates/imports secrets locally.")


if __name__ == "__main__":
    main()
