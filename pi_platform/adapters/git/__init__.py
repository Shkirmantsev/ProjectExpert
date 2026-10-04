"""Git adapter package."""

from .cli_adapter import GitCliAdapter, MINIMUM_GIT_VERSION

__all__ = ["GitCliAdapter", "MINIMUM_GIT_VERSION"]