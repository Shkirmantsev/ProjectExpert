"""Stub for the Phase 2 JAR SourceAdapter.

The real zipfile-based implementation lands in the next step.
Construction succeeds so the default ``LocalPipelineDriver``
registry can be built; ``parse`` raises ``NotImplementedError``
until the real implementation replaces this module at the
documented import path.
"""

from __future__ import annotations

from typing import Optional

from pi_platform.core.canonical.value_types import Source

from pi_platform.ports.ingest.source_adapter import (
    SourceAdapterContext,
    SourceAdapterPort,
    SourceContentFamily,
    SourceParseResult,
)


__all__ = ["JarAdapter"]


class JarAdapter(SourceAdapterPort):
    """Stub SourceAdapter for JAR archives."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.JAR

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        raise NotImplementedError(
            "stub: pi_platform.adapters.java.jar_adapter"
        )
