"""Default capability discovery core.

Implements
:class:`pi_platform.ports.orchestration.capability_discovery.CapabilityDiscoveryPort`
with the deterministic §47 capability descriptor. The core
inspects the registered port implementations (Phase 4
`MultiStageRetrievalPort`, Phase 4 production
`GraphExpansion`, Phase 5 `LocalLLMPort`) and emits the §47
JSON shape.

The descriptor is the source of truth the Phase 6 MCP
`describe_capabilities` tool exposes; the core is
intentionally simple so the JSON serialisation is stable
byte-for-byte for a fixed deployment state.
"""

from __future__ import annotations

import hashlib
import json
from typing import Mapping

from pi_platform.ports.orchestration.capability_discovery import (
    CapabilityDescriptor,
    CapabilityDiscoveryError,
    CapabilityDiscoveryPort,
    CapabilityFeatures,
)


__all__ = [
    "DefaultCapabilityDiscovery",
    "DEFAULT_SERVER_VERSION",
    "DEFAULT_MCP_API_VERSION",
    "DEFAULT_KNOWLEDGE_SCHEMA_VERSION",
    "DEFAULT_OKF_VERSIONS",
]


DEFAULT_SERVER_VERSION = "0.8.0"
DEFAULT_MCP_API_VERSION = "1.3.0"
DEFAULT_KNOWLEDGE_SCHEMA_VERSION = "0.7.0"
DEFAULT_OKF_VERSIONS: tuple[str, ...] = ("0.2",)


class DefaultCapabilityDiscovery(CapabilityDiscoveryPort):
    """Default §47 capability discovery port."""

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
        self._server_version = server_version
        self._mcp_api_version = mcp_api_version
        self._knowledge_schema_version = knowledge_schema_version
        self._okf_versions = tuple(okf_versions)
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
        return CapabilityDescriptor(
            serverVersion=self._server_version,
            mcpApiVersion=self._mcp_api_version,
            knowledgeSchemaVersion=self._knowledge_schema_version,
            okfVersions=list(self._okf_versions),
            features=features,
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