"""Capability discovery port for the v0.8 Phase 5 orchestration
layer.

Covers architecture section §47 (Capability Discovery). The
:class:`CapabilityDiscoveryPort` returns the deterministic
:class:`CapabilityDescriptor` JSON that the Phase 6 MCP server
exposes via `describe_capabilities` and that skills / plugins
consume to adapt to the actual deployment.

Phase 6 prerequisite 5: the descriptor's version fields are the
**actual offered metadata**, not architecture example numbers.
Unavailable dimensions (e.g. ``a2aAdapterVersion`` until Phase
10) are reported with ``available=False`` rather than fabricated
with example values. Each dimension carries its own (value,
available) pair.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence


__all__ = [
    "CapabilityFeatures",
    "CapabilityDescriptor",
    "CapabilityDiscoveryError",
    "CapabilityDiscoveryPort",
    "DimensionValue",
    "VersionDimensions",
]


class CapabilityDiscoveryError(RuntimeError):
    """Raised when the capability descriptor cannot be built."""


@dataclass(frozen=True)
class DimensionValue:
    """One version dimension's actual offered value.

    ``value`` is the literal metadata the deployment advertises
    (or ``None`` when the dimension is intentionally absent).
    ``available`` is False when the dimension is not yet
    implemented; the descriptor reports it as unavailable rather
    than inventing a placeholder.
    """

    name: str
    value: Optional[str]
    available: bool

    def as_dict(self) -> dict:
        out: dict = {
            "name": self.name,
            "available": self.available,
        }
        out["value"] = self.value
        return out


@dataclass(frozen=True)
class VersionDimensions:
    """Phase 6 prerequisite 5 — honest 9-dimension version block.

    The 9 dimensions mirror the §39 architecture list. Each
    carries ``value`` (the actual advertised metadata) and
    ``available`` (False when the dimension is not yet
    implemented). Unavailable dimensions are reported with
    ``value=None`` rather than fabricated.
    """

    platformVersion: DimensionValue
    mcpApiVersion: DimensionValue
    a2aAdapterVersion: DimensionValue
    knowledgeSchemaVersion: DimensionValue
    okfProfileVersion: DimensionValue
    skillVersion: DimensionValue
    pluginDistributionSchemaVersion: DimensionValue
    agentAdapterVersion: DimensionValue
    runtimeIndexSchemaVersion: DimensionValue

    def as_dict(self) -> dict:
        return {
            "platformVersion": self.platformVersion.as_dict(),
            "mcpApiVersion": self.mcpApiVersion.as_dict(),
            "a2aAdapterVersion": self.a2aAdapterVersion.as_dict(),
            "knowledgeSchemaVersion":
                self.knowledgeSchemaVersion.as_dict(),
            "okfProfileVersion": self.okfProfileVersion.as_dict(),
            "skillVersion": self.skillVersion.as_dict(),
            "pluginDistributionSchemaVersion":
                self.pluginDistributionSchemaVersion.as_dict(),
            "agentAdapterVersion": self.agentAdapterVersion.as_dict(),
            "runtimeIndexSchemaVersion":
                self.runtimeIndexSchemaVersion.as_dict(),
        }

    @property
    def unavailable_names(self) -> tuple[str, ...]:
        return tuple(
            d.name for d in (
                self.platformVersion, self.mcpApiVersion,
                self.a2aAdapterVersion,
                self.knowledgeSchemaVersion, self.okfProfileVersion,
                self.skillVersion,
                self.pluginDistributionSchemaVersion,
                self.agentAdapterVersion, self.runtimeIndexSchemaVersion,
            ) if not d.available
        )


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
    """§47 deterministic capability descriptor.

    The descriptor carries the legacy short-form fields for
    backward compatibility AND the new :class:`VersionDimensions`
    block so the MCP server can answer either shape.
    """

    serverVersion: str
    mcpApiVersion: str
    knowledgeSchemaVersion: str
    okfVersions: Sequence[str] = field(default_factory=tuple)
    features: CapabilityFeatures = field(default_factory=CapabilityFeatures)
    dimensions: VersionDimensions | None = None

    def as_dict(self) -> dict:
        out = {
            "serverVersion": self.serverVersion,
            "mcpApiVersion": self.mcpApiVersion,
            "knowledgeSchemaVersion": self.knowledgeSchemaVersion,
            "okfVersions": list(self.okfVersions),
            "features": self.features.as_dict(),
        }
        if self.dimensions is not None:
            out["dimensions"] = self.dimensions.as_dict()
        return out


class CapabilityDiscoveryPort(abc.ABC):
    """Abstract capability discovery port."""

    @abc.abstractmethod
    def describe(self) -> CapabilityDescriptor: ...

    @abc.abstractmethod
    def refresh(self) -> CapabilityDescriptor: ...

    @abc.abstractmethod
    def stats(self) -> Mapping[str, int]: ...