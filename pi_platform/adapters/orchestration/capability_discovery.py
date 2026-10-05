"""Default capability discovery adapter.

Wraps :class:`pi_platform.core.orchestration.capability_discovery.DefaultCapabilityDiscovery`
as a thin adapter so the registry / CLI can introspect the
same shape across the default and alternative discovery
implementations.
"""

from __future__ import annotations

from pi_platform.core.orchestration.capability_discovery import (
    DEFAULT_KNOWLEDGE_SCHEMA_VERSION,
    DEFAULT_MCP_API_VERSION,
    DEFAULT_OKF_VERSIONS,
    DEFAULT_SERVER_VERSION,
    DefaultCapabilityDiscovery,
)


__all__ = [
    "DefaultCapabilityDiscoveryAdapter",
    "ADAPTER_NAME",
]


ADAPTER_NAME = "capability-discovery-default"


class DefaultCapabilityDiscoveryAdapter(DefaultCapabilityDiscovery):
    """Default §47 capability discovery adapter."""

    def __init__(
        self, *,
        server_version: str = DEFAULT_SERVER_VERSION,
        mcp_api_version: str = DEFAULT_MCP_API_VERSION,
        knowledge_schema_version: str = DEFAULT_KNOWLEDGE_SCHEMA_VERSION,
        okf_versions: tuple[str, ...] = DEFAULT_OKF_VERSIONS,
        retrieval: object = None,
        graph_expansion: object = None,
        materialisation: object = None,
        local_llm: object = None,
        a2a: object = None,
    ) -> None:
        super().__init__(
            server_version=server_version,
            mcp_api_version=mcp_api_version,
            knowledge_schema_version=knowledge_schema_version,
            okf_versions=okf_versions,
            retrieval=retrieval,
            graph_expansion=graph_expansion,
            materialisation=materialisation,
            local_llm=local_llm,
            a2a=a2a,
        )
        self._name = ADAPTER_NAME

    @property
    def backend_name(self) -> str:
        return self._name