"""Implementation of the GitPort contract.

The CLI adapter lives in :mod:`platform.adapters.git.cli_adapter` so
the Git core stays adapter-free; this file merely re-exports the
default implementation for callers that do not want to import from
:mod:`platform.adapters.git` directly.
"""

from __future__ import annotations

from ...adapters.git.cli_adapter import GitCliAdapter, MINIMUM_GIT_VERSION

__all__ = ["GitCliAdapter", "MINIMUM_GIT_VERSION"]