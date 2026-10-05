"""Capability discovery port for the v0.8 Phase 5 orchestration
layer.

Covers architecture section §47 (Capability Discovery). The
:class:`CapabilityDiscoveryPort` returns the deterministic
:class:`CapabilityDescriptor` JSON that the Phase 6 MCP server
exposes via `describe_capabilities` and that skills / plugins
consume to adapt to the actual deployment.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Sequence


__all__ = [
    "CapabilityFeatures",
    "CapabilityDescriptor",
    "CapabilityDiscoveryError",
    "CapabilityDiscoveryPort",
]


class CapabilityDiscoveryError(RuntimeError):
    """Raised when the capability descriptor cannot be built."""


@dataclass(frozen=True)
class CapabilityFeatures:
    """§47 capability map."""

    hybridRetrieval: bool = False
    graphExpansion: bool = False
    okf: Sequence[str] = field(default_factory=tuple)
    materialization: bool = False
    a2a: bool = False
    localLlm: bool = False

    def as_dict(self) -> dict:
        return {
            "hybridRetrieval": self.hybridRetrieval,
            "graphExpansion": self.graphExpansion,
            "okf": list(self.okf),
            "materialization": self.materialization,
            "a2a": self.a2a,
            "localLlm": self.localLlm,
        }


@dataclass(frozen=True)
class CapabilityDescriptor:
    """§47 deterministic capability descriptor."""

    serverVersion: str
    mcpApiVersion: str
    knowledgeSchemaVersion: str
    okfVersions: Sequence[str] = field(default_factory=tuple)
    features: CapabilityFeatures = field(default_factory=CapabilityFeatures)

    def as_dict(self) -> dict:
        return {
            "serverVersion": self.serverVersion,
            "mcpApiVersion": self.mcpApiVersion,
            "knowledgeSchemaVersion": self.knowledgeSchemaVersion,
            "okfVersions": list(self.okfVersions),
            "features": self.features.as_dict(),
        }


class CapabilityDiscoveryPort(abc.ABC):
    """Abstract capability discovery port."""

    @abc.abstractmethod
    def describe(self) -> CapabilityDescriptor: ...

    @abc.abstractmethod
    def refresh(self) -> CapabilityDescriptor: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...