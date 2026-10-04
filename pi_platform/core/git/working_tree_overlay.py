"""Working-tree overlay capture.

The overlay is a deterministic JSON document describing the modified,
added, deleted and untracked paths under the target repository root.
The serialisation is stable across runs so the runtime cache and
hydration report can rely on it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ...adapters.git.cli_adapter import GitCliAdapter
from ...ports import WorkingTreeChange

__all__ = ["compute_working_tree_overlay"]


def compute_working_tree_overlay(repo_root: Path,
                                git_port: Optional[GitCliAdapter] = None
                                ) -> bytes:
    """Return a deterministic JSON document describing the working tree."""

    port = git_port or GitCliAdapter()
    try:
        changes = port.status(repo_root)
    except Exception:
        changes = []
    payload = {
        "schemaVersion": "0.1.0",
        "changes": [_change_to_dict(c) for c in sorted(changes,
                                                        key=lambda c: str(c.path))],
    }
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return (text + "\n").encode("utf-8")


def _change_to_dict(change: WorkingTreeChange) -> dict:
    return {"path": str(change.path), "kind": change.kind}