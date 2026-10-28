"""Composition of the dependency research service.

The production composition builds **one** service and injects it into
the MCP context and into the A2A adapter, so both protocols answer
from the same evidence.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Sequence

from pi_platform.core.research.policy import AcquisitionPolicy
from pi_platform.core.research.service import DependencyResearchService
from pi_platform.ports.research.ecosystem import EcosystemResearchPort

__all__ = [
    "build_dependency_research_service",
    "default_ecosystem_adapters",
    "approved_sources",
]


def default_ecosystem_adapters(*, installed_roots: Sequence[Path] = ()) -> tuple:
    """The ecosystem adapters of the production composition."""

    from pi_platform.adapters.research.java_ecosystem import JavaEcosystemAdapter
    from pi_platform.adapters.research.node_ecosystem import NodeEcosystemAdapter
    from pi_platform.adapters.research.python_ecosystem import PythonEcosystemAdapter

    return (
        PythonEcosystemAdapter(installed_roots=installed_roots),
        NodeEcosystemAdapter(),
        JavaEcosystemAdapter(installed_roots=installed_roots),
    )


def approved_sources(env: Optional[dict] = None) -> tuple[str, ...]:
    """The acquisition sources this deployment may use.

    Acquisition is off unless an operator names the approved sources.
    The default is therefore "no acquisition", not "acquire anything".
    """

    source = env if env is not None else os.environ
    raw = str(source.get("PI_RESEARCH_SOURCES", "") or "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def build_dependency_research_service(
    *,
    project_root: Path,
    cache_root: Optional[Path] = None,
    env: Optional[dict] = None,
    adapters: Optional[Sequence[EcosystemResearchPort]] = None,
    fetcher=None,
) -> DependencyResearchService:
    """Build the production dependency research service.

    The acquisition policy is derived from the operator's approved
    sources. Without an approved source the service still answers
    every offline question; it only refuses to download.
    """

    source = env if env is not None else os.environ
    policy = AcquisitionPolicy(
        allowed_sources=approved_sources(source),
        allowed_hosts=("files.pythonhosted.org", "pypi.org",
                       "registry.npmjs.org", "repo1.maven.org"),
    )
    acquirer = None
    reader = None
    if policy.allowed_sources:
        from pi_platform.adapters.research.acquisition import ArtifactAcquirer
        from pi_platform.adapters.research.sources import LibraryReader

        acquirer = ArtifactAcquirer(
            cache_root=Path(cache_root or project_root) / "research-artifacts",
            fetcher=fetcher,
            policy=policy,
        )
        reader = LibraryReader(policy=policy)
    return DependencyResearchService(
        project_root=Path(project_root),
        adapters=tuple(adapters) if adapters is not None
        else default_ecosystem_adapters(),
        acquisition_policy=policy,
        acquirer=acquirer,
        reader=reader,
    )
