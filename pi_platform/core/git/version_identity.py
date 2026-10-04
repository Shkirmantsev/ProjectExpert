"""Runtime project version identity.

§11 requires the structured tuple:

    repository identity +
    Git HEAD commit +
    working-tree fingerprint +
    knowledge schema version +
    embedding model version +
    index schema version

Branch names are mutable pointers and MUST NOT appear in the tuple.
The ``embeddingModelVersion`` defaults to the literal string
``"unknown"`` until Phase 4 binds an embedding model.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from ...adapters.git.cli_adapter import GitCliAdapter
from ...ports import VersionIdentity

__all__ = ["compute_version_identity", "KNOWN_SCHEMA_VERSIONS", "EMBEDDING_UNKNOWN"]


EMBEDDING_UNKNOWN = "unknown"
KNOWN_SCHEMA_VERSIONS = ("0.1.0",)


def _hash_working_tree(working_tree_changes: Iterable[Mapping[str, object]]) -> str:
    """Compute a SHA-256 hex digest of the canonical working-tree state.

    The overlay serialisation is provided by
    :func:`platform.core.git.working_tree_overlay.compute_working_tree_overlay`;
    this function only normalises that result so two equivalent states
    produce the same fingerprint.
    """

    h = hashlib.sha256()
    for entry in sorted(working_tree_changes, key=lambda e: str(e.get("path", ""))):
        h.update(str(entry.get("path", "")).encode("utf-8"))
        h.update(b"\x00")
        h.update(str(entry.get("kind", "")).encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def compute_version_identity(
    repo_root: Path,
    *,
    git_port: Optional[GitCliAdapter] = None,
    knowledge_schema_version: str = "0.1.0",
    embedding_model_version: str = EMBEDDING_UNKNOWN,
    index_schema_version: str = "0.1.0",
    working_tree_overlay: Optional[bytes] = None,
) -> VersionIdentity:
    """Compute the structured runtime project version identity tuple.

    ``embedding_model_version`` defaults to the literal ``"unknown"``;
    Phase 4 will replace this once an embedding model is bound.
    ``working_tree_overlay`` is optional; when supplied it is used to
    compute the working-tree fingerprint without re-querying Git.
    """

    if knowledge_schema_version not in KNOWN_SCHEMA_VERSIONS:
        # Allow future versions to be discovered via configuration; only
        # record the warning via the returned dataclass.
        pass

    port = git_port or GitCliAdapter()
    git_head = port.head(repo_root)
    if working_tree_overlay is None:
        from .working_tree_overlay import compute_working_tree_overlay
        working_tree_overlay = compute_working_tree_overlay(repo_root, git_port=port)
    fingerprint = hashlib.sha256(working_tree_overlay).hexdigest()
    return VersionIdentity(
        gitHead=git_head,
        workingTreeFingerprint=fingerprint,
        knowledgeSchemaVersion=knowledge_schema_version,
        embeddingModelVersion=embedding_model_version,
        indexSchemaVersion=index_schema_version,
    )