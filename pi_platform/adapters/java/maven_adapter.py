"""Stub for the Phase 2 Maven ``pom.xml`` SourceAdapter.

The real stdlib XML implementation lands in the next step.
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


__all__ = ["MavenAdapter"]


class MavenAdapter(SourceAdapterPort):
    """Stub SourceAdapter for Maven ``pom.xml`` files."""

    @property
    def family(self) -> SourceContentFamily:
        return SourceContentFamily.MAVEN_POM

    def parse(self, source: Source,
              context: Optional[SourceAdapterContext] = None) -> SourceParseResult:
        raise NotImplementedError(
            "stub: pi_platform.adapters.java.maven_adapter"
        )
