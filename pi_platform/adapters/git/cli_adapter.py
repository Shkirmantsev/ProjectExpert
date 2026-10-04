"""Git CLI adapter implementing the :class:`GitPort` contract.

Phase 1 uses the system ``git`` binary exclusively. The adapter has a
documented minimum version contract (``>= 2.30``) so the platform can
rely on ``--no-pager``, ``--format=%H`` and ``--raw`` being available.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ...ports import GitPort, GitPortError, WorkingTreeChange

__all__ = ["GitCliAdapter", "MINIMUM_GIT_VERSION"]


MINIMUM_GIT_VERSION = (2, 30)


def _git_version_from_string(raw: str) -> tuple[int, ...]:
    """Parse ``git --version`` output like ``git version 2.43.0``."""
    text = raw.strip()
    # Strip the leading "git version " prefix; ignore trailing extra
    # tokens such as the optional ``-rc0`` suffix or vendor tags.
    if text.startswith("git version "):
        text = text[len("git version "):]
    version = text.split()[0]
    parts = version.split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError as exc:
        raise GitPortError(f"could not parse git version output: {raw!r}") from exc


class GitCliAdapter(GitPort):
    """Default Git port backed by the system ``git`` binary."""

    def __init__(self, *, binary: Optional[str] = None,
                 minimum_version: tuple[int, ...] = MINIMUM_GIT_VERSION):
        self._binary = binary or shutil.which("git")
        if not self._binary:
            raise GitPortError(
                "git executable not found in PATH; install git >= "
                f"{'.'.join(str(p) for p in minimum_version)} or "
                "configure the Git CLI adapter binary path"
            )
        self._minimum_version = minimum_version
        self._verified: Optional[tuple[int, ...]] = None

    @property
    def binary(self) -> str:
        assert self._binary is not None  # for type checkers
        return self._binary

    def version(self) -> tuple[int, ...]:
        if self._verified is None:
            out = subprocess.run(
                [self.binary, "--version"],
                capture_output=True, text=True, check=True,
            )
            parsed = _git_version_from_string(out.stdout)
            if parsed < self._minimum_version:
                raise GitPortError(
                    f"git version {'.'.join(str(p) for p in parsed)} is below "
                    f"the minimum required {'.'.join(str(p) for p in self._minimum_version)}"
                )
            self._verified = parsed
        return self._verified

    def _run(self, repo_root: Path, args: list[str],
             *, capture_output: bool = True) -> subprocess.CompletedProcess:
        self.version()  # validate minimum version before each invocation
        return subprocess.run(
            [self.binary, "-C", str(repo_root), *args],
            capture_output=capture_output, text=True,
            check=False,
        )

    def head(self, repo_root: Path) -> str:
        result = self._run(repo_root, ["rev-parse", "HEAD"])
        if result.returncode != 0:
            raise GitPortError(
                f"git rev-parse HEAD failed in {repo_root}: {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def current_branch(self, repo_root: Path) -> Optional[str]:
        result = self._run(repo_root, ["rev-parse", "--abbrev-ref", "HEAD"])
        if result.returncode != 0:
            return None
        name = result.stdout.strip()
        return name if name and name != "HEAD" else None

    def status(self, repo_root: Path) -> list[WorkingTreeChange]:
        result = self._run(repo_root, ["status", "--porcelain=1", "-z"])
        if result.returncode != 0:
            raise GitPortError(
                f"git status failed in {repo_root}: {result.stderr.strip()}"
            )
        changes: list[WorkingTreeChange] = []
        raw = result.stdout.replace("\u0000", "")
        for line in raw.splitlines():
            if not line.strip():
                continue
            if len(line) < 3:
                continue
            code, path = line[:2], line[3:].strip()
            kind = self._classify(code)
            if kind is None:
                continue
            changes.append(WorkingTreeChange(path=Path(path), kind=kind))
        return changes

    @staticmethod
    def _classify(code: str) -> Optional[str]:
        if code == "??":
            return "untracked"
        if code == "!!":
            return "ignored"
        x, y = code[0], code[1]
        if x in ("M", "T", "A", "R", "C") and y in ("M", "T", "A", "R", "C", " ", "?"):
            return "modified"
        if x == "D" or y == "D":
            return "deleted"
        if x == "A":
            return "added"
        if x == "R":
            return "renamed"
        return "modified"

    def lfs_pointer_for(self, repo_root: Path, path: Path) -> Optional[str]:
        result = self._run(repo_root, ["check-attr", "--", "filter", str(path)])
        if result.returncode != 0:
            return None
        attrs = result.stdout.strip()
        if "lfs" not in attrs.split():
            return None
        pointer = self._run(repo_root, ["show", f":0:{path}"])
        if pointer.returncode != 0:
            return None
        for line in pointer.stdout.splitlines():
            if line.startswith("oid sha256:"):
                return line.split(":", 2)[1].strip()
        return None