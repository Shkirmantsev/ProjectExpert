"""Phase 6 §39 / §47 version compatibility port.

The platform tracks nine independently evolving version
dimensions and exposes a single typed compatibility handshake
that skills, adapters and plugins call at startup.

Dimensions (the 9 §39 dimensions the platform tracks, per the
v0.8 architecture baseline):

* ``platformVersion`` — package release.
* ``mcpApiVersion`` — product tool-schema API; independent of
  the MCP SDK package and the MCP wire protocol.
* ``a2aAdapterVersion`` — UNIMPLEMENTED until Phase 10.
* ``knowledgeSchemaVersion`` — canonical knowledge schema.
* ``okfProfileVersion`` — supported OKF profile versions.
* ``skillVersion`` — canonical Agent Skill version.
* ``pluginDistributionSchemaVersion`` — release manifest
  schema identifier (not semver).
* ``agentAdapterVersion`` — UNIMPLEMENTED until Phase 7+.
* ``runtimeIndexSchemaVersion`` — runtime index schema
  version (UNIMPLEMENTED until Phase 7+).

Semver-style ranges apply to ``platformVersion``,
``mcpApiVersion``, ``knowledgeSchemaVersion`` and
``skillVersion``. The OKF profile and the plugin distribution
schema are identifier sets / opaque identifiers; the remaining
dimensions report availability and must not be compared with
invented values.

This module is intentionally small: policy + verifier + error.
Adapters and MCP clients reuse it; packagers include it in the
deterministic release identity they all share.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence


__all__ = [
    "ALL_DIMENSIONS",
    "ClientCapabilityReport",
    "CompatibilityRange",
    "VersionCompatibilityPolicy",
    "VersionCompatibilityError",
    "VersionIncompatibleError",
    "VersionRange",
]


ALL_DIMENSIONS: tuple[str, ...] = (
    "platformVersion",
    "mcpApiVersion",
    "a2aAdapterVersion",
    "knowledgeSchemaVersion",
    "okfProfileVersion",
    "skillVersion",
    "pluginDistributionSchemaVersion",
    "agentAdapterVersion",
    "runtimeIndexSchemaVersion",
)


@dataclass(frozen=True)
class VersionRange:
    """Inclusive semver-style range ``>=a <b`` parsed at construction."""

    minimum: str
    maximum_exclusive: str

    def __post_init__(self) -> None:
        for label, value in (("minimum", self.minimum),
                             ("maximum_exclusive", self.maximum_exclusive)):
            if not _SEMVER_OK.match(value):
                raise ValueError(
                    f"VersionRange.{label} must be a semver MAJOR.MINOR.PATCH "
                    f"string, got {value!r}"
                )
        if _semver_tuple(self.minimum) >= _semver_tuple(
                self.maximum_exclusive):
            raise ValueError(
                f"VersionRange minimum {self.minimum!r} must be strictly less "
                f"than maximum_exclusive {self.maximum_exclusive!r}"
            )

    def contains(self, version: str) -> bool:
        return (
            _semver_tuple(self.minimum) <= _semver_tuple(version)
            < _semver_tuple(self.maximum_exclusive)
        )

    def as_dict(self) -> dict:
        return {"min": self.minimum, "maxExclusive": self.maximum_exclusive}


@dataclass(frozen=True)
class CompatibilityRange:
    """Per-dimension compatibility ranges advertised by the server.

    Each ``semver_range`` is the inclusive range the server
    accepts (e.g. ``>=1.3.0 <2.0.0``). ``okf_profile_set`` and
    ``plugin_distribution_schema`` are identifier sets / opaque
    identifiers. ``unavailable`` dimensions are reported
    explicitly with ``available=False``; the verifier does not
    compare unavailable dimensions.
    """

    platform_version: VersionRange
    mcp_api_version: VersionRange
    knowledge_schema_version: VersionRange
    skill_version: VersionRange
    okf_profile_set: tuple[str, ...]
    plugin_distribution_schema: tuple[str, ...]
    a2a_adapter_version: Optional[VersionRange] = None
    agent_adapter_version: Optional[VersionRange] = None
    runtime_index_schema_version: Optional[VersionRange] = None

    def __post_init__(self) -> None:
        if not self.okf_profile_set:
            raise ValueError(
                "okf_profile_set must list at least one supported OKF version"
            )
        if not self.plugin_distribution_schema:
            raise ValueError(
                "plugin_distribution_schema must list at least one "
                "supported schema identifier"
            )

    def dimension_ranges(self) -> Mapping[str, object]:
        return {
            "platformVersion": self.platform_version,
            "mcpApiVersion": self.mcp_api_version,
            "knowledgeSchemaVersion": self.knowledge_schema_version,
            "skillVersion": self.skill_version,
            "okfProfileVersion": self.okf_profile_set,
            "pluginDistributionSchemaVersion":
                self.plugin_distribution_schema,
        }


@dataclass(frozen=True)
class ClientCapabilityReport:
    """The version block the client / adapter / plugin advertises.

    Dimensions reported with ``available=False`` are skipped by
    the verifier. Invented dimensions raise
    :class:`VersionCompatibilityError`.
    """

    platform_version: Optional[str] = None
    mcp_api_version: Optional[str] = None
    a2a_adapter_version: Optional[str] = None
    knowledge_schema_version: Optional[str] = None
    okf_profile_version: Optional[str] = None
    skill_version: Optional[str] = None
    plugin_distribution_schema_version: Optional[str] = None
    agent_adapter_version: Optional[str] = None
    runtime_index_schema_version: Optional[str] = None


class VersionCompatibilityError(RuntimeError):
    """Raised when the policy cannot parse its inputs."""


class VersionIncompatibleError(RuntimeError):
    """Typed error returned to clients when a dimension fails.

    Field semantics (mirroring the architecture §39 payload):
    * ``dimension`` — the failing dimension name.
    * ``server_offered_range`` — the range the SERVER advertised
      for that dimension (e.g. ``">=1.3.0 <2.0.0"``); the empty
      string when the server does not yet expose the dimension.
    * ``client_offered_value`` — the value the CLIENT advertised
      for that dimension (single semver / identifier); the empty
      string when the client omitted it.
    * ``applicable_adapter`` — the adapter the client is
      configured with, or ``None``.
    * ``upgrade_instructions`` — typed upgrade messaging.
    """

    def __init__(self, *,
                 dimension: str,
                 server_offered_range: str,
                 client_offered_value: str,
                 applicable_adapter: Optional[str],
                 upgrade_instructions: str):
        self.dimension = dimension
        self.server_offered_range = server_offered_range
        self.client_offered_value = client_offered_value
        self.applicable_adapter = applicable_adapter
        self.upgrade_instructions = upgrade_instructions
        super().__init__(
            f"version-incompatible: dimension={dimension} "
            f"server_offered_range={server_offered_range!r} "
            f"client_offered_value={client_offered_value!r} "
            f"applicable_adapter={applicable_adapter!r}; "
            f"{upgrade_instructions}"
        )


class VersionCompatibilityPolicy(abc.ABC):
    """§39 + §47 compatibility policy.

    The verifier checks every advertised dimension against the
    policy. A failure on any dimension raises a typed
    :class:`VersionIncompatibleError` so the client can act on
    the specific mismatch without parsing prose. Unavailable
    dimensions are skipped, never compared.
    """

    @abc.abstractmethod
    def compatibility_range(self) -> CompatibilityRange: ...

    @abc.abstractmethod
    def verify(self, client: ClientCapabilityReport
               ) -> None: ...

    @abc.abstractmethod
    def upgrade_hint(self, dimension: str) -> str: ...

    @abc.abstractmethod
    def serialise(self) -> str:
        """Byte-stable JSON serialisation for two consecutive reads."""


_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"
_SEMVER_OK = re.compile(_SEMVER_PATTERN)


def _semver_tuple(value: str) -> tuple[int, int, int]:
    parts = value.split(".")
    return int(parts[0]), int(parts[1]), int(parts[2])


def _semver_range(value: str) -> VersionRange:
    """Parse ``>=1.3.0 <2.0.0`` into a :class:`VersionRange`.

    Raises :class:`VersionCompatibilityError` for malformed input.
    """
    parts = value.split()
    if len(parts) != 2:
        raise VersionCompatibilityError(
            f"semver range must be '>=a.b.c <d.e.f', got {value!r}"
        )
    min_text, max_text = parts
    if not min_text.startswith(">="):
        raise VersionCompatibilityError(
            f"semver range minimum must start with '>=', got {min_text!r}"
        )
    if not max_text.startswith("<"):
        raise VersionCompatibilityError(
            f"semver range maximum must start with '<', got {max_text!r}"
        )
    try:
        return VersionRange(
            minimum=min_text[2:],
            maximum_exclusive=max_text[1:],
        )
    except ValueError as exc:
        raise VersionCompatibilityError(str(exc)) from exc