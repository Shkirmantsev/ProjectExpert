#!/usr/bin/env python3
"""Apply the scoped /v1/runs approval resolver compatibility patch."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from common import ROOT


SUPPORTED_PATCHES = {
    "4f22543509d1b91dc45bcb369447126c5eb14fb7": (
        ROOT / "patches/hermes-agent/0001-resolver-backed-api-run-approvals.patch"
    ),
    # This legacy revision already binds a per-run approval session and
    # authenticated /v1/runs/{run_id}/approval resolver. Its deny lifecycle was
    # proven live before adding the capability declaration.
    "981101239a064c020a9d18fc3b1060ae306934ed": (
        ROOT
        / "patches/hermes-agent/0002-legacy-981101-advertise-run-approval-resolver.patch"
    ),
}


def run(source: Path, *args: str, capture: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        check=True,
        text=True,
        capture_output=capture,
    )
    return result.stdout.strip() if capture else ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply the harness Hermes resolver patch to a source checkout"
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--check", action="store_true", help="verify applicability only")
    args = parser.parse_args()
    source = args.source.expanduser().resolve()
    if not (source / ".git").exists():
        parser.error("--source must be a Hermes Agent git checkout")
    revision = run(source, "rev-parse", "HEAD", capture=True)
    patch = SUPPORTED_PATCHES.get(revision)
    if patch is None:
        raise SystemExit(
            f"Unsupported Hermes revision {revision}; expected one of "
            f"{', '.join(sorted(SUPPORTED_PATCHES))}. "
            "Re-evaluate the patch against the installed upstream revision."
        )
    command = ["apply", "--check", str(patch)]
    run(source, *command)
    if args.check:
        print(f"Hermes approval patch: APPLICABLE ({revision})")
        return 0
    run(source, "apply", str(patch))
    print(f"Hermes approval patch: APPLIED ({revision})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
