#!/usr/bin/env python3
"""Emit a deterministic, content-light repository profile."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from common import ROOT


EXCLUDED_PARTS = {
    ".git",
    ".generated",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "tmp",
    "graphify-out",
}
SECRET_NAMES = {".env", "auth.json", "credentials.json"}
EXCLUDED_PREFIXES = (
    ".agents/skills/catalog/",
    ".claude/skills/",
)
LANGUAGES = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".java": "java",
    ".kt": "kotlin",
    ".rs": "rust",
    ".sh": "shell",
    ".ps1": "powershell",
    ".tf": "terraform",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
}
BUILD_FILES = {
    "Makefile",
    "pyproject.toml",
    "requirements.txt",
    "package.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "package-lock.json",
    "go.mod",
    "pom.xml",
    "mvnw",
    "gradlew",
    "Cargo.toml",
    "angular.json",
    "ionic.config.json",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
}
INSTRUCTION_FILES = {"AGENTS.md", "AGENT.md", "CLAUDE.md", "README.md"}


def allowed(path: Path) -> bool:
    if path.as_posix().startswith(EXCLUDED_PREFIXES):
        return False
    parts = set(path.parts)
    if parts.intersection(EXCLUDED_PARTS):
        return False
    name = path.name.lower()
    if name in SECRET_NAMES or name.startswith(".env."):
        return False
    return True


def repository_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(ROOT), "ls-files", "-co", "--exclude-standard"],
            text=True,
            capture_output=True,
            check=True,
        )
        candidates = [Path(line) for line in result.stdout.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        candidates = []
        for base, directories, names in os.walk(ROOT):
            directories[:] = sorted(
                name for name in directories if name not in EXCLUDED_PARTS
            )
            parent = Path(base)
            candidates.extend((parent / name).relative_to(ROOT) for name in sorted(names))
    return sorted(
        path
        for path in candidates
        if allowed(path) and (ROOT / path).is_file()
    )


def make_targets() -> list[str]:
    path = ROOT / "Makefile"
    if not path.is_file():
        return []
    targets = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+):(?:\s|$)", line)
        if match and not match.group(1).startswith("."):
            targets.add(match.group(1))
    return sorted(targets)


def package_scripts() -> list[str]:
    path = ROOT / "package.json"
    if not path.is_file():
        return []
    try:
        scripts = json.loads(path.read_text(encoding="utf-8")).get("scripts", {})
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    return sorted(scripts) if isinstance(scripts, dict) else []


def build_profile() -> dict:
    files = repository_files()
    languages: dict[str, int] = {}
    for path in files:
        language = LANGUAGES.get(path.suffix.lower())
        if language:
            languages[language] = languages.get(language, 0) + 1

    build_files = sorted(path.as_posix() for path in files if path.name in BUILD_FILES)
    instructions = sorted(
        path.as_posix() for path in files if path.name in INSTRUCTION_FILES
    )
    contract_hashes = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
        for path in sorted(set(build_files + instructions))
    }
    test_roots = sorted(
        {
            path.parts[0]
            for path in files
            if path.parts
            and (
                path.parts[0] in {"test", "tests", "spec", "specs"}
                or path.name.startswith("test_")
                or path.name.endswith(("_test.py", ".test.js", ".test.ts", ".spec.ts"))
            )
        }
    )
    profile = {
        "schema_version": "1.0",
        "root": ".",
        "build_files": build_files,
        "instruction_files": instructions,
        "contract_hashes": contract_hashes,
        "languages": dict(sorted(languages.items())),
        "test_roots": test_roots,
        "make_targets": make_targets(),
        "package_scripts": package_scripts(),
        "capabilities": {
            "docker": any("docker" in path.lower() or "compose" in path.lower() for path in build_files),
            "git": (ROOT / ".git").exists(),
            "python": "python" in languages,
            "node": any(path.endswith("package.json") for path in build_files),
        },
    }
    canonical = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
    profile["profile_hash"] = "sha256:" + hashlib.sha256(canonical).hexdigest()
    return profile


def main() -> int:
    print(json.dumps(build_profile(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
