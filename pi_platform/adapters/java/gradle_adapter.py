"""Stub for the Phase 2 Gradle build file SourceAdapter.

The real stdlib text implementation lands in the next step.
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


__all__ = ["GradleAdapter"]


class GradleAdapter(SourceAdapterPort):
    """Stub SourceAdapter for Gradle build files."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.GRADLE_BUILD

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        raise NotImplementedError(
            "stub: pi_platform.adapters.java.gradle_adapter"
        )
