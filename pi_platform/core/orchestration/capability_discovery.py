"""Default capability discovery core.

Implements
:class:`pi_platform.ports.orchestration.capability_discovery.CapabilityDiscoveryPort`
with the deterministic §47 capability descriptor. The core
inspects the registered port implementations (Phase 4
`MultiStageRetrievalPort`, Phase 4 production
`GraphExpansion`, Phase 5 `LocalLLMPort`) and emits the §47
JSON shape.

Phase 6 prerequisite 5: every version dimension is the
**actual offered metadata**, not architecture example numbers.
``mcpApiVersion`` is the product tool-schema API and is
distinct from the MCP SDK package version and the MCP wire
protocol version. Unavailable dimensions
(``a2aAdapterVersion`` until Phase 10,
``agentAdapterVersion`` until Phase 7+) are reported
unavailable rather than fabricated.

The descriptor is the source of truth the Phase 6 MCP
`describe_capabilities` tool exposes; the JSON serialisation is
stable byte-for-byte for a fixed deployment state.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Mapping, Optional

from pi_platform.ports.orchestration.capability_discovery import (
    CapabilityDescriptor,
    CapabilityDiscoveryError,
    CapabilityDiscoveryPort,
    CapabilityFeatures,
    DimensionValue,
    VersionDimensions,
)


__all__ = [
    "DefaultCapabilityDiscovery",
    "DEFAULT_SERVER_VERSION",
    "DEFAULT_MCP_API_VERSION",
    "DEFAULT_KNOWLEDGE_SCHEMA_VERSION",
    "DEFAULT_OKF_VERSIONS",
]


log = logging.getLogger(__name__)


DEFAULT_SERVER_VERSION = "0.8.0"
DEFAULT_MCP_API_VERSION = "1.3.0"
DEFAULT_KNOWLEDGE_SCHEMA_VERSION = "0.7.0"
DEFAULT_OKF_VERSIONS: tuple[str, ...] = ("0.2",)

# Phase 6 honest defaults — these are the *offered* values, not
# architecture examples. Phase 10 will populate
# ``a2aAdapterVersion``; Phase 7+ will populate
# ``agentAdapterVersion``.
DEFAULT_SKILL_VERSION: str | None = None  # populated by packagers
DEFAULT_PLATFORM_VERSION: str | None = None
DEFAULT_A2A_ADAPTER_VERSION: str | None = None
DEFAULT_AGENT_ADAPTER_VERSION: str | None = None
DEFAULT_RUNTIME_INDEX_SCHEMA_VERSION: str | None = None


def _build_dimensions(
    *,
    platform_version: Optional[str],
    mcp_api_version: str,
    knowledge_schema_version: str,
    okf_versions: tuple[str, ...],
    skill_version: Optional[str],
    plugin_distribution_schema: tuple[str, ...] = ("1",),
) -> VersionDimensions:
    return VersionDimensions(
        platformVersion=DimensionValue(
            name="platformVersion", value=platform_version,
            available=platform_version is not None,
        ),
        mcpApiVersion=DimensionValue(
            name="mcpApiVersion", value=mcp_api_version, available=True,
        ),
        a2aAdapterVersion=DimensionValue(
            name="a2aAdapterVersion",
            value=DEFAULT_A2A_ADAPTER_VERSION,
            available=False,  # Phase 10 not yet implemented
        ),
        knowledgeSchemaVersion=DimensionValue(
            name="knowledgeSchemaVersion",
            value=knowledge_schema_version, available=True,
        ),
        okfProfileVersion=DimensionValue(
            name="okfProfileVersion",
            value=",".join(okf_versions),
            available=bool(okf_versions),
        ),
        skillVersion=DimensionValue(
            name="skillVersion", value=skill_version,
            available=skill_version is not None,
        ),
        pluginDistributionSchemaVersion=DimensionValue(
            name="pluginDistributionSchemaVersion",
            value=",".join(plugin_distribution_schema),
            available=bool(plugin_distribution_schema),
        ),
        agentAdapterVersion=DimensionValue(
            name="agentAdapterVersion",
            value=DEFAULT_AGENT_ADAPTER_VERSION,
            available=False,  # Phase 7+ not yet implemented
        ),
        runtimeIndexSchemaVersion=DimensionValue(
            name="runtimeIndexSchemaVersion",
            value=DEFAULT_RUNTIME_INDEX_SCHEMA_VERSION,
            available=False,  # Phase 7+ not yet implemented
        ),
    )


class DefaultCapabilityDiscovery(CapabilityDiscoveryPort):
    """Default §47 capability discovery port."""

    def __init__(
        self, *,
        server_version: str = DEFAULT_SERVER_VERSION,
        mcp_api_version: str = DEFAULT_MCP_API_VERSION,
        knowledge_schema_version: str = DEFAULT_KNOWLEDGE_SCHEMA_VERSION,
        okf_versions: tuple[str, ...] = DEFAULT_OKF_VERSIONS,
        skill_version: Optional[str] = DEFAULT_SKILL_VERSION,
        platform_version: Optional[str] = DEFAULT_PLATFORM_VERSION,
        retrieval: object = None,
        graph_expansion: object = None,
        materialisation: object = None,
        local_llm: object = None,
        a2a: object = None,
    ) -> None:
        self._server_version = server_version
        self._mcp_api_version = mcp_api_version
        self._knowledge_schema_version = knowledge_schema_version
        self._okf_versions = tuple(okf_versions)
        self._skill_version = skill_version
        self._platform_version = platform_version
        self._retrieval = retrieval
        self._graph_expansion = graph_expansion
        self._materialisation = materialisation
        self._local_llm = local_llm
        self._a2a = a2a
        self._describe_calls = 0
        self._refresh_calls = 0

    def describe(self) -> CapabilityDescriptor:
        self._describe_calls += 1
        return self._build()

    def refresh(self) -> CapabilityDescriptor:
        self._refresh_calls += 1
        return self._build()

    def stats(self) -> Mapping[str, int]:
        return {
            "describe_calls": self._describe_calls,
            "refresh_calls": self._refresh_calls,
            "feature_count": 6,
        }

    # -- internal helpers --------------------------------------------------

    def _build(self) -> CapabilityDescriptor:
        features = CapabilityFeatures(
            hybridRetrieval=self._retrieval is not None,
            graphExpansion=self._graph_expansion is not None,
            okf=list(self._okf_versions),
            materialization=self._materialisation is not None,
            a2a=self._a2a is not None,
            localLlm=self._local_llm_available(),
        )
        # ``platformVersion`` defaults to ``server_version`` so the
        # 9-dimension block is populated whenever the legacy top-
        # level ``serverVersion`` is populated. A caller that
        # explicitly passes ``platform_version=None`` keeps it
        # unavailable rather than fabricating a value.
        effective_platform_version = (
            self._platform_version
            if self._platform_version is not None
            else self._server_version
        )
        dimensions = _build_dimensions(
            platform_version=effective_platform_version,
            mcp_api_version=self._mcp_api_version,
            knowledge_schema_version=self._knowledge_schema_version,
            okf_versions=self._okf_versions,
            skill_version=self._skill_version,
        )
        return CapabilityDescriptor(
            serverVersion=self._server_version,
            mcpApiVersion=self._mcp_api_version,
            knowledgeSchemaVersion=self._knowledge_schema_version,
            okfVersions=list(self._okf_versions),
            features=features,
            dimensions=dimensions,
        )

    def _local_llm_available(self) -> bool:
        if self._local_llm is None:
            return False
        available = getattr(self._local_llm, "is_available", None)
        if callable(available):
            try:
                return bool(available())
            except Exception:
                return False
        return False


def _stable_digest(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.blake2b(encoded.encode("utf-8"), digest_size=16).hexdigest()