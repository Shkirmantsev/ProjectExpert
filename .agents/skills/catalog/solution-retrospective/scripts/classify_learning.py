#!/usr/bin/env python3
"""Best-effort helper for deciding where a lesson should be persisted.

Input: free text from stdin or a file path argument.
Output: a recommendation among AGENTS.md, UPDATE_SKILL, CREATE_SKILL, or NONE.

This helper is intentionally conservative.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_HINTS = {
    "repo", "repository", "module", "package", "service", "directory", "path",
    "mvn", "gradle", "liquibase", "spring", "ci", "build", "test command",
    "codebase", "convention", "architecture", "folder", "generated", "schema",
}
WEAK_HINTS = {
    "typo", "temporary", "transient", "credential", "credentials", "network outage",
    "flaky", "incident", "once", "one-off", "vpn", "token expired",
}
REUSABLE_HINTS = {
    "workflow", "reusable", "across repos", "across repositories", "general",
    "verification strategy", "triage", "review routine", "investigation pattern",
    "search strategy", "debugging sequence", "repeatable",
}


def read_text() -> str:
    if len(sys.argv) > 1:
        return Path(sys.argv[1]).read_text(encoding="utf-8")
    return sys.stdin.read()


def score(text: str, hints: set[str]) -> int:
    t = text.lower()
    total = 0
    for h in hints:
        total += len(re.findall(re.escape(h), t))
    return total


def main() -> int:
    text = read_text().strip()
    if not text:
        print("NONE")
        return 0

    repo = score(text, REPO_HINTS)
    weak = score(text, WEAK_HINTS)
    reusable = score(text, REUSABLE_HINTS)

    if weak >= 2 and weak >= repo and weak >= reusable:
        print("NONE")
        return 0
    if repo >= 2 and repo >= reusable:
        print("AGENTS.md")
        return 0
    if reusable >= 3:
        print("UPDATE_OR_CREATE_PROJECT_SKILL")
        return 0
    if reusable >= 1 and repo == 0 and weak == 0:
        print("UPDATE_PROJECT_SKILL_IF_ONE_EXISTS")
        return 0

    print("NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
