"""Filesystem adapter package."""

from .fs_adapter import (
    DEFAULT_DISTRIBUTION_ROOT,
    DEFAULT_PROJECT_KNOWLEDGE_ROOT,
    DEFAULT_RUNTIME_CACHE_ROOT,
    LocalFilesystemAdapter,
    canonical_root_path,
    distribution_root_path,
    runtime_cache_path,
)

__all__ = [
    "DEFAULT_DISTRIBUTION_ROOT",
    "DEFAULT_PROJECT_KNOWLEDGE_ROOT",
    "DEFAULT_RUNTIME_CACHE_ROOT",
    "LocalFilesystemAdapter",
    "canonical_root_path",
    "distribution_root_path",
    "runtime_cache_path",
]