"""Context assembler adapter.

Wraps :class:`pi_platform.core.retrieval.context_assembler.ContextAssemblerCore`
as a thin adapter so the registry / CLI can introspect the same
shape across the default and alternative assembler implementations.
"""

from __future__ import annotations

from pi_platform.core.retrieval.context_assembler import ContextAssemblerCore


__all__ = [
    "ContextAssemblerAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "context-assembler-default"


class ContextAssemblerAdapter(ContextAssemblerCore):
    """Default §32 context assembler adapter."""

    def __init__(self) -> None:
        super().__init__()
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name