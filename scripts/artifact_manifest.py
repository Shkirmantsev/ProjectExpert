#!/usr/bin/env python3
"""Generate and verify the repository's deterministic SHA-256 manifest."""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from pathlib import Path

from common import ROOT, atomic_write_text


MANIFEST = ROOT / "ARTIFACT_MANIFEST.sha256"
EXCLUDED_PREFIXES = (
    ".ai/state/",
    ".claude/commands/opsx/",
    ".claude/skills/",
    ".opencode/commands/opsx-",
    ".opencode/skills/openspec-",
    ".agents/skills/openspec-",
)
EXCLUDED_EXACT = {
    "ARTIFACT_MANIFEST.sha256",
    ".agents/skills/.openspec-target",
}


def manifest_paths() -> set[str]:
    """Return paths already owned by the manifest.

    Keeping existing entries lets a developer verify newly created project files
    before they are staged, without treating every unrelated untracked file in a
    working tree as a release artifact.
    """
    if not MANIFEST.exists():
        return set()
    paths = set()
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        _, separator, raw_path = line.partition("  ./")
        if separator and raw_path:
            paths.add(raw_path)
    return paths


def git_paths(*, include_untracked: bool) -> set[str]:
    command = ["git", "ls-files", "-z", "--cached"]
    if include_untracked:
        command.extend(("--others", "--exclude-standard"))
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    return {raw.decode("utf-8") for raw in result.stdout.split(b"\0") if raw}


def owned_paths(
    *, include_untracked: bool = False, additions: tuple[str, ...] = ()
) -> list[Path]:
    relative_paths = git_paths(include_untracked=include_untracked)
    relative_paths.update(manifest_paths())
    for raw in additions:
        candidate = (ROOT / raw).resolve()
        try:
            relative = candidate.relative_to(ROOT.resolve()).as_posix()
        except ValueError as exc:
            raise SystemExit(f"Artifact path is outside the repository: {raw}") from exc
        if not candidate.is_file():
            raise SystemExit(f"Artifact path is not a file: {raw}")
        relative_paths.add(relative)
    paths = []
    for relative in relative_paths:
        if relative in EXCLUDED_EXACT or relative.startswith(EXCLUDED_PREFIXES):
            continue
        path = ROOT / relative
        if path.is_file():
            paths.append(path)
    return sorted(paths, key=lambda item: item.relative_to(ROOT).as_posix())


def render(*, include_untracked: bool = False, additions: tuple[str, ...] = ()) -> str:
    lines = []
    for path in owned_paths(
        include_untracked=include_untracked, additions=additions
    ):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(ROOT).as_posix()
        lines.append(f"{digest}  ./{relative}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("generate", "verify"))
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="adopt all currently unignored untracked files when generating",
    )
    parser.add_argument(
        "--add",
        action="append",
        default=[],
        metavar="PATH",
        help="adopt one specific repository file when generating; repeatable",
    )
    args = parser.parse_args()
    if args.action == "verify" and (args.include_untracked or args.add):
        parser.error("--include-untracked and --add are valid only with generate")
    expected = render(
        include_untracked=args.include_untracked,
        additions=tuple(args.add),
    )
    if args.action == "generate":
        atomic_write_text(MANIFEST, expected)
        print(f"Artifact manifest: GENERATED ({len(expected.splitlines())} files)")
        return 0
    actual = MANIFEST.read_text(encoding="utf-8") if MANIFEST.exists() else ""
    if actual != expected:
        raise SystemExit(
            "Artifact manifest: FAIL (run `python scripts/artifact_manifest.py generate`)"
        )
    print(f"Artifact manifest: PASS ({len(expected.splitlines())} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
