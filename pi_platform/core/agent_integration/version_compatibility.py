"""Phase 6 §39 / §47 default version compatibility policy.

Deterministic, byte-stable verifier. Two consecutive
``serialise()`` calls produce the same JSON for an unchanged
deployment. ``verify(client)`` returns ``None`` on success and
raises :class:`VersionIncompatibleError` on the first failing
dimension. Unavailable dimensions on the client side are skipped,
never compared; unavailable server dimensions are reported
upfront so the client can fall back.

Design choices:

* Range comparisons use simple semver MAJOR.MINOR.PATCH tuples.
* OKF is an identifier set, not a semver range. ``okf_profile_set``
  is checked for membership of the client's single OKF version.
* The verifier is non-throwing on missing client values where
  the dimension is opt-in; required dimensions raise.
"""

from __future__ import annotations

import json
from typing import Optional

from ...ports.agent_integration import (
    ClientCapabilityReport,
    CompatibilityRange,
    VersionCompatibilityError,
    VersionCompatibilityPolicy,
    VersionIncompatibleError,
    VersionRange,
    _semver_range,
)


__all__ = ["DefaultVersionCompatibilityPolicy"]


class DefaultVersionCompatibilityPolicy(VersionCompatibilityPolicy):
    """Default §39 + §47 version compatibility policy."""

    def __init__(self, *, range_: CompatibilityRange,
                 adapter_name: Optional[str] = None):
        self._range = range_
        self._adapter_name = adapter_name

    def compatibility_range(self) -> CompatibilityRange:
        return self._range

    def verify(self, client: ClientCapabilityReport) -> None:
        # 1. mcpApiVersion — required.
        if client.mcp_api_version is None:
            self._raise(
                "mcpApiVersion", offered=self._range.mcp_api_version.minimum,
                constraint=f">={self._range.mcp_api_version.minimum} "
                           f"<{self._range.mcp_api_version.maximum_exclusive}",
            )
        if not self._range.mcp_api_version.contains(client.mcp_api_version):
            self._raise(
                "mcpApiVersion",
                offered=client.mcp_api_version,
                constraint=f">={self._range.mcp_api_version.minimum} "
                           f"<{self._range.mcp_api_version.maximum_exclusive}",
            )

        # 2. platformVersion — required.
        if client.platform_version is None:
            self._raise(
                "platformVersion", offered=self._range.platform_version.minimum,
                constraint=f">={self._range.platform_version.minimum} "
                           f"<{self._range.platform_version.maximum_exclusive}",
            )
        if not self._range.platform_version.contains(client.platform_version):
            self._raise(
                "platformVersion",
                offered=client.platform_version,
                constraint=f">={self._range.platform_version.minimum} "
                           f"<{self._range.platform_version.maximum_exclusive}",
            )

        # 3. mcpSdkVersion — optional; skip if absent.
        if (client.mcp_sdk_version is not None
                and not self._range.mcp_sdk_version.contains(
                    client.mcp_sdk_version)):
            self._raise(
                "mcpSdkVersion",
                offered=client.mcp_sdk_version,
                constraint=f">={self._range.mcp_sdk_version.minimum} "
                           f"<{self._range.mcp_sdk_version.maximum_exclusive}",
            )

        # 4. knowledgeSchemaVersion — optional; skip if absent.
        if (client.knowledge_schema_version is not None
                and not self._range.knowledge_schema_version.contains(
                    client.knowledge_schema_version)):
            self._raise(
                "knowledgeSchemaVersion",
                offered=client.knowledge_schema_version,
                constraint=f">={self._range.knowledge_schema_version.minimum} "
                           f"<{self._range.knowledge_schema_version.maximum_exclusive}",
            )

        # 5. skillVersion — optional; skip if absent.
        if (client.skill_version is not None
                and not self._range.skill_version.contains(
                    client.skill_version)):
            self._raise(
                "skillVersion",
                offered=client.skill_version,
                constraint=f">={self._range.skill_version.minimum} "
                           f"<{self._range.skill_version.maximum_exclusive}",
            )

        # 6. okfProfileVersion — required to be in the set.
        if client.okf_profile_version is None:
            self._raise(
                "okfProfileVersion", offered=None,
                constraint=f"one of {{{','.join(self._range.okf_profile_set)}}}",
            )
        if client.okf_profile_version not in self._range.okf_profile_set:
            self._raise(
                "okfProfileVersion",
                offered=client.okf_profile_version,
                constraint=f"one of {{{','.join(self._range.okf_profile_set)}}}",
            )

        # 7. Unavailable server-side dimensions: report upfront so
        # the client can fall back; do not compare against invented
        # values.
        for attr_name, dim_name, server_range in (
                ("a2a_adapter_version", "a2aAdapterVersion",
                 self._range.a2a_adapter_version),
                ("agent_adapter_version", "agentAdapterVersion",
                 self._range.agent_adapter_version),
        ):
            if server_range is None:
                client_value = getattr(client, attr_name)
                if client_value is not None:
                    self._raise(
                        dim_name,
                        offered=client_value,
                        constraint="server: unavailable",
                    )

    def upgrade_hint(self, dimension: str) -> str:
        adapter_hint = (
            f" consult adapter {self._adapter_name!r}"
            if self._adapter_name else ""
        )
        hints = {
            "platformVersion":
                "upgrade the platform package to a compatible release"
                f"{adapter_hint}; see distribution manifest",
            "mcpApiVersion":
                "the client advertises an unsupported product "
                "tool-schema API; upgrade the client or server to a "
                "compatible MCP API release",
            "mcpSdkVersion":
                "upgrade the MCP Python SDK to the range declared by the "
                "distribution manifest",
            "knowledgeSchemaVersion":
                "upgrade or downgrade the canonical knowledge schema "
                "to the range declared by the distribution manifest",
            "skillVersion":
                "upgrade the canonical Agent Skill; rerun "
                "`python -m pi_platform.cli skill-distribute`",
            "okfProfileVersion":
                "switch to an OKF profile in the supported set "
                "(see distribution manifest)",
            "a2aAdapterVersion":
                "A2A integration is not implemented until Phase 10; "
                "disable A2A on the client side until then",
            "agentAdapterVersion":
                "agent adapter contract is not implemented until "
                "Phase 7+; install a compatible adapter",
        }
        return hints.get(dimension, "consult the distribution manifest")

    def _raise(self, dimension: str, *,
               offered: Optional[str],
               constraint: str) -> None:
        raise VersionIncompatibleError(
            dimension=dimension,
            offered_value=offered,
            client_constraint=constraint,
            applicable_adapter=self._adapter_name,
            upgrade_instructions=self.upgrade_hint(dimension),
        )

    def serialise(self) -> str:
        payload = {
            "platformVersion": self._range.platform_version.as_dict(),
            "mcpApiVersion": self._range.mcp_api_version.as_dict(),
            "mcpSdkVersion": self._range.mcp_sdk_version.as_dict(),
            "knowledgeSchemaVersion":
                self._range.knowledge_schema_version.as_dict(),
            "skillVersion": self._range.skill_version.as_dict(),
            "okfProfileVersion": list(self._range.okf_profile_set),
            "a2aAdapterVersion": (
                self._range.a2a_adapter_version.as_dict()
                if self._range.a2a_adapter_version is not None else None
            ),
            "agentAdapterVersion": (
                self._range.agent_adapter_version.as_dict()
                if self._range.agent_adapter_version is not None else None
            ),
        }
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def policy_from_distribution_manifest(
        manifest: Mapping[str, object],
        *,
         adapter_name: Optional[str] = None,
) -> DefaultVersionCompatibilityPolicy:
    """Build a policy from a parsed distribution-manifest mapping.

    Raises :class:`VersionCompatibilityError` if any required range
    is missing or malformed.
    """
    try:
        return DefaultVersionCompatibilityPolicy(
            range_=CompatibilityRange(
                platform_version=_semver_range(
                    str(manifest["platformVersionRange"])
                ),
                mcp_api_version=_semver_range(
                    str(manifest["mcpApiRange"])
                ),
                mcp_sdk_version=_semver_range(
                    str(manifest["mcpSdkRange"])
                ),
                knowledge_schema_version=_semver_range(
                    str(manifest["knowledgeSchemaRange"])
                ),
                skill_version=_semver_range(
                    str(manifest["skillVersionRange"])
                ),
                okf_profile_set=tuple(manifest["okfProfileSet"]),
                a2a_adapter_version=(
                    _semver_range(str(manifest["a2aAdapterRange"]))
                    if manifest.get("a2aAdapterRange") else None
                ),
                agent_adapter_version=(
                    _semver_range(str(manifest["agentAdapterRange"]))
                    if manifest.get("agentAdapterRange") else None
                ),
            ),
            adapter_name=adapter_name,
        )
    except (KeyError, TypeError) as exc:
        raise VersionCompatibilityError(
            f"distribution manifest missing required range: {exc}"
        ) from exc