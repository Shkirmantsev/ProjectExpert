#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from common import ROOT, parse_env
from file_lock import file_lock


SOURCE = ROOT / ".agents" / "skills"
CATALOG = SOURCE / "catalog"
CLAUDE = ROOT / ".claude" / "skills"
OPENCODE = ROOT / ".opencode" / "skills"
CORE_SKILL_NAMES = (
    "project-safety",
    "session-checkpoint",
    "skill-router",
    "verification",
)


def exposed_skills() -> list[Path]:
    """Return the fixed harness-owned core, excluding tool-owned skills."""
    exposed = [SOURCE / name for name in CORE_SKILL_NAMES]
    missing = [path.name for path in exposed if not (path / "SKILL.md").is_file()]
    if missing:
        raise SystemExit("Missing harness core skills: " + ", ".join(missing))
    return exposed


def catalog_names() -> set[str]:
    if not CATALOG.exists():
        return set()
    return {
        path.parent.name
        for path in CATALOG.glob("*/SKILL.md")
        if path.parent.is_dir()
    }


def digest(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def sync_to(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    exposed = exposed_skills()
    managed_names = {path.name for path in exposed} | catalog_names() | {"catalog"}
    with tempfile.TemporaryDirectory(prefix=".harness-skill-stage-", dir=destination) as raw:
        staging = Path(raw)
        for source in exposed:
            shutil.copytree(source, staging / source.name)

        with file_lock(destination / ".harness-sync.lock"):
            # Publish complete staged trees while serializing writers. Preserve
            # client-owned skills (including OpenSpec-generated skills).
            for source in exposed:
                target = destination / source.name
                incoming = staging / source.name
                backup = destination / f".{source.name}.harness-backup-{os.getpid()}"
                if backup.exists():
                    shutil.rmtree(backup)
                if target.exists():
                    os.replace(target, backup)
                try:
                    os.replace(incoming, target)
                except Exception:
                    if backup.exists() and not target.exists():
                        os.replace(backup, target)
                    raise
                shutil.rmtree(backup, ignore_errors=True)

            # Remove only stale names owned by this project. Personal/unrelated
            # Client skills are intentionally left untouched.
            for target in destination.iterdir():
                if (
                    target.is_dir()
                    and target.name in managed_names
                    and target.name not in CORE_SKILL_NAMES
                ):
                    shutil.rmtree(target)


def local() -> None:
    for destination in (CLAUDE, OPENCODE):
        sync_to(destination)
    print(f"Synced {len(exposed_skills())} core skills to Claude and OpenCode; "
          "Codex uses canonical .agents/skills; optional catalog stays on demand.")


def remote() -> None:
    env = parse_env()
    host = env.get("HERMES_REMOTE_HOST", "")
    os_user = env.get("HERMES_REMOTE_OS_USER", "hermes")
    profile = env.get("HERMES_REMOTE_PROFILE", "hermes-tailscale-worker")
    if not host or host.startswith("CHANGE_ME"):
        raise SystemExit("Configure HERMES_REMOTE_HOST first")
    destination = (
        f"{os_user}@{host}:~/.hermes/profiles/{profile}/skills/harness-layout/"
    )

    # Sync a clean core-only staging tree. Optional skills remain available at
    # canonical project paths through Hermes' native SSH repository access.
    with tempfile.TemporaryDirectory(prefix="harness-core-skills-") as raw:
        staging = Path(raw)
        for source in exposed_skills():
            shutil.copytree(source, staging / source.name)
        subprocess.run(
            [
                "rsync",
                "-az",
                "--delete",
                "--exclude=.env",
                "--exclude=.git",
                f"{staging}/",
                destination,
            ],
            check=True,
        )
    print("Remote core skills synced to", destination)


def check_target(destination: Path) -> None:
    exposed = exposed_skills()
    for source in exposed:
        target = destination / source.name
        if not target.is_dir() or digest(source) != digest(target):
            raise SystemExit(
                f"Client core skill differs from canonical source in {destination}: {source.name}"
            )

    leaked = sorted(
        name for name in catalog_names() | {"catalog"} if (destination / name).exists()
    )
    if leaked:
        raise SystemExit(
            f"Optional catalog skills are directly exposed in {destination}: "
            + ", ".join(leaked)
        )


def check() -> None:
    for destination in (CLAUDE, OPENCODE):
        check_target(destination)
    print(f"Local skills: PASS ({len(exposed_skills())} core, "
          f"{len(catalog_names())} on demand; Claude and OpenCode mirrors)")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("scope", choices=("local", "remote", "check"))
    args = parser.parse_args()
    if args.scope == "local":
        local()
    elif args.scope == "remote":
        remote()
    else:
        check()


if __name__ == "__main__":
    main()
