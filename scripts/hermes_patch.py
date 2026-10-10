#!/usr/bin/env python3
"""Re-apply the harness Hermes resolver patch on the remote Hermes host.

This wraps ``scripts/apply_hermes_approval_patch.py`` with the SSH and
file-transfer mechanics the operator would otherwise do by hand. The
patch is selected from ``SUPPORTED_PATCHES`` based on the live source
revision; if no entry matches, we refuse to invent a target.

Typical operator flow:

    make hermes-patch REMOTE_USER=hermes
    make hermes-patch REMOTE_USER=hermes REMOTE_SOURCE=/srv/ai/hermes/.hermes/hermes-agent

Environment / .env keys used (all optional, defaults match a stock
Tailscale-protected install):

    HERMES_REMOTE_HOST           Tailscale DNS or IP of the remote Hermes host
    HERMES_REMOTE_OS_USER        SSH/copy account (default: hermes)
    HERMES_REMOTE_RUNTIME_HOME   Where the hermes profile lives
                                 (default: /srv/ai/hermes)

The script never touches secrets: it transfers only files under
``patches/hermes-agent/`` and restarts the gateway via the user systemd
manager.

If ``--restart-gateway`` is omitted we still print the exact restart
command so the operator can run it themselves — the prior state may be
serving active runs that should drain naturally.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from common import ROOT, parse_env, bool_env


# Local repo paths -------------------------------------------------------------

PATCH_DIR = ROOT / "patches/hermes-agent"

# Remote paths -----------------------------------------------------------------

REMOTE_STAGING_DIR = "/var/tmp/harness-hermes-resolver-patch"


def _env(env: dict[str, str], key: str, default: str) -> str:
    value = (env.get(key) or "").strip()
    return value or default


def _remote_source(env: dict[str, str], runtime_home: str) -> Path:
    """Default path to the live Hermes source checkout on the remote host.

    The ``hermes`` runtime account's checkout has been at
    ``.hermes/hermes-agent`` for every supported install; that is the
    only one we patch in-place.
    """
    return Path(runtime_home) / ".hermes/hermes-agent"


def _ssh(*args: str, user: str, host: str, port: int) -> list[str]:
    cmd = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", f"ConnectTimeout=8",
        "-p", str(port),
        f"{user}@{host}",
        *args,
    ]
    return cmd


def _rsync(local: Path, remote_user: str, remote_host: str, port: int, remote_dir: str) -> list[str]:
    return [
        "rsync",
        "-a",
        "-e", f"ssh -p {port} -o BatchMode=yes -o ConnectTimeout=8",
        str(local),
        f"{remote_user}@{remote_host}:{remote_dir}/",
    ]


def _run(cmd: list[str], **kwargs) -> None:
    print("+", " ".join(shlex.quote(c) for c in cmd))
    subprocess.run(cmd, check=True, **kwargs)


def main() -> int:
    env = parse_env()
    if not bool_env(env, "HERMES_ENABLED"):
        print("HERMES_ENABLED is not true in .env; nothing to do.", file=sys.stderr)
        return 1

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--remote-user", default=os.environ.get("HERMES_REMOTE_OS_USER")
                    or _env(env, "HERMES_REMOTE_OS_USER", "hermes"))
    ap.add_argument("--remote-host", default=os.environ.get("HERMES_REMOTE_HOST")
                    or _env(env, "HERMES_REMOTE_HOST", ""))
    ap.add_argument("--remote-source", default=None,
                    help="Absolute path to the live Hermes source checkout on the remote host")
    ap.add_argument("--remote-port", type=int,
                    default=int(os.environ.get("HERMES_SSH_PORT") or _env(env, "HERMES_SSH_PORT", "22")))
    ap.add_argument("--gateway-service", default="hermes-tailscale-worker-gateway.service",
                    help="systemd --user unit to restart after the patch lands")
    ap.add_argument("--check", action="store_true",
                    help="rsync + `git apply --check` only; do not apply or restart")
    ap.add_argument("--no-restart", action="store_true",
                    help="apply the patch but do not restart the gateway")
    args = ap.parse_args()

    if not args.remote_host:
        ap.error("remote host is required (--remote-host or HERMES_REMOTE_HOST in .env)")

    runtime_home = _env(env, "HERMES_REMOTE_RUNTIME_HOME", "/srv/ai/hermes")
    remote_source = Path(args.remote_source) if args.remote_source else _remote_source(env, runtime_home)

    # 1) Probe live revision on the remote.
    rev_cmd = _ssh("git", "-C", str(remote_source), "rev-parse", "HEAD",
                   user=args.remote_user, host=args.remote_host, port=args.remote_port)
    rev_proc = subprocess.run(rev_cmd, check=True, capture_output=True, text=True)
    revision = rev_proc.stdout.strip()
    print(f"remote Hermes HEAD: {revision}")

    # 2) Resolve the patch by importing the existing selector.
    sys.path.insert(0, str(ROOT / "scripts"))
    from apply_hermes_approval_patch import SUPPORTED_PATCHES  # type: ignore
    if revision not in SUPPORTED_PATCHES:
        print(
            f"Unsupported Hermes revision {revision}; expected one of:\n  "
            + "\n  ".join(sorted(SUPPORTED_PATCHES))
            + "\nRe-evaluate the patch against the installed upstream revision before adding a new entry.",
            file=sys.stderr,
        )
        return 2
    patch = SUPPORTED_PATCHES[revision]
    if not patch.is_file():
        print(f"Patch file missing locally: {patch}", file=sys.stderr)
        return 1

    # 3) Stage the patch on the remote (read-only copy under /var/tmp).
    stage_cmd = _ssh("mkdir", "-p", REMOTE_STAGING_DIR,
                     user=args.remote_user, host=args.remote_host, port=args.remote_port)
    _run(stage_cmd)
    rsync_cmd = _rsync(patch, args.remote_user, args.remote_host, args.remote_port, REMOTE_STAGING_DIR)
    if shutil.which("rsync") is None:
        print("rsync is not installed on this host; install it to use `make hermes-patch`.", file=sys.stderr)
        return 1
    _run(rsync_cmd)
    remote_patch = f"{REMOTE_STAGING_DIR}/{patch.name}"

    # 4) git apply [--check] on the remote, as the runtime user. If the patch is
    # already applied (re-run after a previous invocation, or a clean restart of
    # the harness), forward `git apply` rejects as a no-op. Fall back to a
    # reverse check so the operator gets a clear "ALREADY APPLIED" status
    # instead of a confusing patch failure.
    apply_args = ["git", "-C", str(remote_source), "apply", "--check", remote_patch] \
        if args.check else ["git", "-C", str(remote_source), "apply", remote_patch]
    apply_cmd = _ssh(*apply_args, user=args.remote_user, host=args.remote_host, port=args.remote_port)
    # Forward check is the primary path; stderr is intentionally silenced
    # because a non-zero exit is expected when the patch is already in place,
    # and we report that with a structured ALREADY APPLIED message below.
    proc = subprocess.run(apply_cmd, text=True, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        reverse_args = ["git", "-C", str(remote_source), "apply", "--reverse", "--check", remote_patch]
        reverse_cmd = _ssh(*reverse_args, user=args.remote_user, host=args.remote_host, port=args.remote_port)
        rev = subprocess.run(reverse_cmd, text=True)
        if rev.returncode == 0:
            print(f"Hermes approval patch: ALREADY APPLIED ({revision}); no-op.")
            if args.check or args.no_restart:
                return 0
        else:
            print(
                f"Patch does not apply forward or reverse against {revision};\n"
                "the source tree has drifted past the supported patch. Re-port the patch.",
                file=sys.stderr,
            )
            return 3
    else:
        print(f"Hermes approval patch: {'APPLICABLE' if args.check else 'APPLIED'} ({revision})")
        if args.check:
            return 0
        if args.no_restart:
            return 0

    if args.check or args.no_restart:
        return 0

    # 5) Restart the user systemd gateway unit on the remote.
    restart_cmd = _ssh(
        "systemctl", "--user", "restart", args.gateway_service,
        user=args.remote_user, host=args.remote_host, port=args.remote_port,
    )
    _run(restart_cmd)
    show_cmd = _ssh(
        "systemctl", "--user", "show",
        "-p", "MainPID,ActiveEnterTimestamp,SubState",
        args.gateway_service,
        user=args.remote_user, host=args.remote_host, port=args.remote_port,
    )
    subprocess.run(show_cmd, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
