"""Metadata filter adapter.

Wraps :class:`pi_platform.core.retrieval.metadata_filter.MetadataFilterCore`
as a thin adapter so the registry / CLI can introspect the same
shape across the default and alternative filter projections.
"""

from __future__ import annotations

from pi_platform.core.retrieval.metadata_filter import MetadataFilterCore


__all__ = [
    "MetadataFilterAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "metadata-filter-default"


class MetadataFilterAdapter(MetadataFilterCore):
    """Default §24 / §56 metadata filter adapter."""

    def __init__(self) -> None:
        super().__init__()
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name