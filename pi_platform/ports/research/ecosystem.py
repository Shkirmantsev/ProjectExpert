"""The ecosystem adapter port.

An ecosystem adapter reads the manifests, locks and local artifacts of
one ecosystem and reports what it could observe *offline*. It never
downloads anything and never executes dependency code.
"""

from __future__ import annotations

import abc
from pathlib import Path
from typing import Optional, Sequence

from pi_platform.core.research.records import EcosystemSnapshot

__all__ = ["EcosystemResearchPort"]


class EcosystemResearchPort(abc.ABC):
    """Offline evidence for one ecosystem."""

    #: Stable ecosystem key, e.g. ``python``, ``java``, ``node``.
    ecosystem: str = ""

    @abc.abstractmethod
    def detect(self, project_root: Path) -> bool:
        """Report whether this ecosystem is present in the project."""

    @abc.abstractmethod
    def collect(self, project_root: Path, *, environment: str = "default",
                scopes: Sequence[str] = ()) -> EcosystemSnapshot:
        """Read the offline evidence of this ecosystem."""

    def capabilities(self) -> dict:
        """Describe the formats and tools this adapter supports."""

        return {"ecosystem": self.ecosystem}
