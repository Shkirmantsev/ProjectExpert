"""Phase 6 version-compatibility port (§39 + §47).

The platform tracks nine independently evolving version
dimensions and exposes a single typed compatibility handshake
that skills, adapters and plugins call at startup.

Dimensions (the 9 §39 dimensions the platform tracks):

* ``platformVersion`` — package release.
* ``mcpApiVersion`` — product tool-schema API; independent of
  the MCP SDK package and the MCP wire protocol.
* ``mcpSdkVersion`` — installed MCP SDK.
* ``mcpWireProtocolVersion`` — negotiated wire protocol.
* ``knowledgeSchemaVersion`` — canonical knowledge schema.
* ``okfProfileVersion`` — supported OKF profile versions.
* ``skillVersion`` — canonical Agent Skill version.
* ``a2aAdapterVersion`` — UNIMPLEMENTED until Phase 10.
* ``agentAdapterVersion`` — UNIMPLEMENTED until Phase 7+.

Semver-style ranges apply to ``platformVersion``,
``mcpApiVersion``, ``mcpSdkVersion``, ``knowledgeSchemaVersion``
and ``skillVersion``. The OKF profile is an identifier set
(``{"0.2"}``); the remaining dimensions report availability and
must not be compared with invented values.

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
    "mcpSdkVersion",
    "mcpWireProtocolVersion",
    "knowledgeSchemaVersion",
    "okfProfileVersion",
    "skillVersion",
    "a2aAdapterVersion",
    "agentAdapterVersion",
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
    accepts (e.g. ``>=1.3.0 <2.0.0``). ``okf_profile_set`` is an
    identifier set. ``unavailable`` dimensions are reported
    explicitly with ``available=False``; the verifier does not
    compare unavailable dimensions.
    """

    platform_version: VersionRange
    mcp_api_version: VersionRange
    mcp_sdk_version: VersionRange
    knowledge_schema_version: VersionRange
    skill_version: VersionRange
    okf_profile_set: tuple[str, ...]
    mcp_wire_protocol_version: Optional[str] = None
    a2a_adapter_version: Optional[VersionRange] = None
    agent_adapter_version: Optional[VersionRange] = None

    def __post_init__(self) -> None:
        if not self.okf_profile_set:
            raise ValueError(
                "okf_profile_set must list at least one supported OKF version"
            )

    def dimension_ranges(self) -> Mapping[str, object]:
        return {
            "platformVersion": self.platform_version,
            "mcpApiVersion": self.mcp_api_version,
            "mcpSdkVersion": self.mcp_sdk_version,
            "knowledgeSchemaVersion": self.knowledge_schema_version,
            "skillVersion": self.skill_version,
            "okfProfileVersion": self.okf_profile_set,
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
    mcp_sdk_version: Optional[str] = None
    mcp_wire_protocol_version: Optional[str] = None
    knowledge_schema_version: Optional[str] = None
    okf_profile_version: Optional[str] = None
    skill_version: Optional[str] = None
    a2a_adapter_version: Optional[str] = None
    agent_adapter_version: Optional[str] = None


class VersionCompatibilityError(RuntimeError):
    """Raised when the policy cannot parse its inputs."""


class VersionIncompatibleError(RuntimeError):
    """Typed error returned to clients when a dimension fails.

    The error carries the failed ``dimension`` name, the
    ``offered_value`` the server advertised, the
    ``client_constraint`` the client advertised (a semver range or
    an OKF identifier set), the applicable ``adapter`` family (if
    any), and ``upgrade_instructions`` the client can follow.
    """

    def __init__(self, *,
                 dimension: str,
                 offered_value: Optional[str],
                 client_constraint: str,
                 applicable_adapter: Optional[str],
                 upgrade_instructions: str):
        self.dimension = dimension
        self.offered_value = offered_value
        self.client_constraint = client_constraint
        self.applicable_adapter = applicable_adapter
        self.upgrade_instructions = upgrade_instructions
        super().__init__(
            f"version-incompatible: dimension={dimension} "
            f"offered={offered_value!r} "
            f"client_constraint={client_constraint!r} "
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