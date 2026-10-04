#!/usr/bin/env python3
"""Check dated OpenSpec identities and the central accepted-state inventory."""
from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import re

SEMANTIC = r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*"
DATED = re.compile(rf"(\d{{4}}-\d{{2}}-\d{{2}})-({SEMANTIC})")


def dated_name(name: str) -> bool:
    match = DATED.fullmatch(name)
    if not match:
        return False
    try:
        date.fromisoformat(match[1])
    except ValueError:
        return False
    return not DATED.fullmatch(match[2])  # Reject stacked dates.


def validate_layout(root: Path) -> list[str]:
    errors = []
    specs = root / "specs"
    accepted = set()
    identities = {}
    for path in sorted(specs.iterdir()) if specs.exists() else []:
        if path.name.startswith("."):
            continue
        if not path.is_dir() or not dated_name(path.name) or not (path / "spec.md").is_file():
            errors.append(f"Invalid current spec: {path.name}; expected YYYY-MM-DD-domain-capability/spec.md")
        else:
            accepted.add(f"specs/{path.name}/spec.md")
            identities[DATED.fullmatch(path.name)[2]] = path.name
    changes = root / "changes"
    for path in sorted(changes.iterdir()) if changes.exists() else []:
        if not path.is_dir() or path.name.startswith("."):
            continue
        if path.name == "archive":
            for archive in sorted(path.iterdir()):
                if archive.is_dir() and not dated_name(archive.name):
                    errors.append(f"Invalid archive name: {archive.name}")
        elif not re.fullmatch(SEMANTIC, path.name):
            errors.append(f"Invalid active change name: {path.name}; expected undated kebab-case")
        if path.name != "archive":
            deltas = path / "specs"
            for delta in sorted(deltas.iterdir()) if deltas.is_dir() else []:
                if delta.name.startswith("."):
                    continue
                match = DATED.fullmatch(delta.name)
                valid_name = dated_name(delta.name) if match else bool(re.fullmatch(SEMANTIC, delta.name))
                if not delta.is_dir() or not valid_name:
                    errors.append(f"Invalid delta capability: {path.name}/specs/{delta.name}")
                    continue
                capability = match[2] if match else delta.name
                expected = identities.get(capability)
                if expected and delta.name != expected:
                    errors.append(f"Mismatched delta capability: {path.name}/specs/{delta.name}; expected {expected}")
    current = root / "CURRENT.md"
    if not current.is_file():
        errors.append("Missing central OpenSpec current state: CURRENT.md")
    else:
        # Relative canonical links are portable and do not duplicate requirement text.
        links = Counter(re.findall(r"\]\((specs/[^)]+)\)", current.read_text(encoding="utf-8")))
        for path in sorted(accepted - links.keys()):
            errors.append(f"Current state missing spec: {path}")
        for path in sorted(links.keys() - accepted):
            errors.append(f"Current state stale spec: {path}")
        for path, count in sorted(links.items()):
            if count != 1:
                errors.append(f"Current state duplicate spec: {path}")
        if re.search(r"\]\([^)]*changes/", current.read_text(encoding="utf-8")):
            errors.append("Current state must not link proposed or archived changes as accepted specs")
    return errors
