"""Dense-index backend selection.

Implements the ``dense_index.backend ∈ {auto, flat, usearch}``
configuration knob from plan §17. ``auto`` may choose flat vs
USearch based on benchmarked corpus size and recall constraints;
the choice is data-driven, not hard-coded as an architectural
invariant.

This module is stdlib-only. The USearch adapter is the
production-stub from :mod:`pi_platform.adapters.runtime.usearch_dense_index`
(D.1.5). When the real ``usearch`` binding lands (a follow-up
that imports the optional dependency), ``select_dense_index``
will be the only call site that needs to know about backend
plumbing.
"""

from __future__ import annotations

from typing import Optional

from pi_platform.ports.runtime.dense_index import DenseIndexError, DenseIndexPort

from pi_platform.adapters.runtime.flat_dense_index import FlatDenseIndex
from pi_platform.adapters.runtime.usearch_dense_index import USearchDenseIndex


__all__ = [
    "DenseIndexBackend",
    "AUTO_FLAT_CORPUS_THRESHOLD",
    "select_dense_index",
    "AutoCorpusSizeError",
]


# Architectural choice is data-driven, not a hard threshold. The
# default threshold is the smallest corpus size at which the
# USearch adapter's amortised build cost is justified on a
# representative benchmark. Operators may override it per
# deployment. Tests assert ``select_dense_index(..., backend=
# "auto", corpus_size=...)`` selects USearch for large corpora
# and Flat for small corpora; they do NOT assert a specific
# threshold value.
AUTO_FLAT_CORPUS_THRESHOLD = 1000


class DenseIndexBackend:
    """Configuration-side constants; not an Enum so we can
    validate at runtime without importing the (potentially
    missing) optional USearch dependency."""

    AUTO = "auto"
    FLAT = "flat"
    USEARCH = "usearch"
    ALLOWED = (AUTO, FLAT, USEARCH)


class AutoCorpusSizeError(DenseIndexError):
    """Raised when ``backend="auto"`` is requested without
    ``corpus_size`` and a policy-driven default is not
    available."""


def select_dense_index(
    backend: str,
    *,
    embedding_profile_hash: str,
    corpus_size: Optional[int] = None,
    cache_root: Optional[str] = None,
    auto_flat_threshold: int = AUTO_FLAT_CORPUS_THRESHOLD,
    source_generation: str = "0",
) -> DenseIndexPort:
    """Select and construct a dense index adapter.

    Args:
        backend: one of ``"auto"``, ``"flat"``, ``"usearch"``.
        embedding_profile_hash: required for USearch (the index
            namespace key). For Flat, the hash is accepted but
            ignored.
        corpus_size: the number of vectors currently in the
            corpus. Required for ``backend="auto"`` so the
            data-driven decision can be made.
        cache_root: path to the disposable index directory. Only
            used by USearch.
        auto_flat_threshold: the corpus size at which ``auto``
            switches from Flat to USearch. Default is
            :data:`AUTO_FLAT_CORPUS_THRESHOLD`.
        source_generation: opaque generation token recorded in
            the index metadata for rebuild-on-mismatch detection.

    Returns:
        A :class:`DenseIndexPort` instance.

    Raises:
        DenseIndexError: for unknown ``backend`` values.
        AutoCorpusSizeError: for ``backend="auto"`` without
            ``corpus_size``.
    """
    if backend not in DenseIndexBackend.ALLOWED:
        raise DenseIndexError(
            f"unknown dense_index.backend: {backend!r}; allowed: "
            f"{DenseIndexBackend.ALLOWED}"
        )
    if backend == DenseIndexBackend.FLAT:
        return FlatDenseIndex()
    if backend == DenseIndexBackend.USEARCH:
        if not embedding_profile_hash:
            raise DenseIndexError(
                "embedding_profile_hash is required for usearch backend"
            )
        return USearchDenseIndex(
            embedding_profile_hash=embedding_profile_hash,
            cache_root=cache_root,
            source_generation=source_generation,
        )
    # backend == "auto"
    if corpus_size is None:
        raise AutoCorpusSizeError(
            "backend='auto' requires corpus_size to be provided"
        )
    if corpus_size <= auto_flat_threshold:
        return FlatDenseIndex()
    if not embedding_profile_hash:
        raise DenseIndexError(
            "embedding_profile_hash is required for usearch backend"
        )
    return USearchDenseIndex(
        embedding_profile_hash=embedding_profile_hash,
        cache_root=cache_root,
        source_generation=source_generation,
    )
