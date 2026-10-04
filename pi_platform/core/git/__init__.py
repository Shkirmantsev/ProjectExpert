"""Git core package: ports and adapters for version-aware runtime."""

from .git_port import GitCliAdapter, MINIMUM_GIT_VERSION
from .version_identity import compute_version_identity, KNOWN_SCHEMA_VERSIONS
from .working_tree_overlay import compute_working_tree_overlay

__all__ = [
    "GitCliAdapter",
    "MINIMUM_GIT_VERSION",
    "compute_version_identity",
    "compute_working_tree_overlay",
    "KNOWN_SCHEMA_VERSIONS",
]