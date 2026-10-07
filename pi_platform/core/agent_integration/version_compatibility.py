"""Phase 6 §39 / §47 default version compatibility policy.

Deterministic, byte-stable verifier. Two consecutive
``serialise()`` calls produce the same JSON for an unchanged
deployment. ``verify(client)`` returns ``None`` on success and
raises :class:`VersionIncompatibleError` on the first failing
dimension. Unavailable dimensions on the client side are skipped,
never compared; unavailable server dimensions are reported
upfront so the client can fall back.

The verifier populates the typed error with both sides of the
handshake — the server-offered range and the client-offered
value — so the failing payload is unambiguous without parsing
prose.

Design choices:

* Range comparisons use simple semver MAJOR.MINOR.PATCH tuples.
* OKF and plugin-distribution-schema are identifier sets; the
  client's single identifier is checked for membership.
* The verifier is non-throwing on missing client values where
  the dimension is opt-in; required dimensions raise.
"""

from __future__ import annotations

import json
from typing import Mapping, Optional

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
            self._raise_semver(
                "mcpApiVersion", client_value="",
                server_range=self._range.mcp_api_version,
            )
        if not self._range.mcp_api_version.contains(client.mcp_api_version):
            self._raise_semver(
                "mcpApiVersion",
                client_value=client.mcp_api_version,
                server_range=self._range.mcp_api_version,
            )

        # 2. platformVersion — required.
        if client.platform_version is None:
            self._raise_semver(
                "platformVersion", client_value="",
                server_range=self._range.platform_version,
            )
        if not self._range.platform_version.contains(client.platform_version):
            self._raise_semver(
                "platformVersion",
                client_value=client.platform_version,
                server_range=self._range.platform_version,
            )

        # 3. knowledgeSchemaVersion — optional; skip if absent.
        if (client.knowledge_schema_version is not None
                and not self._range.knowledge_schema_version.contains(
                    client.knowledge_schema_version)):
            self._raise_semver(
                "knowledgeSchemaVersion",
                client_value=client.knowledge_schema_version,
                server_range=self._range.knowledge_schema_version,
            )

        # 4. skillVersion — optional; skip if absent.
        if (client.skill_version is not None
                and not self._range.skill_version.contains(
                    client.skill_version)):
            self._raise_semver(
                "skillVersion",
                client_value=client.skill_version,
                server_range=self._range.skill_version,
            )

        # 5. okfProfileVersion — required to be in the set.
        if client.okf_profile_version is None:
            self._raise_set(
                "okfProfileVersion", client_value="",
                server_set=self._range.okf_profile_set,
            )
        if client.okf_profile_version not in self._range.okf_profile_set:
            self._raise_set(
                "okfProfileVersion",
                client_value=client.okf_profile_version,
                server_set=self._range.okf_profile_set,
            )

        # 6. pluginDistributionSchemaVersion — required to be in the set.
        if client.plugin_distribution_schema_version is None:
            self._raise_set(
                "pluginDistributionSchemaVersion", client_value="",
                server_set=self._range.plugin_distribution_schema,
            )
        if (client.plugin_distribution_schema_version
                not in self._range.plugin_distribution_schema):
            self._raise_set(
                "pluginDistributionSchemaVersion",
                client_value=client.plugin_distribution_schema_version,
                server_set=self._range.plugin_distribution_schema,
            )

        # 7. Unavailable server-side dimensions: report upfront so
        # the client can fall back; do not compare against invented
        # values.
        for attr_name, dim_name, server_range in (
                ("a2a_adapter_version", "a2aAdapterVersion",
                 self._range.a2a_adapter_version),
                ("agent_adapter_version", "agentAdapterVersion",
                 self._range.agent_adapter_version),
                ("runtime_index_schema_version",
                 "runtimeIndexSchemaVersion",
                 self._range.runtime_index_schema_version),
        ):
            if server_range is None:
                client_value = getattr(client, attr_name)
                if client_value is not None:
                    raise VersionIncompatibleError(
                        dimension=dim_name,
                        server_offered_range="(unavailable)",
                        client_offered_value=client_value,
                        applicable_adapter=self._adapter_name,
                        upgrade_instructions=self.upgrade_hint(dim_name),
                    )

    def upgrade_hint(self, dimension: str) -> str:
        adapter_hint = (
            f" consult adapter {self._adapter_name!r}"
            if self._adapter_name else "")
        hints = {
            "platformVersion":
                "upgrade the platform package to a compatible release"
                f"{adapter_hint}; see distribution manifest",
            "mcpApiVersion":
                "the client advertises an unsupported product "
                "tool-schema API; upgrade the client or server to a "
                "compatible MCP API release",
            "a2aAdapterVersion":
                "A2A integration is not implemented until Phase 10; "
                "disable A2A on the client side until then",
            "knowledgeSchemaVersion":
                "upgrade or downgrade the canonical knowledge schema "
                "to the range declared by the distribution manifest",
            "skillVersion":
                "upgrade the canonical Agent Skill; rerun "
                "`python -m pi_platform.cli skill-distribute`",
            "okfProfileVersion":
                "switch to an OKF profile in the supported set "
                "(see distribution manifest)",
            "pluginDistributionSchemaVersion":
                "switch to a plugin distribution schema in the "
                "supported set (see distribution manifest)",
            "agentAdapterVersion":
                "agent adapter contract is not implemented until "
                "Phase 7+; install a compatible adapter",
            "runtimeIndexSchemaVersion":
                "the runtime index schema is not yet implemented; "
                "disable the runtime index on the client side "
                "until Phase 7+",
        }
        return hints.get(dimension, "consult the distribution manifest")

    def _raise_semver(self, dimension: str, *,
                      client_value: str,
                      server_range: VersionRange) -> None:
        server_offered_range = (
            f">={server_range.minimum} <{server_range.maximum_exclusive}"
        )
        raise VersionIncompatibleError(
            dimension=dimension,
            server_offered_range=server_offered_range,
            client_offered_value=client_value,
            applicable_adapter=self._adapter_name,
            upgrade_instructions=self.upgrade_hint(dimension),
        )

    def _raise_set(self, dimension: str, *,
                   client_value: str,
                   server_set: tuple[str, ...]) -> None:
        server_offered_range = (
            f"one of {{{','.join(server_set)}}}"
        )
        raise VersionIncompatibleError(
            dimension=dimension,
            server_offered_range=server_offered_range,
            client_offered_value=client_value,
            applicable_adapter=self._adapter_name,
            upgrade_instructions=self.upgrade_hint(dimension),
        )

    def serialise(self) -> str:
        payload = {
            "platformVersion": self._range.platform_version.as_dict(),
            "mcpApiVersion": self._range.mcp_api_version.as_dict(),
            "knowledgeSchemaVersion":
                self._range.knowledge_schema_version.as_dict(),
            "skillVersion": self._range.skill_version.as_dict(),
            "okfProfileVersion": list(self._range.okf_profile_set),
            "pluginDistributionSchemaVersion":
                list(self._range.plugin_distribution_schema),
            "a2aAdapterVersion": (
                self._range.a2a_adapter_version.as_dict()
                if self._range.a2a_adapter_version is not None else None
            ),
            "agentAdapterVersion": (
                self._range.agent_adapter_version.as_dict()
                if self._range.agent_adapter_version is not None else None
            ),
            "runtimeIndexSchemaVersion": (
                self._range.runtime_index_schema_version.as_dict()
                if self._range.runtime_index_schema_version is not None
                else None
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
                knowledge_schema_version=_semver_range(
                    str(manifest["knowledgeSchemaRange"])
                ),
                skill_version=_semver_range(
                    str(manifest["skillVersionRange"])
                ),
                okf_profile_set=tuple(manifest["okfProfileSet"]),
                plugin_distribution_schema=tuple(
                    manifest["pluginDistributionSchemaSet"]
                ),
                a2a_adapter_version=(
                    _semver_range(str(manifest["a2aAdapterRange"]))
                    if manifest.get("a2aAdapterRange") else None
                ),
                agent_adapter_version=(
                    _semver_range(str(manifest["agentAdapterRange"]))
                    if manifest.get("agentAdapterRange") else None
                ),
                runtime_index_schema_version=(
                    _semver_range(
                        str(manifest["runtimeIndexSchemaVersionRange"])
                    )
                    if manifest.get("runtimeIndexSchemaVersionRange")
                    else None
                ),
            ),
            adapter_name=adapter_name,
        )
    except (KeyError, TypeError) as exc:
        raise VersionCompatibilityError(
            f"distribution manifest missing required range: {exc}"
        ) from exc